"""Shared generate → validate → render → record → deliver flow for every document kind."""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

import anyio
from mcp import types
from pydantic import BaseModel

from . import brand, render
from .templates import Template
from .tools import ToolContext, ToolError, registry
from .validate import ValidationFailed, check_package

KIND_LABEL = {"word": "Word document", "powerpoint": "PowerPoint presentation", "excel": "Excel workbook"}
_UNSAFE = re.compile(r"[^A-Za-z0-9 _-]+")


def output_filename(spec: BaseModel, version: int, ext: str) -> str:
    base = getattr(spec, "filename", None) or getattr(spec, "title", "") or "document"
    base = _UNSAFE.sub("", base).strip().replace(" ", "-")
    base = re.sub(r"-{2,}", "-", base)[:60].strip("-_") or "document"
    return f"{base}{'' if version == 1 else f'-v{version}'}{ext}"


class PageTargetExceeded(ValueError):
    pass


async def _check_page_target(job: "Job", pages: int, pdf: Path, checks: dict) -> None:
    """Rejects a render longer than target_pages, saying how much must go and how."""
    target = getattr(job.spec, "target_pages", None)
    if not target or pages <= target:
        return
    overflow = await render.pdf_text_lines(pdf, target + 1, pages)
    per_page = await render.pdf_text_lines(pdf, 1, 1) or 45
    checks["page_target"] = {"target": target, "rendered": pages, "overflow_lines": overflow}
    sections = getattr(job.spec, "sections", []) or []
    tables = sum(1 for section in sections if getattr(section, "table", None))
    raise PageTargetExceeded(
        f"it renders to {pages} pages but target_pages is {target}: about {overflow} lines spill past "
        f"page {target} (a full page holds about {per_page}). Remove at least that many lines. "
        f"Each section heading with its spacing takes about 3 lines, each table row 1-2 lines and each "
        f"sentence about 1 line (the document has {len(sections)} sections and {tables} tables). "
        "Merging or dropping sections and table rows saves the most."
    )


@dataclass
class Job:
    kind: str
    ext: str
    spec: BaseModel
    template: Template
    build: Callable[[BaseModel, Template, Path, bytes | None], dict]
    reopen: Callable[[Path], dict]
    extra_checks: Callable[[Path, Path, dict], Awaitable[None]] | None = None
    document_id: str | None = None  # set for a revision
    summary: Callable[[dict], str] | None = None
    preview: dict | None = None  # preview_png options (dpi, max_pages, columns)


async def run(ctx: ToolContext, job: Job) -> list:
    started = time.monotonic()
    store, owner, settings = ctx.store, ctx.identity.user_id, ctx.settings
    document_id = job.document_id or store.create_document(
        owner=owner,
        kind=job.kind,
        template=job.template.name,
        title=getattr(job.spec, "title", ""),
        conversation_id=ctx.identity.conversation_id,
    )
    version = store.add_version(
        owner=owner,
        document_id=document_id,
        template_version=job.template.version,
        spec=job.spec.model_dump(mode="json"),
        message_id=ctx.identity.message_id,
    )
    folder = store.version_dir(owner, document_id, version)
    target = folder / output_filename(job.spec, version, job.ext)
    checks: dict = {"template": f"{job.template.name} {job.template.version}"}
    timings: dict = {}
    try:
        logo = await anyio.to_thread.run_sync(brand.load_logo, settings.logo_dir)
        checks["logo"] = "added" if logo else "absent"
        mark = time.monotonic()
        stats = await anyio.to_thread.run_sync(job.build, job.spec, job.template, target, logo)
        timings["build_ms"] = int((time.monotonic() - mark) * 1000)
        mime = check_package(target, settings.max_file_bytes, checks)
        checks["reopen"] = await anyio.to_thread.run_sync(job.reopen, target)
        if job.extra_checks:
            await job.extra_checks(target, folder, checks)
        mark = time.monotonic()
        pdf = await render.convert(target, "pdf", folder, settings.convert_timeout_s)
        pdf = pdf.rename(folder / "preview.pdf")
        pages = await render.pdf_pages(pdf)
        checks["render"] = "ok"
        checks["pages"] = pages
        if "slides" in stats and pages != stats["slides"]:
            raise ValueError(f"LibreOffice rendered {pages} slides but the deck has {stats['slides']}")
        await _check_page_target(job, pages, pdf, checks)
        await render.preview_png(pdf, folder / "preview.png", pages, **(job.preview or {}))
        timings["render_ms"] = int((time.monotonic() - mark) * 1000)
    except PageTargetExceeded as exc:
        checks["error"] = str(exc)
        store.fail_version(document_id=document_id, version=version, error=str(exc), checks=checks)
        raise ToolError(
            f"The {KIND_LABEL[job.kind]} was not delivered because {exc} "
            "Shorten the content and call the tool again with the same target_pages."
        ) from None
    except (ValidationFailed, render.RenderError, ValueError, KeyError) as exc:
        checks["error"] = str(exc)
        store.fail_version(document_id=document_id, version=version, error=str(exc), checks=checks)
        raise ToolError(
            f"The {KIND_LABEL[job.kind]} failed validation and was not delivered: {exc}. "
            "Simplify or correct the content and call the tool again."
        ) from None
    except ToolError:
        store.fail_version(document_id=document_id, version=version, error="rejected", checks=checks)
        raise
    except Exception:
        store.fail_version(document_id=document_id, version=version, error="internal error", checks=checks)
        raise

    duration_ms = int((time.monotonic() - started) * 1000)
    checks["timings"] = {**timings, "total_ms": duration_ms}
    store.complete_version(
        document_id=document_id,
        version=version,
        file_path=target,
        mime_type=mime,
        pages=checks.get("pages"),
        checks=checks,
        duration_ms=duration_ms,
    )
    return _deliver(ctx, job, document_id, version, target, mime, stats, checks)


def _deliver(ctx, job: Job, document_id, version, target: Path, mime, stats, checks) -> list:
    pages = checks.get("pages")
    unit = {"powerpoint": "slide", "excel": "printed page"}.get(job.kind, "page")
    detail = job.summary(stats) if job.summary else ""
    text = (
        f'Created the {KIND_LABEL[job.kind]} "{getattr(job.spec, "title", target.stem)}" as {target.name} '
        f"({pages} {unit}{'s' if pages != 1 else ''}{', ' + detail if detail else ''}) from the MTN "
        f"{job.template.title} template {job.template.version}. Version {version}, "
        f"document_id {document_id}. Checks passed: package, reopen, LibreOffice render. "
        f"Logo {'added' if checks.get('logo') == 'added' else 'not available (logo-free output)'}.\n"
        "The file is attached to this message for the user. Do not paste file contents or links."
    )
    if "revise_office_file" in registry:
        text += " To change it, call revise_office_file with this document_id."
    if job.kind == "powerpoint":
        from .revise import outline

        # The model must use the user's slide numbers (title slide = 1), not its own.
        text += "\nSlides (numbered as the user sees them; use these paths to revise):\n" + "\n".join(
            outline("powerpoint", job.spec.model_dump(mode="json"))
        )
    content: list = [
        types.TextContent(type="text", text=text),
        types.EmbeddedResource(
            type="resource",
            resource=types.BlobResourceContents(
                uri=f"office://documents/{document_id}/v{version}/{target.name}",
                mimeType=mime,
                blob=base64.b64encode(target.read_bytes()).decode("ascii"),
            ),
        ),
    ]
    preview = target.parent / "preview.png"
    if ctx.settings.preview_image and preview.is_file():
        content.append(
            types.ImageContent(
                type="image", data=base64.b64encode(preview.read_bytes()).decode("ascii"), mimeType="image/png"
            )
        )
    return content
