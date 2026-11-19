"""Bounds check for a saved deck, run on the reopened file (independent of the builder).

Per slide it reports:
- ``out_of_bounds``: content shapes outside the 0.5" safe margin, or any shape off the slide;
- ``overflow``: text that needs more height than its box, measured with the render metrics;
- ``overlaps``: content shapes whose rectangles intersect.
Any finding fails validation, so a deck with clipped or colliding content is never delivered.
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.util import Emu

from .measure import LINE_SPACING, text_height_pt

SAFE = 0.5
TOLERANCE = 0.01  # inches
CONTENT_ROLES = {"title", "subtitle", "kicker", "bullets", "table", "chart", "key_message"}
DECORATION_ROLES = {"background", "accent", "logo", "footer-left", "footer-right"}


def _inches(value) -> float:
    return Emu(value).inches


def _rect(shape) -> tuple[float, float, float, float]:
    x, y = _inches(shape.left), _inches(shape.top)
    return x, y, x + _inches(shape.width), y + _inches(shape.height)


def _role(shape) -> str:
    return shape.name[4:] if shape.name.startswith("mtn:") else "unknown"


def _text_overflow(shape) -> float:
    """Inches by which the text exceeds its box (0 when it fits)."""
    frame = shape.text_frame
    width_pt = (
        _inches(shape.width) - _inches(frame.margin_left or 0) - _inches(frame.margin_right or 0)
    ) * 72
    needed = 0.0
    for paragraph in frame.paragraphs:
        runs = paragraph.runs
        if not runs:
            continue
        size = max((r.font.size.pt for r in runs if r.font.size), default=18)
        bold = any(r.font.bold for r in runs)
        indent = 0.0
        p_pr = paragraph._p.pPr
        if p_pr is not None and p_pr.get("marL"):
            indent = int(p_pr.get("marL")) / 12700
        text = "".join(r.text for r in runs)
        space_after = paragraph.space_after.pt if paragraph.space_after is not None else 0
        needed += text_height_pt(text, size, width_pt - indent, bold, space_after)
    available = (
        _inches(shape.height) - _inches(frame.margin_top or 0) - _inches(frame.margin_bottom or 0)
    ) * 72
    return max(0.0, (needed - available) / 72)


def _table_overflow(shape) -> float:
    table = shape.table
    needed = 0.0
    for row in table.rows:
        row_needed = 0.0
        for c, cell in enumerate(row.cells):
            width_pt = (_inches(table.columns[c].width) - 0.2) * 72
            for paragraph in cell.text_frame.paragraphs:
                runs = paragraph.runs
                size = max((r.font.size.pt for r in runs if r.font.size), default=12)
                text = "".join(r.text for r in runs)
                row_needed = max(row_needed, text_height_pt(text, size, width_pt, any(r.font.bold for r in runs)))
        needed += max(row_needed + 0.12 * 72, _inches(row.height) * 72)
    return max(0.0, needed / 72 - _inches(shape.height))


def check(path: Path) -> dict:
    prs = Presentation(path)
    slide_w, slide_h = _inches(prs.slide_width), _inches(prs.slide_height)
    report = {"slides": len(prs.slides), "shapes": 0, "issues": [], "per_slide": []}
    for number, slide in enumerate(prs.slides, start=1):
        entry = {"slide": number, "shapes": 0, "out_of_bounds": [], "overflow": [], "overlaps": []}
        content = []
        for shape in slide.shapes:
            entry["shapes"] += 1
            role = _role(shape)
            x0, y0, x1, y1 = _rect(shape)
            if x0 < -TOLERANCE or y0 < -TOLERANCE or x1 > slide_w + TOLERANCE or y1 > slide_h + TOLERANCE:
                entry["out_of_bounds"].append(f"{role} is off the slide")
            if role not in DECORATION_ROLES:
                if (
                    x0 < SAFE - TOLERANCE
                    or y0 < SAFE - 0.06 - TOLERANCE
                    or x1 > slide_w - SAFE + TOLERANCE
                    or y1 > slide_h - SAFE - 0.4 + TOLERANCE
                ):
                    entry["out_of_bounds"].append(f"{role} crosses the safe margin")
                content.append((role, (x0, y0, x1, y1)))
            if shape.has_text_frame and role in CONTENT_ROLES:
                over = _text_overflow(shape)
                if over > 0.02:
                    entry["overflow"].append(f"{role} text overflows by {over:.2f} in")
            if getattr(shape, "has_table", False) and shape.has_table:
                over = _table_overflow(shape)
                if over > 0.05:
                    entry["overflow"].append(f"table overflows by {over:.2f} in")
        for i in range(len(content)):
            for j in range(i + 1, len(content)):
                (ra, a), (rb, b) = content[i], content[j]
                if a[0] < b[2] - TOLERANCE and b[0] < a[2] - TOLERANCE and a[1] < b[3] - TOLERANCE and b[1] < a[3] - TOLERANCE:
                    entry["overlaps"].append(f"{ra} overlaps {rb}")
        report["shapes"] += entry["shapes"]
        for kind in ("out_of_bounds", "overflow", "overlaps"):
            report["issues"].extend(f"slide {number}: {issue}" for issue in entry[kind])
        report["per_slide"].append(entry)
    report["line_spacing"] = LINE_SPACING
    return report
