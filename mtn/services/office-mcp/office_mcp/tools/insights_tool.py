"""inspect_workbook and analyse_workbook (Excel insights).

The person's upload is read read-only and owner-scoped (``files.py``). Reading and computing run
in a separate process that is stopped at the time limit. The JSON results are the only numbers
the model may quote; each analysis run is saved for its owner so files can be built from it.
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

import anyio
from mcp import types

from .. import insights_analyse, insights_data
from ..files import InsightLimits, LocalUploadsSource, SourceFile
from . import Tool, ToolContext, ToolError, register

FILE_HINT = "The exact name of a spreadsheet the user attached to this chat (.xlsx or .csv), e.g. 'sales.xlsx'."
INSPECT_DESCRIPTION = (
    "Inspect a spreadsheet the user uploaded (.xlsx or .csv) BEFORE analysing it: sheets, columns with "
    "their types (number, date, text, true/false), row counts, and data quality (blanks, duplicate rows, "
    "mixed types, unusual values). Read-only. Example: {\"file\": \"sales.xlsx\"}"
)
ANALYSE_DESCRIPTION = (
    "Analyse a spreadsheet the user uploaded, with pandas. Returns tables of computed numbers: these are "
    "the ONLY numbers you may quote; never calculate or estimate numbers yourself. Analysis types: "
    "group_summary (group_by, measure, agg sum|average|count|min|max|median), time_trend (date_column, "
    "measure, period day|week|month|quarter|year, agg), top_n (group_by, measure, n, order top|bottom), "
    "share_of_total (group_by, measure), period_change (date_column, measure, period, compare "
    "previous|year_ago), distribution (column, bins). measure may be omitted with agg 'count'. Optional "
    "filters: [{column, op eq|ne|in|gt|gte|lt|lte|between, value}]. Use column names exactly as "
    "inspect_workbook reports them. Example: {\"file\": \"sales.xlsx\", \"sheet\": \"Sales\", \"analyses\": "
    "[{\"type\": \"group_summary\", \"group_by\": \"Region\", \"measure\": \"Revenue\", \"agg\": \"sum\"}, "
    "{\"type\": \"time_trend\", \"date_column\": \"Month\", \"measure\": \"Revenue\", \"period\": \"month\"}]}"
)


def _source(ctx: ToolContext) -> LocalUploadsSource:
    if ctx.settings.uploads_dir is None:
        raise ToolError("Spreadsheet analysis is not enabled on this server.")
    return LocalUploadsSource(ctx.settings.uploads_dir, ctx.settings.insight_limits)


# Worker functions run in a child process (picklable arguments and results only).
def _inspect_worker(src: SourceFile, limits: InsightLimits) -> dict:
    return insights_data.describe(insights_data.read_workbook(src, limits))


def _analyse_worker(src: SourceFile, limits: InsightLimits, arguments: dict) -> dict:
    request = insights_analyse.parse_request(arguments, limits.max_analyses)
    return insights_analyse.analyse(insights_data.read_workbook(src, limits), request)


async def _in_child(fn, *args, timeout_s: int):
    try:
        with anyio.fail_after(timeout_s):
            return await anyio.to_process.run_sync(fn, *args, cancellable=True)
    except TimeoutError as exc:
        raise ToolError(f"The analysis took longer than {timeout_s} s and was stopped. Try fewer analyses or a smaller sheet.") from exc


def save_run(data_dir: Path, owner: str, payload: dict) -> str:
    run_id = "run_" + secrets.token_hex(8)
    folder = data_dir / "insights" / owner
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{run_id}.json").write_text(json.dumps({**payload, "run_id": run_id, "created": time.time()}))
    return run_id


def load_run(data_dir: Path, owner: str, run_id: str) -> dict:
    if not run_id.startswith("run_") or not run_id[4:].isalnum():
        raise ToolError("Unknown analysis run.")
    path = data_dir / "insights" / owner / f"{run_id}.json"
    if not path.is_file():
        raise ToolError("Unknown analysis run. Run analyse_workbook first.")
    return json.loads(path.read_text())


def _text(header: str, body: dict) -> list:
    return [types.TextContent(type="text", text=header + "\n" + json.dumps(body, ensure_ascii=False, default=str))]


async def inspect_workbook(ctx: ToolContext, arguments: dict) -> list:
    src = _source(ctx).open_for(ctx.identity.user_id, str(arguments.get("file", "")))
    limits = ctx.settings.insight_limits
    result = await _in_child(_inspect_worker, src, limits, timeout_s=limits.timeout_s)
    return _text(f"Contents of '{src.name}' (read-only). Choose analyses that fit these columns.", result)


async def analyse_workbook(ctx: ToolContext, arguments: dict) -> list:
    if not isinstance(arguments, dict):
        raise ToolError("Send the analysis request as a JSON object.")
    src = _source(ctx).open_for(ctx.identity.user_id, str(arguments.get("file", "")))
    limits = ctx.settings.insight_limits
    result = await _in_child(_analyse_worker, src, limits, {**arguments, "file": src.name}, timeout_s=limits.timeout_s)
    result["run_id"] = save_run(ctx.settings.data_dir, ctx.identity.user_id, result)
    return _text(
        "Computed results. Quote ONLY these numbers, each with its sheet and columns; say 'not enough data' "
        "where a result has no rows. Use run_id to create charts or files from this run.",
        result,
    )


_FILE_SCHEMA = {"type": "string", "description": FILE_HINT}

register(Tool(
    definition=types.Tool(
        name="inspect_workbook",
        description=INSPECT_DESCRIPTION,
        inputSchema={"type": "object", "properties": {"file": _FILE_SCHEMA}, "required": ["file"]},
    ),
    run=inspect_workbook,
))

register(Tool(
    definition=types.Tool(
        name="analyse_workbook",
        description=ANALYSE_DESCRIPTION,
        inputSchema={
            "type": "object",
            "properties": {
                "file": _FILE_SCHEMA,
                "sheet": {"type": "string", "description": "Sheet name; needed when the workbook has several."},
                "analyses": {"type": "array", "items": {"type": "object"}, "description": "1 to 8 analyses (see description)."},
                "filters": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["file", "analyses"],
        },
    ),
    run=analyse_workbook,
))
