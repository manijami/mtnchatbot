"""revise_office_file and get_generation_status (owner-scoped)."""

from __future__ import annotations

import datetime as dt

from mcp import types

from .. import pipeline, templates
from .. import revise as revisions
from ..schemas import parse
from ..store import STATUS_COMPLETE
from . import Tool, ToolContext, ToolError, excel_tool, powerpoint_tool, register, word_tool

KINDS = {"word": word_tool, "powerpoint": powerpoint_tool, "excel": excel_tool}

REVISE_DESCRIPTION = (
    "Revise a Word, PowerPoint or Excel file this user generated earlier in the chat; creates the "
    "next version and keeps earlier ones unchanged. Pass document_id and either changes (edits to "
    "the stored content: op add|replace|remove, path, value) or content (complete new content). "
    "Paths: /sections/N for Word, /sheets/N for Excel, and for PowerPoint the slide number the user "
    "sees, /slide/N (title slide = 1; the create result lists every slide). A slide holds a table "
    "OR a chart: to put a table on a chart slide, remove the chart in the same change list. "
    "Example (shorten slide 2, risks table on slide 5): {\"document_id\": \"...\", \"changes\": "
    "[{\"op\": \"replace\", \"path\": \"/slide/2/bullets\", \"value\": [\"Short point\"]}, "
    "{\"op\": \"remove\", \"path\": \"/slide/5/chart\"}, {\"op\": \"add\", \"path\": "
    "\"/slide/5/table\", \"value\": {\"columns\": [\"Risk\", \"Mitigation\"], \"rows\": [[\"...\", "
    "\"...\"]]}}]}. Remove only what exists (get_generation_status shows the structure). Files "
    "uploaded by employees cannot be revised yet."
)
REVISE_SCHEMA = {
    "type": "object",
    "properties": {
        "document_id": {"type": "string", "description": "document_id from the create result."},
        "changes": {
            "type": "array",
            "description": "Edits to the stored content.",
            "items": {
                "type": "object",
                "properties": {"op": {"type": "string"}, "path": {"type": "string"}, "value": {}},
                "required": ["op", "path"],
            },
        },
        "content": {"type": "object", "description": "Complete replacement content (instead of changes)."},
    },
    "required": ["document_id"],
}
STATUS_DESCRIPTION = (
    "Show this user's generated files: with document_id, every version's status, page/slide count, "
    "checks and an outline of the latest version with the paths revise_office_file uses; without "
    "it, the user's most recent files."
)
STATUS_SCHEMA = {
    "type": "object",
    "properties": {"document_id": {"type": "string", "description": "Optional document_id."}},
}
NOT_FOUND = "No generated file with that document_id was found for you."


def _time(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


async def revise(ctx: ToolContext, arguments: dict) -> list:
    document_id = str(arguments.get("document_id", "")).strip()
    doc = ctx.store.get_document(ctx.identity.user_id, document_id) if document_id else None
    if doc is None:
        raise ToolError(NOT_FOUND)
    base = next((v for v in reversed(doc.versions) if v.status == STATUS_COMPLETE), None)
    if base is None:
        raise ToolError("That document has no completed version to revise; create it again instead.")
    module = KINDS[doc.kind]
    has_changes, has_content = bool(arguments.get("changes")), bool(arguments.get("content"))
    if has_changes == has_content:
        raise ToolError("Pass exactly one of changes or content.")
    if has_changes:
        new_spec = revisions.apply_changes(base.spec, arguments["changes"], doc.kind)
    else:
        new_spec = dict(arguments["content"])
    new_spec["template"] = doc.template  # a revision keeps the document's template
    notes: list[str] = []
    spec = parse(module.SPEC, new_spec, notes, doc.kind)
    try:
        template = templates.load(ctx.settings.templates_dir, doc.kind, doc.template, base.template_version)
    except templates.TemplateError as exc:
        raise ToolError(f"Template problem: {exc}.") from None
    content = await pipeline.run(ctx, module.make_job(spec, template, document_id=doc.id, coercions=notes))
    content[0].text = content[0].text.replace(
        "Created the", f"Revised version {base.version} into a new version of the", 1
    ) + f" Version {base.version} is unchanged."
    return content


async def status(ctx: ToolContext, arguments: dict) -> list:
    owner = ctx.identity.user_id
    document_id = str(arguments.get("document_id") or "").strip()
    if not document_id:
        docs = ctx.store.list_documents(owner, limit=10)
        if not docs:
            return [types.TextContent(type="text", text="You have no generated files yet.")]
        lines = [
            f"- {d.id}: {d.kind} \"{d.title}\", latest v{d.latest.version} ({d.latest.status}), {_time(d.created_at)}"
            for d in docs
            if d.latest
        ]
        return [types.TextContent(type="text", text="Your recent generated files:\n" + "\n".join(lines))]
    doc = ctx.store.get_document(owner, document_id)
    if doc is None:
        raise ToolError(NOT_FOUND)
    lines = [f"{doc.kind} \"{doc.title}\" (template {doc.template}), document_id {doc.id}:"]
    for v in doc.versions:
        unit = "slides" if doc.kind == "powerpoint" else "pages"
        detail = f"{v.filename}, {v.pages} {unit}" if v.status == STATUS_COMPLETE else (v.error or "")[:200]
        lines.append(f"- v{v.version} {v.status} ({_time(v.created_at)}): {detail}")
    latest = next((v for v in reversed(doc.versions) if v.status == STATUS_COMPLETE), None)
    if latest:
        lines.append(f"Outline of v{latest.version} (paths for revise_office_file):")
        lines.extend(revisions.outline(doc.kind, latest.spec))
    return [types.TextContent(type="text", text="\n".join(lines))]


def _annotations(title: str, read_only: bool) -> types.ToolAnnotations:
    return types.ToolAnnotations(
        title=title, readOnlyHint=read_only, destructiveHint=False, idempotentHint=read_only, openWorldHint=False
    )


register(
    Tool(
        definition=types.Tool(
            name="revise_office_file",
            title="Revise generated Office file",
            description=REVISE_DESCRIPTION,
            inputSchema=REVISE_SCHEMA,
            annotations=_annotations("Revise generated Office file", False),
        ),
        run=revise,
    )
)
register(
    Tool(
        definition=types.Tool(
            name="get_generation_status",
            title="Generated file status",
            description=STATUS_DESCRIPTION,
            inputSchema=STATUS_SCHEMA,
            annotations=_annotations("Generated file status", True),
        ),
        run=status,
    )
)
