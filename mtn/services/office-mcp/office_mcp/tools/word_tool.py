"""create_word_document."""

from __future__ import annotations

from mcp import types

from .. import pipeline, templates, word
from ..schemas import WORD_INPUT_SCHEMA, WordDocumentSpec, parse
from . import Tool, ToolContext, ToolError, register

DESCRIPTION = (
    "Create an MTN-branded Word (.docx) document from structured content. Pick the template that "
    "fits: proposal, meeting_minutes or incident_report (also for IT/operational processes). "
    "Write the complete content in sections. With headings and a table, one A4 page holds about "
    "250-300 words of body text: a two-page document is roughly 500-550 words in 6-7 sections. "
    "When the user asks for a length, set target_pages. The finished file is attached to the chat "
    "automatically; report the page count the tool returns."
)


async def run(ctx: ToolContext, arguments: dict) -> list:
    spec = parse(WordDocumentSpec, arguments)
    try:
        template = templates.load(ctx.settings.templates_dir, "word", spec.template)
    except templates.TemplateError as exc:
        raise ToolError(f"Template problem: {exc}.") from None
    job = pipeline.Job(
        kind="word",
        ext=".docx",
        spec=spec,
        template=template,
        build=word.build,
        reopen=word.reopen,
        summary=lambda s: f"{s['sections']} sections, {s['tables']} tables, ~{s['words']} words",
    )
    return await pipeline.run(ctx, job)


TOOL = register(
    Tool(
        definition=types.Tool(
            name="create_word_document",
            title="Create Word document",
            description=DESCRIPTION,
            inputSchema=WORD_INPUT_SCHEMA,
            annotations=types.ToolAnnotations(
                title="Create Word document",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        ),
        run=run,
    )
)
