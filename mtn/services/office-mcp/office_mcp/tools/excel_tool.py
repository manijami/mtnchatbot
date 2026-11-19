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
    "Create an MTN-branded Excel (.xlsx) workbook. Templates: action_tracker or project_plan. "
    "Each sheet becomes a filterable table with a frozen header. Columns are typed: text, number, "
    "integer, currency, percent, date (YYYY-MM-DD) or formula. A formula column refers to other "
    "columns of the same row by name in braces and gets null in every row. Optional: "
    "allowed_values (dropdown), totals, conditional_formats, a summary (count/sum per group) and "
    "one chart with at most 4 value_columns. Formulas are recalculated and checked before the file "
    "is attached automatically. Example sheet: {\"name\": \"Actions\", \"columns\": [{\"name\": "
    "\"Action\"}, {\"name\": \"Due\", \"type\": \"date\"}, {\"name\": \"Status\", "
    "\"allowed_values\": [\"Open\", \"Done\"]}, {\"name\": \"Days left\", \"type\": \"formula\", "
    "\"formula\": \"={Due}-TODAY()\"}], \"rows\": [[\"Patch servers\", \"2026-11-20\", \"Open\", null]], "
    "\"conditional_formats\": [{\"column\": \"Status\", \"operator\": \"equal\", \"value\": \"Done\", "
    "\"style\": \"good\"}], \"summary\": {\"group_by\": \"Status\"}, \"chart\": {\"type\": \"pie\", "
    "\"source\": \"summary\", \"title\": \"By status\"}}"
)


async def recalc_check(target: Path, folder: Path, checks: dict) -> None:
    """Precise check: recalculates a copy in LibreOffice and names every error cell."""
    work = folder / "recalc"
    try:
        copy = await render.convert(target, "xlsx:Calc MS Excel 2007 XML", work, timeout=60)
        report = await anyio.to_thread.run_sync(excel.recalc_report, target, copy)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    errors = report["errors"]
    checks["recalc"] = {
        "engine": "LibreOffice (cell scan)",
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


async def rendered_formula_check(target: Path, folder: Path, pdf: Path, checks: dict) -> None:
    """Fast path: the PDF render already computed every formula (LibreOffice recalculates
    formulas that have no cached value). Only if an error token shows up in the rendered text
    does the slower per-cell recalculation run, so a failure still names the cells."""
    text = await render.pdf_text(pdf)
    formulas = await anyio.to_thread.run_sync(excel.formula_count, target)
    if any(token in text for token in excel.ERROR_VALUES):
        await recalc_check(target, folder, checks)
        return
    checks["recalc"] = {"engine": "LibreOffice (render)", "formulas": formulas, "error_count": 0, "errors": []}


SPEC = WorkbookSpec


def make_job(spec: WorkbookSpec, template, document_id: str | None = None, coercions: list | None = None) -> pipeline.Job:
    return pipeline.Job(
        kind="excel",
        ext=".xlsx",
        spec=spec,
        template=template,
        build=excel.build,
        reopen=excel.reopen,
        post_render_checks=rendered_formula_check,
        document_id=document_id,
        coercions=coercions,
        summary=lambda s: (
            f"{s['sheets']} sheet{'s' if s['sheets'] != 1 else ''}, {s['rows']} rows, {s['formulas']} "
            f"formulas recalculated with no errors, {s['charts']} chart{'s' if s['charts'] != 1 else ''}"
        ),
        preview={"dpi": 60, "max_pages": 4, "columns": 2},
    )


async def run(ctx: ToolContext, arguments: dict) -> list:
    notes: list[str] = []
    spec = parse(WorkbookSpec, arguments, notes, "excel")
    try:
        template = templates.load(ctx.settings.templates_dir, "excel", spec.template)
    except templates.TemplateError as exc:
        raise ToolError(f"Template problem: {exc}.") from None
    return await pipeline.run(ctx, make_job(spec, template, coercions=notes))


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
