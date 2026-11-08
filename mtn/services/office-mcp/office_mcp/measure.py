"""Text measurement with the metrics LibreOffice renders with.

"MTN Brighter Sans" falls back to Arial-metric Liberation Sans in the container (fontconfig alias),
so wrapping is measured with Liberation Sans. Office on a machine that has the MTN font installed
renders with slightly different metrics, so fits keep a safety margin (``SAFETY``).
"""

from __future__ import annotations

from functools import lru_cache

from PIL import ImageFont

FONT_DIR = "/usr/share/fonts/truetype/liberation"
SCALE = 10  # measure at 10 px per point for sub-point precision
LINE_SPACING = 1.2
SAFETY = 0.92  # use 92% of the box width/height when deciding a fit


@lru_cache(maxsize=64)
def _font(size_pt: float, bold: bool):
    name = "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"
    return ImageFont.truetype(f"{FONT_DIR}/{name}", size=max(1, int(round(size_pt * SCALE))))


def text_width_pt(text: str, size_pt: float, bold: bool = False) -> float:
    return _font(size_pt, bold).getlength(text) / SCALE


def wrap_lines(text: str, size_pt: float, width_pt: float, bold: bool = False) -> int:
    """Number of lines greedy word-wrapping needs; a word wider than the line breaks across lines."""
    if width_pt <= 0:
        return 10**6
    lines = 0
    for paragraph in (text or "").split("\n"):
        words = paragraph.split()
        if not words:
            lines += 1
            continue
        current = 0.0
        lines += 1
        space = text_width_pt(" ", size_pt, bold)
        for word in words:
            w = text_width_pt(word, size_pt, bold)
            if w > width_pt:  # long token: hard-wrapped
                extra = int(w // width_pt)
                lines += extra if current == 0 else extra + 1
                current = w - extra * width_pt
                continue
            needed = w if current == 0 else current + space + w
            if needed <= width_pt:
                current = needed
            else:
                lines += 1
                current = w
    return lines


def text_height_pt(text: str, size_pt: float, width_pt: float, bold: bool = False, space_after_pt: float = 0) -> float:
    return wrap_lines(text, size_pt, width_pt, bold) * size_pt * LINE_SPACING + space_after_pt
