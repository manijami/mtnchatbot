"""Builds a Word document from a validated :class:`WordDocumentSpec` and a template."""

from __future__ import annotations

import io
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from . import brand
from .schemas import WordDocumentSpec
from .templates import Template

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_STRAY_MARKUP = re.compile(r"(^#{1,6}\s+)|(`)|(^\s*[-*]\s+)")


def _runs(paragraph, text: str) -> None:
    """Adds text, turning **bold** spans into bold runs and dropping stray Markdown."""
    text = _STRAY_MARKUP.sub("", text)
    position = 0
    for match in _BOLD.finditer(text):
        if match.start() > position:
            paragraph.add_run(text[position : match.start()])
        paragraph.add_run(match.group(1)).bold = True
        position = match.end()
    if position < len(text):
        paragraph.add_run(text[position:])


def _shade(cell, colour: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), colour)
    tc_pr.append(shading)


def _table_borders(table, colour: str = brand.GREY_LIGHT) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "4")
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), colour)
        borders.append(node)
    tbl_pr.append(borders)


def _cell_margins(table, vertical_twips: int = 50, horizontal_twips: int = 100) -> None:
    margins = OxmlElement("w:tblCellMar")
    for edge, value in (("top", vertical_twips), ("bottom", vertical_twips), ("left", horizontal_twips), ("right", horizontal_twips)):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        margins.append(node)
    table._tbl.tblPr.append(margins)


def _keep_row_together(row) -> None:
    row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))


def _repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def _field(paragraph, instruction: str) -> None:
    """Inserts a Word field (PAGE, NUMPAGES) that Word and LibreOffice compute on open."""
    for kind, text in (("begin", None), (None, instruction), ("separate", None), (None, "1"), ("end", None)):
        run = paragraph.add_run()
        if kind:
            char = OxmlElement("w:fldChar")
            char.set(qn("w:fldCharType"), kind)
            run._r.append(char)
        elif text == instruction:
            instr = OxmlElement("w:instrText")
            instr.set(qn("xml:space"), "preserve")
            instr.text = f" {instruction} "
            run._r.append(instr)
        else:
            run.text = text


def _new_numbering(document) -> int | None:
    """A fresh numbering instance of the List Number style, so each list restarts at 1."""
    try:
        style_num = document.styles["List Number"].element.pPr.numPr.numId.val
        numbering = document.part.numbering_part.numbering_definitions._numbering
        abstract_id = numbering.num_having_numId(style_num).abstractNumId.val
        num = numbering.add_num(abstract_id)
        num.add_lvlOverride(ilvl=0).add_startOverride(1)
        return num.numId
    except (AttributeError, KeyError):
        return None


def _set_numbering(paragraph, num_id: int | None) -> None:
    if num_id is None:
        return
    num_pr = paragraph._p.get_or_add_pPr().get_or_add_numPr()
    num_pr.get_or_add_ilvl().val = 0
    num_pr.get_or_add_numId().val = num_id


def _content_width_cm(document) -> float:
    section = document.sections[0]
    return (section.page_width - section.left_margin - section.right_margin) / 360000


def _header_footer(document, spec: WordDocumentSpec, logo: bytes | None) -> None:
    width = _content_width_cm(document)
    section = document.sections[0]

    header = section.header.paragraphs[0]
    header.style = document.styles["MTN Small"]
    header.paragraph_format.tab_stops.add_tab_stop(Cm(width), WD_TAB_ALIGNMENT.RIGHT)
    header.add_run(brand.CLASSIFICATION.upper())
    if logo:
        header.add_run("\t").add_picture(io.BytesIO(logo), height=Cm(1.4))

    footer = section.footer.paragraphs[0]
    footer.style = document.styles["MTN Small"]
    footer.paragraph_format.tab_stops.add_tab_stop(Cm(width), WD_TAB_ALIGNMENT.RIGHT)
    footer.add_run(spec.title[:90])
    footer.add_run("\tPage ")
    _field(footer, "PAGE")
    footer.add_run(" of ")
    _field(footer, "NUMPAGES")


def _add_table(document, columns: list[str], rows: list[list[str]], label_column: bool = False):
    width = _content_width_cm(document)
    table = document.add_table(rows=0, cols=len(columns))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _table_borders(table)
    _cell_margins(table)
    col_width = Cm(width / len(columns))
    if columns:
        cells = table.add_row().cells
        _repeat_header(table.rows[0])
        for cell, text in zip(cells, columns):
            cell.width = col_width
            _shade(cell, brand.YELLOW)
            paragraph = cell.paragraphs[0]
            paragraph.style = document.styles["MTN Table Text"]
            run = paragraph.add_run(text)
            run.bold = True
            run.font.color.rgb = RGBColor.from_string(brand.BLACK)
    for index, row in enumerate(rows):
        added = table.add_row()
        _keep_row_together(added)
        cells = added.cells
        for col, (cell, text) in enumerate(zip(cells, row)):
            cell.width = col_width
            if index % 2 == 1:
                _shade(cell, brand.TINT)
            paragraph = cell.paragraphs[0]
            paragraph.style = document.styles["MTN Table Text"]
            _runs(paragraph, text)
            if label_column and col == 0:
                for run in paragraph.runs:
                    run.bold = True
    return table


def _cover_table(document, fields) -> None:
    width = _content_width_cm(document)
    table = document.add_table(rows=0, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _table_borders(table)
    _cell_margins(table)
    for field in fields:
        label, value = table.add_row().cells
        label.width, value.width = Cm(width * 0.3), Cm(width * 0.7)
        _shade(label, brand.TINT)
        for cell, text, bold in ((label, field.label, True), (value, field.value, False)):
            paragraph = cell.paragraphs[0]
            paragraph.style = document.styles["MTN Table Text"]
            run = paragraph.add_run(text)
            run.bold = bold
    document.add_paragraph()


# Compact layouts used to meet target_pages without dropping content (level -> settings).
COMPACT = {
    1: {"body": 10.0, "after": 4, "line": 1.1, "title": 22, "h": (13.5, 11.5, 10.5), "before": (10, 8, 6), "margin": None},
    2: {"body": 9.5, "after": 3, "line": 1.0, "title": 20, "h": (12.5, 11, 10), "before": (8, 6, 5), "margin": 1.8},
}


def _compact(document, level: int) -> None:
    settings = COMPACT[level]
    styles = document.styles
    styles["Normal"].font.size = Pt(settings["body"])
    styles["Normal"].paragraph_format.space_after = Pt(settings["after"])
    styles["Normal"].paragraph_format.line_spacing = settings["line"]
    for name in ("List Bullet", "List Number"):
        styles[name].font.size = Pt(settings["body"])
        styles[name].paragraph_format.space_after = Pt(max(1, settings["after"] - 2))
    styles["Title"].font.size = Pt(settings["title"])
    styles["Subtitle"].paragraph_format.space_after = Pt(8)
    for level_index, size in enumerate(settings["h"], start=1):
        heading = styles[f"Heading {level_index}"]
        heading.font.size = Pt(size)
        heading.paragraph_format.space_before = Pt(settings["before"][level_index - 1])
        heading.paragraph_format.space_after = Pt(3)
    if settings["margin"]:
        section = document.sections[0]
        section.left_margin = section.right_margin = Cm(settings["margin"])
        section.top_margin, section.bottom_margin = Cm(2.2), Cm(1.8)


def build(spec: WordDocumentSpec, template: Template, target: Path, logo: bytes | None, compact: int = 0) -> dict:
    document = Document(template.path)
    if compact:
        _compact(document, compact)
    _header_footer(document, spec, logo)

    kicker = template.manifest.get("kicker")
    if kicker:
        document.add_paragraph(kicker, style="MTN Kicker")
    document.add_paragraph(spec.title, style="Title")
    if spec.subtitle:
        document.add_paragraph(spec.subtitle, style="Subtitle")
    if spec.cover_fields:
        _cover_table(document, spec.cover_fields)

    stats = {"sections": len(spec.sections), "tables": 0, "words": 0}
    for section in spec.sections:
        document.add_heading(section.heading, level=section.level)
        for text in section.paragraphs:
            _runs(document.add_paragraph(), text)
            stats["words"] += len(text.split())
        for text in section.bullets:
            _runs(document.add_paragraph(style="List Bullet"), text)
            stats["words"] += len(text.split())
        num_id = _new_numbering(document) if section.numbered else None
        for text in section.numbered:
            paragraph = document.add_paragraph(style="List Number")
            _set_numbering(paragraph, num_id)
            _runs(paragraph, text)
            stats["words"] += len(text.split())
        if section.table:
            _add_table(document, section.table.columns, section.table.rows)
            stats["tables"] += 1
            if section.table.caption:
                document.add_paragraph(section.table.caption, style="MTN Small")
            else:
                document.add_paragraph()

    props = document.core_properties
    props.title = spec.title
    props.subject = template.title
    props.author = "MTN Employee AI"
    props.comments = f"Generated from MTN template {template.name} {template.version}"
    document.save(target)
    return stats


def reopen(path: Path) -> dict:
    """Reopens the saved file with python-docx and reports what it found."""
    document = Document(path)
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    if not headings:
        raise ValueError("the document has no headings after reopening")
    return {"paragraphs": len(document.paragraphs), "tables": len(document.tables), "headings": len(headings)}
