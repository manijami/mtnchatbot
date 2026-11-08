import base64
import io

import pytest
from pptx import Presentation

from office_mcp import bounds
from office_mcp.powerpoint import FitError

from .conftest import ALICE, call
from .samples import deck_spec

PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _resource(result):
    return next(c["resource"] for c in result["content"] if c["type"] == "resource")


def _doc(store, result):
    text = result["content"][0]["text"]
    return store.get_document(ALICE, text.split("document_id ")[1].split(".")[0])


def test_creates_a_five_slide_deck_with_native_charts_notes_and_clean_bounds(client, store, tmp_path):
    result = call(client, "create_powerpoint_presentation", deck_spec())
    assert result["isError"] is False, result
    text = result["content"][0]["text"]
    assert "5 slides" in text and "bounds check passed" in text
    resource = _resource(result)
    assert resource["mimeType"] == PPTX
    prs = Presentation(io.BytesIO(base64.b64decode(resource["blob"])))
    assert len(prs.slides) == 5
    assert round(prs.slide_width / prs.slide_height, 3) == round(16 / 9, 3)
    charts = [s for slide in prs.slides for s in slide.shapes if s.has_chart]
    assert len(charts) == 2 and {c.name for c in charts} == {"mtn:chart"}
    tables = [s for slide in prs.slides for s in slide.shapes if s.has_table]
    assert len(tables) == 1 and tables[0].table.cell(0, 0).text == "Workstream"
    assert prs.slides[1].notes_slide.notes_text_frame.text.startswith("Open with")
    version = _doc(store, result).latest
    assert version.pages == 5
    assert version.checks["bounds"]["issues"] == []
    assert version.checks["bounds"]["slides"] == 5
    assert version.checks["reopen"] == {"slides": 5, "notes": 2}


def test_logo_on_every_slide_when_available(settings, store, tmp_path):
    from dataclasses import replace

    from PIL import Image
    from starlette.testclient import TestClient

    from office_mcp.app import build_app

    logo_dir = tmp_path / "logo"
    logo_dir.mkdir()
    Image.new("RGB", (800, 800), "#FFCB05").save(logo_dir / "yello_logo.jpg")
    with TestClient(build_app(replace(settings, logo_dir=logo_dir), store)) as client:
        result = call(client, "create_powerpoint_presentation", deck_spec())
    prs = Presentation(io.BytesIO(base64.b64decode(_resource(result)["blob"])))
    assert all(any(s.name == "mtn:logo" for s in slide.shapes) for slide in prs.slides)


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda s: s.update(target_slides=6), "give exactly 5 items in slides"),
        (lambda s: s["slides"][2].update(chart=s["slides"][1]["chart"]), "either table or chart"),
        (lambda s: s["slides"][1]["chart"]["series"][0]["values"].pop(), "series[0] has 2 values"),
        (lambda s: s["slides"][3]["chart"]["series"].append({"name": "x", "values": [1, 2, 3, 4]}), "pie chart takes exactly one series"),
        (lambda s: s["slides"][0].update(bullets=["x"] * 7), "slides[0].bullets"),
        (lambda s: s["slides"][0].update(bullets=[], key_message=None), "needs bullets, a table or a chart"),
        (lambda s: s.update(template="pitch_deck"), "template"),
    ],
)
def test_invalid_decks_return_fixable_errors(client, store, mutate, expected):
    spec = deck_spec()
    mutate(spec)
    result = call(client, "create_powerpoint_presentation", spec)
    assert result["isError"] is True
    assert expected in result["content"][0]["text"]
    assert store.list_documents(ALICE) == []


def test_text_that_cannot_fit_is_rejected_with_guidance(client, store):
    long = "This bullet is deliberately long so that six of them cannot fit beside a table " * 2
    spec = deck_spec()
    spec["slides"][2]["bullets"] = [long[:158]] * 6
    result = call(client, "create_powerpoint_presentation", spec)
    assert result["isError"] is True
    message = result["content"][0]["text"]
    assert "slides[2].bullets" in message and "split the slide" in message
    [doc] = store.list_documents(ALICE)
    assert doc.latest.status == "failed"


def _built_deck(client, tmp_path):
    result = call(client, "create_powerpoint_presentation", deck_spec())
    path = tmp_path / "deck.pptx"
    path.write_bytes(base64.b64decode(_resource(result)["blob"]))
    return path


def _shape(prs, slide, role):
    return next(s for s in prs.slides[slide].shapes if s.name == f"mtn:{role}")


def test_bounds_check_catches_off_slide_and_safe_margin(client, tmp_path):
    path = _built_deck(client, tmp_path)
    assert bounds.check(path)["issues"] == []
    prs = Presentation(path)
    _shape(prs, 2, "chart").left = prs.slide_width - 100000
    prs.save(path)
    issues = bounds.check(path)["issues"]
    assert any("slide 3: chart is off the slide" in i for i in issues)
    assert any("slide 3: chart crosses the safe margin" in i for i in issues)


def test_bounds_check_catches_overlap(client, tmp_path):
    path = _built_deck(client, tmp_path)
    prs = Presentation(path)
    chart = _shape(prs, 2, "chart")
    bullets = _shape(prs, 2, "bullets")
    chart.left, chart.top = bullets.left, bullets.top
    prs.save(path)
    assert any("slide 3: chart overlaps bullets" in i or "bullets overlaps chart" in i for i in bounds.check(path)["issues"])


def test_bounds_check_catches_text_overflow(client, tmp_path):
    from pptx.util import Pt

    path = _built_deck(client, tmp_path)
    prs = Presentation(path)
    for paragraph in _shape(prs, 1, "bullets").text_frame.paragraphs:
        for run in paragraph.runs:
            run.font.size = Pt(54)
    prs.save(path)
    assert any("slide 2: bullets text overflows" in i for i in bounds.check(path)["issues"])


def test_fit_error_is_a_value_error():
    assert issubclass(FitError, ValueError)


def test_pie_labels_sit_outside_and_brand_blocks_have_no_shadow(client):
    from pptx.enum.chart import XL_LABEL_POSITION

    prs = Presentation(io.BytesIO(base64.b64decode(_resource(call(client, "create_powerpoint_presentation", deck_spec()))["blob"])))
    pie = _shape(prs, 4, "chart").chart
    assert pie.plots[0].data_labels.position == XL_LABEL_POSITION.OUTSIDE_END
    key = _shape(prs, 1, "key_message")
    assert key.shadow.inherit is False
    assert key._element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}style") is None
