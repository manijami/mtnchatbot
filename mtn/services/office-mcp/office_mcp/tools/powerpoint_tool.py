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
    "Create an MTN-branded 16:9 PowerPoint (.pptx) deck. Templates: executive_update (leadership "
    "update) or project_status. A title slide is added from title/subtitle and counts as a slide, "
    "so a five-slide deck has 4 items in slides. Each content slide has a short title and up to 6 "
    "bullets of at most 160 characters, a table (up to 6 columns x "
    "8 rows) or a native chart; bullets may sit beside a table or chart. Add speaker notes for "
    "detail instead of crowding slides. Set target_slides when the user asks for a number of "
    "slides. The deck is checked for overflow and overlap and attached to the chat automatically."
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


def make_job(spec: PresentationSpec, template, document_id: str | None = None) -> pipeline.Job:
    return pipeline.Job(
        kind="powerpoint",
        ext=".pptx",
        spec=spec,
        template=template,
        build=powerpoint.build,
        reopen=reopen,
        extra_checks=bounds_check,
        document_id=document_id,
        summary=lambda s: f"{s['charts']} charts, {s['tables']} tables, speaker notes on {s['notes']}, bounds check passed",
        preview={"dpi": 40, "max_pages": 21, "columns": 3},
    )


async def run(ctx: ToolContext, arguments: dict) -> list:
    spec = parse(PresentationSpec, arguments)
    try:
        template = templates.load(ctx.settings.templates_dir, "powerpoint", spec.template)
    except templates.TemplateError as exc:
        raise ToolError(f"Template problem: {exc}.") from None
    return await pipeline.run(ctx, make_job(spec, template))


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
