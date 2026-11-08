"""create_excel_workbook."""

from __future__ import annotations

import shutil
from pathlib import Path

import anyio
from mcp import types

from .. import excel, pipeline, render, templates
from ..schemas import EXCEL_INPUT_SCHEMA, WorkbookSpec, parse
from ..validate import ValidationFailed
from . import Tool, ToolContext, ToolError, register

DESCRIPTION = (
    "Create an MTN-branded Excel (.xlsx) workbook. Templates: action_tracker (actions with owner, "
    "due date, status, priority) or project_plan (tasks with dates, durations, progress). Each "
    "sheet is a filterable table with a frozen header. Columns are typed (text, number, integer, "
    "currency, percent, date as YYYY-MM-DD, formula). Formula columns refer to other columns by "
    "name, e.g. \"={End}-{Start}\". Optional: dropdown choices, total row, conditional formatting, "
    "a formula-driven summary (e.g. count per Status) and a native chart. Formulas are recalculated "
    "and checked for errors before the file is attached to the chat automatically."
)


async def recalc_check(target: Path, folder: Path, checks: dict) -> None:
    """Recalculates a copy in headless LibreOffice and rejects error values (#REF!, #DIV/0!, ...)."""
    work = folder / "recalc"
    try:
        copy = await render.convert(target, "xlsx:Calc MS Excel 2007 XML", work, timeout=60)
        report = await anyio.to_thread.run_sync(excel.recalc_report, target, copy)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    errors = report["errors"]
    checks["recalc"] = {
        "engine": "LibreOffice",
        "formulas": report["formulas"],
        "computed": report["computed"],
        "errors": errors[:20],
        "error_count": len(errors),
    }
    if report["formulas"] and not report["computed"]:
        raise ValidationFailed("the formulas could not be recalculated", checks)
    if errors:
        raise ValidationFailed(
            "formulas produce error values after recalculation: " + "; ".join(errors[:8])
            + ". Fix the formulas or the data they use",
            checks,
        )


SPEC = WorkbookSpec


def make_job(spec: WorkbookSpec, template, document_id: str | None = None) -> pipeline.Job:
    return pipeline.Job(
        kind="excel",
        ext=".xlsx",
        spec=spec,
        template=template,
        build=excel.build,
        reopen=excel.reopen,
        extra_checks=recalc_check,
        document_id=document_id,
        summary=lambda s: (
            f"{s['sheets']} sheet{'s' if s['sheets'] != 1 else ''}, {s['rows']} rows, {s['formulas']} "
            f"formulas recalculated with no errors, {s['charts']} chart{'s' if s['charts'] != 1 else ''}"
        ),
        preview={"dpi": 60, "max_pages": 4, "columns": 2},
    )


async def run(ctx: ToolContext, arguments: dict) -> list:
    spec = parse(WorkbookSpec, arguments)
    try:
        template = templates.load(ctx.settings.templates_dir, "excel", spec.template)
    except templates.TemplateError as exc:
        raise ToolError(f"Template problem: {exc}.") from None
    return await pipeline.run(ctx, make_job(spec, template))


TOOL = register(
    Tool(
        definition=types.Tool(
            name="create_excel_workbook",
            title="Create Excel workbook",
            description=DESCRIPTION,
            inputSchema=EXCEL_INPUT_SCHEMA,
            annotations=types.ToolAnnotations(
                title="Create Excel workbook",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        ),
        run=run,
    )
)
