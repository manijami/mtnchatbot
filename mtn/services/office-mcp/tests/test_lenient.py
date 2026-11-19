"""Clear-intent mistakes are repaired (and recorded) instead of costing the model a retry."""
import base64
import io

import pytest
from pptx import Presentation

from office_mcp.lenient import trim_words

from .conftest import ALICE, call
from .samples import deck_spec, incident_process_spec, plan_spec


def _doc(store, result):
    return store.get_document(ALICE, result["content"][0]["text"].split("document_id ")[1].split(".")[0])


def _slides(result):
    blob = next(c["resource"]["blob"] for c in result["content"] if c["type"] == "resource")
    return Presentation(io.BytesIO(base64.b64decode(blob))).slides


def test_numbered_list_on_a_slide_becomes_numbered_bullets(client, store):
    spec = deck_spec()
    spec["slides"][0]["numbered"] = ["Fix usability issues", "Approve rollout"]
    result = call(client, "create_powerpoint_presentation", spec)
    assert result["isError"] is False, result
    bullets = next(s for s in _slides(result)[1].shapes if s.name == "mtn:bullets")
    texts = [p.text for p in bullets.text_frame.paragraphs]
    assert texts[-2:] == ["1. Fix usability issues", "2. Approve rollout"]
    coercions = _doc(store, result).latest.checks["coercions"]
    assert any("slides[0].numbered" in c for c in coercions)
    assert "Adjusted automatically: slides[0].numbered" in result["content"][0]["text"]


def test_slightly_long_bullet_and_title_are_trimmed_at_a_word_boundary(client, store):
    spec = deck_spec()
    spec["slides"][0]["bullets"][0] = ("word " * 40).strip()  # 199 characters, limit 160
    spec["slides"][1]["title"] = (
        "A slide title that runs a little past the ninety character limit for slide titles in this deck today"
    )
    assert 90 < len(spec["slides"][1]["title"]) <= 135
    result = call(client, "create_powerpoint_presentation", spec)
    assert result["isError"] is False, result
    version = _doc(store, result).latest
    bullet = version.spec["slides"][0]["bullets"][0]
    assert len(bullet) <= 160 and bullet.endswith("…") and not bullet[:-1].endswith(" ")
    assert {c.split(":")[0] for c in version.checks["coercions"]} >= {"slides[0].bullets[0]", "slides[1].title"}


def test_text_far_over_the_limit_is_still_rejected(client, store):
    spec = deck_spec()
    spec["slides"][0]["bullets"][0] = "word " * 80  # 400 characters: trimming would lose real content
    result = call(client, "create_powerpoint_presentation", spec)
    assert result["isError"] is True
    assert "slides[0].bullets[0]" in result["content"][0]["text"]
    assert store.list_documents(ALICE) == []


def test_unknown_harmless_fields_are_ignored_and_recorded(client, store):
    spec = deck_spec(theme="dark")
    spec["slides"][0]["layout"] = "bullets"
    result = call(client, "create_powerpoint_presentation", spec)
    assert result["isError"] is False, result
    coercions = _doc(store, result).latest.checks["coercions"]
    assert "theme: unknown field ignored" in coercions and "slides[0].layout: unknown field ignored" in coercions


def test_up_to_eight_bullets_are_accepted_when_they_fit(client):
    spec = deck_spec()
    spec["slides"][0]["bullets"] = [f"Point {n}" for n in range(8)]
    assert call(client, "create_powerpoint_presentation", spec)["isError"] is False


def test_chart_with_too_many_series_keeps_the_first_four(client, store):
    spec = plan_spec()
    sheet = spec["sheets"][0]
    sheet["chart"] = {"type": "column", "source": "data", "category_column": "Task",
                      "value_columns": ["Duration (days)", "Budget", "% complete", "Duration (days)", "Budget"]}
    result = call(client, "create_excel_workbook", spec)
    assert result["isError"] is False, result
    version = _doc(store, result).latest
    assert len(version.spec["sheets"][0]["chart"]["value_columns"]) == 4
    assert any("chart shows the first 4 series" in c for c in version.checks["coercions"])


def test_numbers_in_word_tables_and_string_levels_are_accepted(client, store):
    spec = incident_process_spec()
    spec["sections"][2]["table"]["rows"][0][2] = 15
    spec["sections"][6]["level"] = "2"
    result = call(client, "create_word_document", spec)
    assert result["isError"] is False, result
    version = _doc(store, result).latest
    assert version.spec["sections"][2]["table"]["rows"][0][2] == "15"
    assert version.spec["sections"][6]["level"] == 2


def test_strict_rules_that_protect_the_document_still_apply(client):
    spec = deck_spec()
    spec["slides"][2]["table"]["rows"].append(["only two", "cells"])
    assert "rows[4] has 2 cells" in call(client, "create_powerpoint_presentation", spec)["content"][0]["text"]
    spec = deck_spec(target_slides=6)
    assert "target_slides is 6" in call(client, "create_powerpoint_presentation", spec)["content"][0]["text"]


@pytest.mark.parametrize(
    "text,limit,expected",
    [("short", 10, "short"), ("one two three four", 12, "one two…"), ("abcdefghijklmnop", 8, "abcdefg…")],
)
def test_trim_words(text, limit, expected):
    assert trim_words(text, limit) == expected
