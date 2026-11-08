"""create_word_document."""

from __future__ import annotations

from mcp import types

from .. import pipeline, templates, word
from ..schemas import WORD_INPUT_SCHEMA, WordDocumentSpec, parse
from . import Tool, ToolContext, ToolError, register

DESCRIPTION = (
    "Create an MTN-branded Word (.docx) document. Templates: proposal, meeting_minutes, "
    "incident_report (also for IT/operational processes). Give the complete content as sections; "
    "every list field is a real JSON array, never a string containing JSON. With headings and a "
    "table, one A4 page holds about 250-300 words: a two-page document is 6-7 sections and "
    "500-550 words; a one-page document is 3-4 short sections and no more than ~200 words. "
    "When the user asks for a length, set target_pages. The file is attached to the chat "
    "automatically. Example: {\"template\": \"incident_report\", \"title\": \"VPN outage\", "
    "\"target_pages\": 1, \"cover_fields\": [{\"label\": \"Severity\", \"value\": \"P2\"}], "
    "\"sections\": [{\"heading\": \"Summary\", \"paragraphs\": [\"...\"]}, {\"heading\": "
    "\"Timeline\", \"table\": {\"columns\": [\"Time\", \"Event\"], \"rows\": [[\"09:00\", "
    "\"Alerts fired\"]]}}, {\"heading\": \"Actions\", \"numbered\": [\"...\"]}]}"
)


SPEC = WordDocumentSpec


def make_job(spec: WordDocumentSpec, template, document_id: str | None = None, coercions: list | None = None) -> pipeline.Job:
    return pipeline.Job(
        kind="word",
        ext=".docx",
        spec=spec,
        template=template,
        build=word.build,
        reopen=word.reopen,
        document_id=document_id,
        coercions=coercions,
        compact_levels=2 if spec.target_pages else 0,
        summary=lambda s: f"{s['sections']} sections, {s['tables']} tables, ~{s['words']} words",
    )


async def run(ctx: ToolContext, arguments: dict) -> list:
    notes: list[str] = []
    spec = parse(WordDocumentSpec, arguments, notes, "word")
    try:
        template = templates.load(ctx.settings.templates_dir, "word", spec.template)
    except templates.TemplateError as exc:
        raise ToolError(f"Template problem: {exc}.") from None
    return await pipeline.run(ctx, make_job(spec, template, coercions=notes))


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
