import shutil
import zipfile

import pytest
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

from office_mcp import brand, templates

from .conftest import TEMPLATES

EXPECTED = {
    "word": {"proposal", "meeting_minutes", "incident_report"},
    "powerpoint": {"executive_update", "project_status"},
    "excel": {"action_tracker", "project_plan"},
}


@pytest.mark.parametrize("kind", templates.KINDS)
def test_catalogue_lists_every_template(kind):
    assert set(templates.available(TEMPLATES, kind)) == EXPECTED[kind]


@pytest.mark.parametrize("kind,name", [(k, n) for k, names in EXPECTED.items() for n in names])
def test_every_template_loads_and_passes_integrity(kind, name):
    template = templates.load(TEMPLATES, kind, name)
    assert template.version == "v0.1"
    assert template.manifest["font"] == {"primary": brand.FONT, "fallback": "Arial", "embedded": False}


def test_unknown_template_and_version_are_refused():
    with pytest.raises(templates.TemplateError):
        templates.load(TEMPLATES, "word", "nope")
    with pytest.raises(templates.TemplateError):
        templates.load(TEMPLATES, "word", "proposal", "v9.9")
    with pytest.raises(templates.TemplateError):
        templates.load(TEMPLATES, "visio", "proposal")


def test_tampered_template_is_refused(tmp_path):
    root = tmp_path / "t"
    shutil.copytree(TEMPLATES / "word", root / "word")
    (root / "word" / "proposal" / "v0.1" / "template.docx").write_bytes(b"PK tampered")
    with pytest.raises(templates.TemplateError, match="integrity"):
        templates.load(root, "word", "proposal")


def test_word_template_styles_name_mtn_font_with_arial_fallback():
    path = templates.load(TEMPLATES, "word", "incident_report").path
    document = Document(path)
    for style in ("Normal", "Title", "Heading 1", "Heading 2", "MTN Table Text"):
        assert document.styles[style].font.name == brand.FONT, style
    section = document.sections[0]
    assert round(section.page_width.cm, 1) == 21.0 and round(section.page_height.cm, 1) == 29.7
    with zipfile.ZipFile(path) as package:
        font_table = package.read("word/fontTable.xml").decode()
        assert f'w:name="{brand.FONT}"' in font_table and 'w:val="Arial"' in font_table
        assert not any(n.startswith("word/fonts/") for n in package.namelist()), "no embedded fonts"


def test_powerpoint_template_is_16_9_with_mtn_theme_font():
    path = templates.load(TEMPLATES, "powerpoint", "project_status").path
    prs = Presentation(path)
    assert round(prs.slide_width / prs.slide_height, 3) == round(16 / 9, 3)
    with zipfile.ZipFile(path) as package:
        theme = next(n for n in package.namelist() if n.startswith("ppt/theme/"))
        xml = package.read(theme).decode()
        assert f'typeface="{brand.FONT}"' in xml and brand.YELLOW in xml


def test_excel_template_has_named_styles():
    path = templates.load(TEMPLATES, "excel", "action_tracker").path
    workbook = load_workbook(path)
    names = set(workbook.named_styles)
    assert {"MTN Title", "MTN Header", "MTN Cell", "MTN Total"} <= names
