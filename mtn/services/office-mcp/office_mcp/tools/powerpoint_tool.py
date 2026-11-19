"""create_powerpoint_presentation."""

from __future__ import annotations

from pathlib import Path

import anyio
from mcp import types
from pptx import Presentation

from .. import bounds, pipeline, powerpoint, templates
from ..schemas import POWERPOINT_INPUT_SCHEMA, PresentationSpec, parse
from ..validate import ValidationFailed
from . import Tool, ToolContext, ToolError, register

DESCRIPTION = (
    "Create an MTN-branded 16:9 PowerPoint (.pptx) deck. Templates: executive_update or "
    "project_status. A title slide is made from title/subtitle and counts as slide 1, so a "
    "five-slide deck has exactly 4 items in slides (set target_slides 5). Each content slide has "
    "a short title and bullets (up to 6, each under 160 characters; write numbered steps as "
    "bullets), and optionally ONE table (up to 6 columns x 8 rows) OR ONE chart - never both. "
    "Charts use categories plus series of numbers, nothing else. Put detail in notes. Every list "
    "field is a real JSON array, never a string. The deck is checked for overflow and attached "
    "automatically. Example: {\"template\": \"project_status\", \"title\": \"Migration status\", "
    "\"target_slides\": 3, \"slides\": [{\"title\": \"Summary\", \"bullets\": [\"On track\", "
    "\"One risk\"], \"key_message\": \"Go-live 1 Dec\", \"notes\": \"...\"}, {\"title\": "
    "\"Progress\", \"bullets\": [\"Tasks up each week\"], \"chart\": {\"type\": \"line\", "
    "\"categories\": [\"W1\", \"W2\"], \"series\": [{\"name\": \"Done\", \"values\": [4, 9]}]}}]}"
)


def reopen(path: Path) -> dict:
    prs = Presentation(path)
    notes = sum(1 for s in prs.slides if s.has_notes_slide and s.notes_slide.notes_text_frame.text.strip())
    return {"slides": len(prs.slides), "notes": notes}


async def bounds_check(target: Path, _folder: Path, checks: dict) -> None:
    report = await anyio.to_thread.run_sync(bounds.check, target)
    checks["bounds"] = {
        "slides": report["slides"],
        "shapes": report["shapes"],
        "issues": report["issues"],
        "per_slide": [
            {k: v for k, v in entry.items() if k == "slide" or k == "shapes" or v} for entry in report["per_slide"]
        ],
    }
    if report["issues"]:
        raise ValidationFailed("layout problems: " + "; ".join(report["issues"][:8]), checks)


SPEC = PresentationSpec


def make_job(spec: PresentationSpec, template, document_id: str | None = None, coercions: list | None = None) -> pipeline.Job:
    return pipeline.Job(
        kind="powerpoint",
        ext=".pptx",
        spec=spec,
        template=template,
        build=powerpoint.build,
        reopen=reopen,
        extra_checks=bounds_check,
        document_id=document_id,
        coercions=coercions,
        summary=lambda s: f"{s['charts']} charts, {s['tables']} tables, speaker notes on {s['notes']}, bounds check passed",
        preview={"dpi": 40, "max_pages": 21, "columns": 3},
    )


async def run(ctx: ToolContext, arguments: dict) -> list:
    notes: list[str] = []
    spec = parse(PresentationSpec, arguments, notes, "powerpoint")
    try:
        template = templates.load(ctx.settings.templates_dir, "powerpoint", spec.template)
    except templates.TemplateError as exc:
        raise ToolError(f"Template problem: {exc}.") from None
    return await pipeline.run(ctx, make_job(spec, template, coercions=notes))


TOOL = register(
    Tool(
        definition=types.Tool(
            name="create_powerpoint_presentation",
            title="Create PowerPoint presentation",
            description=DESCRIPTION,
            inputSchema=POWERPOINT_INPUT_SCHEMA,
            annotations=types.ToolAnnotations(
                title="Create PowerPoint presentation",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        ),
        run=run,
    )
)
