"""Builds an MTN 16:9 deck from a validated :class:`PresentationSpec`.

Every shape is placed on a fixed grid and named ``mtn:<role>``; text is fitted before it is placed
(font sizes step down until the measured text fits), so content that cannot fit is rejected with a
fixable message instead of overflowing. :mod:`office_mcp.bounds` re-checks the saved file.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from . import brand
from .measure import SAFETY, text_height_pt
from .schemas import PresentationSpec, SlideSpec
from .templates import Template

SLIDE_W, SLIDE_H = 13.333, 7.5
MARGIN = 0.5
CONTENT_W = SLIDE_W - 2 * MARGIN
TITLE_Y, TITLE_H = 0.45, 0.95  # two lines at 22 pt: a 90-character title must fit
CONTENT_TOP = 1.65
CONTENT_BOTTOM = 6.55
KEY_H = 0.6
GAP = 0.4
TEXT_INSET = 0.1  # inches, left/right internal margin on every text box
BULLET_INDENT_PT = 18

BULLET_SIZES = (20, 18, 16, 14)
TABLE_SIZES = (14, 12, 11, 10)
TITLE_SIZES = (28, 24, 22, 20)
CHART_COLOURS = (brand.YELLOW, brand.BLACK, "808080", "C9A400")
CHART_TYPES = {
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
    "pie": XL_CHART_TYPE.PIE,
}


class FitError(ValueError):
    """Content that does not fit its area; the message tells the model what to change."""


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float


def _rgb(hex_colour: str) -> RGBColor:
    return RGBColor.from_string(hex_colour)


def _name(shape, role: str) -> None:
    shape.name = f"mtn:{role}"


def _fill(shape, colour: str) -> None:
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(colour)
    shape.line.fill.background()
    shape.shadow.inherit = False  # no theme drop shadow on brand blocks
    style = shape._element.find(qn("p:style"))
    if style is not None:  # drop the theme style reference (effects); colours are explicit
        shape._element.remove(style)


def _rect(slide, box: Box, colour: str, role: str):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(box.x), Inches(box.y), Inches(box.w), Inches(box.h))
    _fill(shape, colour)
    _name(shape, role)
    return shape


def _textbox(slide, box: Box, role: str):
    shape = slide.shapes.add_textbox(Inches(box.x), Inches(box.y), Inches(box.w), Inches(box.h))
    _name(shape, role)
    frame = shape.text_frame
    frame.word_wrap = True
    frame.auto_size = None
    frame.margin_left = frame.margin_right = Inches(TEXT_INSET)
    frame.margin_top = frame.margin_bottom = Inches(0.05)
    return shape, frame


def _run(paragraph, text: str, size: float, colour: str = brand.INK, bold: bool = False):
    run = paragraph.add_run()
    run.text = text
    run.font.name = brand.FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = _rgb(colour)
    return run


def _inner_width_pt(box: Box, indent_pt: float = 0) -> float:
    return ((box.w - 2 * TEXT_INSET) * 72 - indent_pt) * SAFETY


def _inner_height_pt(box: Box) -> float:
    return (box.h - 0.1) * 72 * SAFETY


def _fit_lines(texts: list[str], box: Box, sizes, bold=False, indent_pt=0.0, gap_ratio=0.45) -> float | None:
    for size in sizes:
        height = sum(
            text_height_pt(t, size, _inner_width_pt(box, indent_pt), bold, size * gap_ratio) for t in texts
        )
        if height <= _inner_height_pt(box):
            return size
    return None


def _set_bullet(paragraph, size: float) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_pr.set("marL", str(Pt(BULLET_INDENT_PT)))
    p_pr.set("indent", str(-Pt(BULLET_INDENT_PT)))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        for node in p_pr.findall(qn(tag)):
            p_pr.remove(node)
    colour = p_pr.makeelement(qn("a:buClr"), {})
    srgb = colour.makeelement(qn("a:srgbClr"), {"val": brand.BLACK})
    colour.append(srgb)
    p_pr.append(colour)
    p_pr.append(p_pr.makeelement(qn("a:buFont"), {"typeface": "Arial"}))
    p_pr.append(p_pr.makeelement(qn("a:buChar"), {"char": "•"}))
    paragraph.space_after = Pt(size * 0.45)


# --------------------------------------------------------------------------------------------
# Slide furniture


def _logo(slide, logo: bytes | None, on_dark: bool = False) -> None:
    if not logo:
        return
    size = 0.6
    picture = slide.shapes.add_picture(
        io.BytesIO(logo), Inches(SLIDE_W - MARGIN - size), Inches(TITLE_Y), Inches(size), Inches(size)
    )
    _name(picture, "logo")


def _footer(slide, number: int, total: int, on_dark: bool = False) -> None:
    colour = brand.GREY_LIGHT if on_dark else brand.GREY
    _, frame = _textbox(slide, Box(MARGIN, 6.95, 6.0, 0.3), "footer-left")
    _run(frame.paragraphs[0], brand.CLASSIFICATION, 10, colour)
    _, frame = _textbox(slide, Box(SLIDE_W - MARGIN - 2.0, 6.95, 2.0, 0.3), "footer-right")
    frame.paragraphs[0].alignment = PP_ALIGN.RIGHT
    _run(frame.paragraphs[0], f"{number} / {total}", 10, colour)


def _title_slide(prs, spec: PresentationSpec, template: Template, logo, total: int) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(slide, Box(0, 0, SLIDE_W, SLIDE_H), brand.BLACK, "background")
    _logo(slide, logo, on_dark=True)
    kicker_box = Box(MARGIN, 2.2, CONTENT_W - 1.0, 0.4)
    _, frame = _textbox(slide, kicker_box, "kicker")
    _run(frame.paragraphs[0], template.title.upper(), 14, brand.YELLOW, bold=True)
    title_box = Box(MARGIN, 2.65, CONTENT_W - 1.0, 1.9)
    size = _fit_lines([spec.title], title_box, (44, 40, 36, 32), bold=True, gap_ratio=0)
    if size is None:
        raise FitError("title: the deck title is too long for the title slide; shorten it")
    _, frame = _textbox(slide, title_box, "title")
    frame.vertical_anchor = MSO_ANCHOR.BOTTOM
    _run(frame.paragraphs[0], spec.title, size, brand.WHITE, bold=True)
    _rect(slide, Box(MARGIN + TEXT_INSET, 4.7, 1.4, 0.09), brand.YELLOW, "accent")
    if spec.subtitle:
        sub_box = Box(MARGIN, 4.95, CONTENT_W - 1.0, 1.0)
        sub_size = _fit_lines([spec.subtitle], sub_box, (22, 20, 18), gap_ratio=0)
        if sub_size is None:
            raise FitError("subtitle: too long for the title slide; shorten it")
        _, frame = _textbox(slide, sub_box, "subtitle")
        _run(frame.paragraphs[0], spec.subtitle, sub_size, brand.GREY_LIGHT)
    _footer(slide, 1, total, on_dark=True)


# --------------------------------------------------------------------------------------------
# Content


def _bullets(slide, box: Box, bullets: list[str], index: int) -> None:
    size = _fit_lines(bullets, box, BULLET_SIZES, indent_pt=BULLET_INDENT_PT)
    if size is None:
        words = sum(len(b.split()) for b in bullets)
        raise FitError(
            f"slides[{index}].bullets: {len(bullets)} bullets ({words} words) do not fit even at "
            f"{BULLET_SIZES[-1]} pt; shorten them to about {int(words * 0.6)} words or split the slide"
        )
    _, frame = _textbox(slide, box, "bullets")
    for i, text in enumerate(bullets):
        paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        _set_bullet(paragraph, size)
        _run(paragraph, text, size)


def _table(slide, box: Box, table_spec, index: int) -> None:
    columns, rows = table_spec.columns, table_spec.rows
    weights = [
        max(len(columns[c]), *(len(r[c]) for r in rows), 6) ** 0.8 for c in range(len(columns))
    ]
    total = sum(weights)
    widths = [box.w * w / total for w in weights]
    chosen, heights = None, []
    for size in TABLE_SIZES:
        heights = []
        for r, row in enumerate([columns, *rows]):
            row_h = max(
                text_height_pt(text, size, ((widths[c] - 0.2) * 72) * SAFETY, bold=(r == 0))
                for c, text in enumerate(row)
            ) + 0.12 * 72
            heights.append(row_h)
        if sum(heights) <= box.h * 72 * SAFETY:
            chosen = size
            break
    if chosen is None:
        raise FitError(
            f"slides[{index}].table: {len(rows)} rows do not fit even at {TABLE_SIZES[-1]} pt; "
            "use fewer rows, shorter cell text, or split the table over two slides"
        )
    frame = slide.shapes.add_table(
        len(rows) + 1, len(columns), Inches(box.x), Inches(box.y), Inches(box.w), Pt(sum(heights))
    )
    _name(frame, "table")
    table = frame.table
    table.first_row = True
    for c, width in enumerate(widths):
        table.columns[c].width = Inches(width)
    for r, row in enumerate([columns, *rows]):
        table.rows[r].height = Pt(heights[r])
        for c, text in enumerate(row):
            cell = table.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.margin_top = cell.margin_bottom = Inches(0.06)
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(brand.YELLOW if r == 0 else (brand.TINT if r % 2 == 0 else brand.WHITE))
            paragraph = cell.text_frame.paragraphs[0]
            cell.text_frame.word_wrap = True
            _run(paragraph, text, chosen, brand.BLACK if r == 0 else brand.INK, bold=(r == 0))


def _chart(slide, box: Box, chart_spec) -> None:
    data = CategoryChartData()
    data.categories = chart_spec.categories
    for series in chart_spec.series:
        data.add_series(series.name, series.values)
    frame = slide.shapes.add_chart(
        CHART_TYPES[chart_spec.type], Inches(box.x), Inches(box.y), Inches(box.w), Inches(box.h), data
    )
    _name(frame, "chart")
    chart = frame.chart
    chart.font.name = brand.FONT
    chart.font.size = Pt(12)
    chart.font.color.rgb = _rgb(brand.INK)
    if chart_spec.title:
        chart.has_title = True
        chart.chart_title.text_frame.text = chart_spec.title
        chart.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
        chart.chart_title.text_frame.paragraphs[0].runs[0].font.bold = True
    else:
        chart.has_title = False
    plot = chart.plots[0]
    if chart_spec.type == "pie":
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.RIGHT
        chart.legend.include_in_layout = False
        plot.has_data_labels = True
        plot.data_labels.number_format = "0%"
        plot.data_labels.show_percentage = True
        plot.data_labels.show_value = False
        # Outside the slices: a label inside the black slice would be black on black.
        plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
        plot.data_labels.font.size = Pt(12)
        plot.data_labels.font.color.rgb = _rgb(brand.INK)
        palette = (*CHART_COLOURS, "B3B3B3", "FFE680", "595959", "E6B800")
        for i, point in enumerate(plot.series[0].points):
            point.format.fill.solid()
            point.format.fill.fore_color.rgb = _rgb(palette[i % len(palette)])
        return
    chart.has_legend = len(chart_spec.series) > 1
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
    if chart_spec.type in ("bar", "column"):
        plot.gap_width = 80
    for i, series in enumerate(plot.series):
        colour = _rgb(CHART_COLOURS[i % len(CHART_COLOURS)])
        if chart_spec.type == "line":
            series.format.line.color.rgb = colour
            series.format.line.width = Pt(2.5)
            series.smooth = False
        else:
            series.format.fill.solid()
            series.format.fill.fore_color.rgb = colour
    value_axis = chart.value_axis
    value_axis.has_major_gridlines = True
    value_axis.major_gridlines.format.line.color.rgb = _rgb(brand.GREY_LIGHT)
    value_axis.format.line.fill.background()


def _content_slide(prs, slide_spec: SlideSpec, index: int, number: int, total: int, logo) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _logo(slide, logo)
    title_box = Box(MARGIN, TITLE_Y, CONTENT_W - 0.9, TITLE_H)
    size = _fit_lines([slide_spec.title], title_box, TITLE_SIZES, bold=True, gap_ratio=0)
    if size is None:
        raise FitError(f"slides[{index}].title: too long for the slide title area; shorten it")
    _, frame = _textbox(slide, title_box, "title")
    frame.vertical_anchor = MSO_ANCHOR.BOTTOM
    _run(frame.paragraphs[0], slide_spec.title, size, brand.BLACK, bold=True)
    _rect(slide, Box(MARGIN + TEXT_INSET, TITLE_Y + TITLE_H + 0.05, 1.0, 0.07), brand.YELLOW, "accent")

    bottom = CONTENT_BOTTOM - (KEY_H + 0.2 if slide_spec.key_message else 0)
    area = Box(MARGIN, CONTENT_TOP, CONTENT_W, bottom - CONTENT_TOP)
    visual = slide_spec.table or slide_spec.chart
    if slide_spec.bullets and visual:
        left_w = (CONTENT_W - GAP) * (0.42 if slide_spec.chart else 0.38)
        text_box = Box(area.x, area.y, left_w, area.h)
        visual_box = Box(area.x + left_w + GAP, area.y, CONTENT_W - left_w - GAP, area.h)
    else:
        text_box = visual_box = area
    if slide_spec.bullets:
        _bullets(slide, text_box, slide_spec.bullets, index)
    if slide_spec.table:
        _table(slide, visual_box, slide_spec.table, index)
    if slide_spec.chart:
        _chart(slide, visual_box, slide_spec.chart)
    if slide_spec.key_message:
        key_box = Box(MARGIN, CONTENT_BOTTOM - KEY_H, CONTENT_W, KEY_H)
        key_size = _fit_lines([slide_spec.key_message], key_box, (18, 16, 14), bold=True, gap_ratio=0)
        if key_size is None:
            raise FitError(f"slides[{index}].key_message: too long for one line; shorten it")
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(key_box.x), Inches(key_box.y), Inches(key_box.w), Inches(key_box.h)
        )
        _fill(shape, brand.TINT)
        _name(shape, "key_message")
        frame = shape.text_frame
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = Inches(TEXT_INSET)
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        _run(frame.paragraphs[0], slide_spec.key_message, key_size, brand.BLACK, bold=True)
    if slide_spec.notes:
        slide.notes_slide.notes_text_frame.text = slide_spec.notes
    _footer(slide, number, total)


def build(spec: PresentationSpec, template: Template, target: Path, logo: bytes | None) -> dict:
    prs = Presentation(template.path)
    total = len(spec.slides) + (1 if spec.include_title_slide else 0)
    number = 1
    if spec.include_title_slide:
        _title_slide(prs, spec, template, logo, total)
        number += 1
    for index, slide_spec in enumerate(spec.slides):
        _content_slide(prs, slide_spec, index, number, total, logo)
        number += 1
    props = prs.core_properties
    props.title = spec.title
    props.subject = template.title
    props.author = "MTN Employee AI"
    props.comments = f"Generated from MTN template {template.name} {template.version}"
    prs.save(target)
    return {
        "slides": total,
        "charts": sum(1 for s in spec.slides if s.chart),
        "tables": sum(1 for s in spec.slides if s.table),
        "notes": sum(1 for s in spec.slides if s.notes),
    }


def emu_to_in(value) -> float:
    return Emu(value).inches
