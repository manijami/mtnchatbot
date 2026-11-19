"""Builds the MTN Office templates (v0.1) and their manifests.

Run inside the office-mcp image, which has python-docx, python-pptx and openpyxl:

    docker run --rm -v "$PWD/mtn/templates:/out" -e PYTHONPATH=/app \
      mtn-office-mcp:test python /out/build_templates.py /out

Templates carry page setup, styles, theme fonts and colours only; content, header/footer text and
the logo are added at generation time. A new look ships as a new version folder (v0.2, ...); an
existing version is never rebuilt in place once documents reference it.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from lxml import etree
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, NamedStyle, PatternFill, Side
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.util import Inches

from office_mcp import brand

VERSION = "v0.1"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

WORD_TEMPLATES = {
    "proposal": {
        "title": "Proposal",
        "kicker": "PROPOSAL",
        "description": "Business or project proposal: problem, proposed solution, plan, costs, risks.",
        "cover_fields": ["Prepared for", "Prepared by", "Date", "Version"],
        "suggested_sections": [
            "Executive summary",
            "Background",
            "Proposed solution",
            "Implementation plan",
            "Costs and benefits",
            "Risks and mitigations",
            "Next steps",
        ],
    },
    "meeting_minutes": {
        "title": "Meeting minutes",
        "kicker": "MEETING MINUTES",
        "description": "Minutes of a meeting: attendees, agenda, discussion, decisions, actions.",
        "cover_fields": ["Date", "Time", "Location", "Chair", "Attendees", "Apologies"],
        "suggested_sections": ["Agenda", "Discussion", "Decisions", "Action items", "Next meeting"],
    },
    "incident_report": {
        "title": "Incident report",
        "kicker": "INCIDENT REPORT",
        "description": "IT or operational incident report or process: summary, timeline, impact, "
        "root cause, resolution, lessons learned.",
        "cover_fields": ["Incident ID", "Severity", "Status", "Date", "Owner"],
        "suggested_sections": [
            "Summary",
            "Timeline",
            "Impact",
            "Root cause",
            "Resolution",
            "Lessons learned",
            "Follow-up actions",
        ],
    },
}

POWERPOINT_TEMPLATES = {
    "executive_update": {
        "title": "Executive update",
        "description": "Short leadership update: headline messages, key metrics, decisions needed.",
        "suggested_slides": ["Title", "Summary", "Key metrics", "Progress", "Risks", "Decisions"],
    },
    "project_status": {
        "title": "Project status",
        "description": "Project status report: milestones, status by workstream, risks, next steps.",
        "suggested_slides": ["Title", "Overview", "Milestones", "Workstreams", "Risks", "Next steps"],
    },
}

EXCEL_TEMPLATES = {
    "action_tracker": {
        "title": "Action tracker",
        "description": "List of actions with owner, due date, status and priority; filters and a "
        "status summary chart.",
        "suggested_columns": ["ID", "Action", "Owner", "Due date", "Status", "Priority", "Notes"],
    },
    "project_plan": {
        "title": "Project plan",
        "description": "Tasks with start/end dates, duration formulas, owners, progress and a chart.",
        "suggested_columns": ["Task", "Owner", "Start", "End", "Duration (days)", "% complete"],
    },
}

FONT_INFO = {"primary": brand.FONT, "fallback": brand.FONT_FALLBACK, "embedded": False}
COLOURS = {"yellow": brand.YELLOW, "black": brand.BLACK, "ink": brand.INK, "tint": brand.TINT}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(folder: Path, data: dict) -> None:
    (folder / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")


# --------------------------------------------------------------------------------------------
# Word


def _set_run_font(style, size: float, bold: bool = False, colour: str = brand.INK) -> None:
    style.font.name = brand.FONT
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.italic = False
    style.font.color.rgb = RGBColor.from_string(colour)
    rpr = style.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), brand.FONT)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        fonts.attrib.pop(qn(attr), None)


def _bottom_border(style, colour: str, size_eighths: int) -> None:
    ppr = style.element.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size_eighths))
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), colour)
    borders.append(bottom)
    ppr.append(borders)


def _add_font_table_fallback(document) -> None:
    """Declares MTN Brighter Sans with altName Arial, so Word substitutes Arial when missing."""
    target = None
    for rel in document.part.rels.values():
        if rel.reltype.endswith("/fontTable"):
            target = rel.target_part
    if target is None:
        return
    root = etree.fromstring(target.blob)
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    font = etree.SubElement(root, f"{{{w}}}font", {f"{{{w}}}name": brand.FONT})
    etree.SubElement(font, f"{{{w}}}altName", {f"{{{w}}}val": brand.FONT_FALLBACK})
    etree.SubElement(font, f"{{{w}}}family", {f"{{{w}}}val": "swiss"})
    etree.SubElement(font, f"{{{w}}}pitch", {f"{{{w}}}val": "variable"})
    target._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _set_theme_fonts(theme_part) -> None:
    root = etree.fromstring(theme_part.blob)
    for tag in ("majorFont", "minorFont"):
        for latin in root.iter(f"{{{A_NS}}}{tag}"):
            node = latin.find(f"{{{A_NS}}}latin")
            if node is not None:
                node.set("typeface", brand.FONT)
    for name, value in (("accent1", brand.YELLOW), ("accent2", brand.BLACK), ("dk2", brand.INK)):
        for node in root.iter(f"{{{A_NS}}}{name}"):
            for child in list(node):
                node.remove(child)
            etree.SubElement(node, f"{{{A_NS}}}srgbClr", {"val": value})
    theme_part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def build_word(out: Path, name: str, meta: dict) -> None:
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(2.6), Cm(2.2)
    section.left_margin = section.right_margin = Cm(2.2)
    section.header_distance = section.footer_distance = Cm(1.0)

    styles = document.styles
    normal = styles["Normal"]
    _set_run_font(normal, 10.5)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15

    _set_run_font(styles["Title"], 26, bold=True, colour=brand.BLACK)
    styles["Title"].paragraph_format.space_after = Pt(4)
    title_ppr = styles["Title"].element.get_or_add_pPr()
    for border in title_ppr.findall(qn("w:pBdr")):
        title_ppr.remove(border)
    _set_run_font(styles["Subtitle"], 13, colour=brand.GREY)
    styles["Subtitle"].paragraph_format.space_after = Pt(14)

    for level, size, colour, before in ((1, 15, brand.BLACK, 16), (2, 12.5, brand.INK, 12), (3, 11, brand.GREY_DARK, 10)):
        heading = styles[f"Heading {level}"]
        _set_run_font(heading, size, bold=True, colour=colour)
        heading.paragraph_format.space_before = Pt(before)
        heading.paragraph_format.space_after = Pt(6)
        heading.paragraph_format.keep_with_next = True
    _bottom_border(styles["Heading 1"], brand.YELLOW, 12)

    for list_style in ("List Bullet", "List Number"):
        _set_run_font(styles[list_style], 10.5)
        styles[list_style].paragraph_format.space_after = Pt(3)

    kicker = styles.add_style("MTN Kicker", WD_STYLE_TYPE.PARAGRAPH)
    kicker.base_style = normal
    _set_run_font(kicker, 9, bold=True, colour=brand.GREY_DARK)
    kicker.paragraph_format.space_after = Pt(2)

    small = styles.add_style("MTN Small", WD_STYLE_TYPE.PARAGRAPH)
    small.base_style = normal
    _set_run_font(small, 8, colour=brand.GREY)
    small.paragraph_format.space_after = Pt(0)

    table_text = styles.add_style("MTN Table Text", WD_STYLE_TYPE.PARAGRAPH)
    table_text.base_style = normal
    _set_run_font(table_text, 9.5)
    table_text.paragraph_format.space_after = Pt(0)
    table_text.paragraph_format.line_spacing = 1.0

    _add_font_table_fallback(document)
    for rel in document.part.rels.values():
        if rel.reltype == RT.THEME:
            _set_theme_fonts(rel.target_part)

    props = document.core_properties
    props.author = "MTN Employee AI"
    props.title = meta["title"]
    props.comments = f"MTN template {name} {VERSION}"

    folder = out / "word" / name / VERSION
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "template.docx"
    document.save(path)
    _write_manifest(
        folder,
        {
            "kind": "word",
            "name": name,
            "version": VERSION,
            "file": "template.docx",
            "sha256": _sha256(path),
            "page": {"size": "A4", "margins_cm": {"top": 2.6, "bottom": 2.2, "left": 2.2, "right": 2.2}},
            "font": FONT_INFO,
            "colours": COLOURS,
            "classification": brand.CLASSIFICATION,
            "logo": {"placement": "header-right", "height_cm": 1.4},
            **meta,
        },
    )


# --------------------------------------------------------------------------------------------
# PowerPoint


def build_powerpoint(out: Path, name: str, meta: dict) -> None:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    _set_theme_fonts(prs.slide_master.part.part_related_by(RT.THEME))
    prs.core_properties.author = "MTN Employee AI"
    prs.core_properties.title = meta["title"]
    prs.core_properties.comments = f"MTN template {name} {VERSION}"

    folder = out / "powerpoint" / name / VERSION
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "template.pptx"
    prs.save(path)
    _write_manifest(
        folder,
        {
            "kind": "powerpoint",
            "name": name,
            "version": VERSION,
            "file": "template.pptx",
            "sha256": _sha256(path),
            "slide": {"width_in": 13.333, "height_in": 7.5, "safe_margin_in": 0.5},
            "font": FONT_INFO,
            "colours": COLOURS,
            "classification": brand.CLASSIFICATION,
            "logo": {"placement": "top-right", "height_in": 0.6},
            "limits": {"max_slides": 20, "max_bullets": 6, "max_bullet_chars": 160},
            **meta,
        },
    )


# --------------------------------------------------------------------------------------------
# Excel


def build_excel(out: Path, name: str, meta: dict) -> None:
    workbook = Workbook()
    thin = Side(style="thin", color=brand.GREY_LIGHT)
    styles = [
        NamedStyle(name="MTN Title", font=Font(name=brand.FONT, size=16, bold=True, color=brand.BLACK)),
        NamedStyle(name="MTN Subtitle", font=Font(name=brand.FONT, size=10, color=brand.GREY)),
        NamedStyle(
            name="MTN Header",
            font=Font(name=brand.FONT, size=10, bold=True, color=brand.BLACK),
            fill=PatternFill("solid", fgColor=brand.YELLOW),
            alignment=Alignment(vertical="center", wrap_text=True),
            border=Border(bottom=Side(style="medium", color=brand.BLACK)),
        ),
        NamedStyle(
            name="MTN Cell",
            font=Font(name=brand.FONT, size=10, color=brand.INK),
            alignment=Alignment(vertical="top", wrap_text=True),
            border=Border(bottom=thin),
        ),
        NamedStyle(
            name="MTN Total",
            font=Font(name=brand.FONT, size=10, bold=True, color=brand.BLACK),
            border=Border(top=Side(style="thin", color=brand.BLACK)),
        ),
    ]
    for style in styles:
        workbook.add_named_style(copy.copy(style))
    sheet = workbook.active
    sheet.title = "Sheet1"
    workbook.properties.creator = "MTN Employee AI"
    workbook.properties.title = meta["title"]
    workbook.properties.description = f"MTN template {name} {VERSION}"

    folder = out / "excel" / name / VERSION
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "template.xlsx"
    workbook.save(path)
    _write_manifest(
        folder,
        {
            "kind": "excel",
            "name": name,
            "version": VERSION,
            "file": "template.xlsx",
            "sha256": _sha256(path),
            "font": FONT_INFO,
            "colours": COLOURS,
            "classification": brand.CLASSIFICATION,
            "named_styles": [s.name for s in styles],
            "limits": {"max_sheets": 6, "max_rows": 2000, "max_columns": 30},
            **meta,
        },
    )


def main(out: Path) -> None:
    for name, meta in WORD_TEMPLATES.items():
        build_word(out, name, meta)
    for name, meta in POWERPOINT_TEMPLATES.items():
        build_powerpoint(out, name, meta)
    for name, meta in EXCEL_TEMPLATES.items():
        build_excel(out, name, meta)
    print(f"Built {len(WORD_TEMPLATES) + len(POWERPOINT_TEMPLATES) + len(EXCEL_TEMPLATES)} templates ({VERSION}) in {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent))
