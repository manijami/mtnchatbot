"""Headless LibreOffice rendering: PDF conversion, page count, preview PNG.

One conversion runs at a time (a process-wide lock) with a hard timeout; on timeout the whole
LibreOffice process group is killed and its profile discarded. LibreOffice opening the file is
also the "opens cleanly in an office suite" check.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import tempfile
from pathlib import Path

PROFILE_DIR = Path(tempfile.gettempdir()) / "lo-profile"
PREVIEW_DPI = 80
PREVIEW_MAX_PAGES = 4

_lock = asyncio.Lock()


class RenderError(Exception):
    pass


async def _run(args: list[str], timeout: float, cwd: Path | None = None) -> tuple[int, bytes]:
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
        raise
    return process.returncode, output


async def convert(source: Path, target_ext: str, out_dir: Path, timeout: float) -> Path:
    """Converts ``source`` with LibreOffice (e.g. to ``pdf`` or ``xlsx``) into ``out_dir``."""
    async with _lock:
        with tempfile.TemporaryDirectory(prefix="lo-out-") as work:
            args = [
                "soffice",
                "--headless",
                "--invisible",
                "--nologo",
                "--norestore",
                "--nodefault",
                "--nolockcheck",
                f"-env:UserInstallation=file://{PROFILE_DIR}",
                "--convert-to",
                target_ext,
                "--outdir",
                work,
                str(source),
            ]
            try:
                code, output = await _run(args, timeout)
            except asyncio.TimeoutError:
                shutil.rmtree(PROFILE_DIR, ignore_errors=True)
                raise RenderError(f"LibreOffice did not finish within {int(timeout)} seconds") from None
            produced = Path(work) / f"{source.stem}.{target_ext.split(':')[0]}"
            if code != 0 or not produced.is_file() or produced.stat().st_size == 0:
                shutil.rmtree(PROFILE_DIR, ignore_errors=True)
                tail = output.decode(errors="replace").strip()[-300:]
                raise RenderError(f"LibreOffice could not open the file ({tail or f'exit {code}'})")
            out_dir.mkdir(parents=True, exist_ok=True)
            final = out_dir / produced.name
            shutil.move(str(produced), final)
            return final


async def pdf_pages(pdf: Path) -> int:
    code, output = await _run(["pdfinfo", str(pdf)], timeout=20)
    if code != 0:
        raise RenderError("the rendered PDF could not be read")
    for line in output.decode(errors="replace").splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1])
    raise RenderError("the rendered PDF has no page count")


async def preview_png(
    pdf: Path,
    target: Path,
    pages: int,
    dpi: int = PREVIEW_DPI,
    max_pages: int = PREVIEW_MAX_PAGES,
    columns: int | None = None,
) -> Path:
    """Renders the first pages as one contact-sheet PNG (a single row unless ``columns`` is set)."""
    from PIL import Image, ImageOps

    count = max(1, min(pages, max_pages))
    columns = columns or count
    with tempfile.TemporaryDirectory(prefix="preview-") as work:
        prefix = Path(work) / "p"
        code, _ = await _run(
            ["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", str(count), str(pdf), str(prefix)],
            timeout=60,
        )
        images = sorted(Path(work).glob("p*.png"))
        if code != 0 or not images:
            raise RenderError("the preview image could not be rendered")
        frames = [ImageOps.expand(Image.open(p).convert("RGB"), border=1, fill="#BFBFBF") for p in images]
        gap = 16
        cell_w = max(f.width for f in frames)
        cell_h = max(f.height for f in frames)
        rows = -(-len(frames) // columns)
        used_cols = min(columns, len(frames))
        sheet = Image.new(
            "RGB", (used_cols * cell_w + gap * (used_cols + 1), rows * cell_h + gap * (rows + 1)), "#F2F2F2"
        )
        for i, frame in enumerate(frames):
            r, c = divmod(i, columns)
            sheet.paste(frame, (gap + c * (cell_w + gap), gap + r * (cell_h + gap)))
        sheet.save(target, format="PNG", optimize=True)
        for frame in frames:
            frame.close()
    return target


async def pdf_text_lines(pdf: Path, first: int, last: int) -> int:
    """Non-empty text lines on pages first..last (layout mode), to size an overflow."""
    code, output = await _run(
        ["pdftotext", "-layout", "-f", str(first), "-l", str(last), str(pdf), "-"], timeout=20
    )
    if code != 0:
        return 0
    return sum(1 for line in output.decode(errors="replace").splitlines() if line.strip())
