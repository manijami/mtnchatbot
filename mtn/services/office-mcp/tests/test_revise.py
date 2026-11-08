import base64
import hashlib
import io

from pptx import Presentation

from .conftest import ALICE, BOB, call, headers
from .samples import deck_spec, incident_process_spec, plan_spec

RISKS = {
    "columns": ["Risk", "Impact", "Mitigation"],
    "rows": [
        ["Supplier delay", "High", "Second supplier on standby"],
        ["Budget overrun", "Medium", "Monthly cost review"],
        ["Low adoption", "Medium", "Targeted customer comms"],
    ],
}


def _doc_id(result):
    return result["content"][0]["text"].split("document_id ")[1].split(".")[0]


def _resource(result):
    return next(c["resource"] for c in result["content"] if c["type"] == "resource")


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_revision_creates_v2_and_keeps_v1_unchanged(client, store):
    v1 = call(client, "create_powerpoint_presentation", deck_spec())
    doc_id = _doc_id(v1)
    v1_path = store.file_path(ALICE, doc_id, 1, "file")
    v1_hash, v1_bytes = _sha(v1_path), v1_path.read_bytes()

    # "Shorten slide 2 and add a risks table to slide 5"
    result = call(client, "revise_office_file", {
        "document_id": doc_id,
        "changes": [
            {"op": "replace", "path": "/slides/0/bullets", "value": ["On track overall", "One decision needed"]},
            {"op": "add", "path": "/slides/3/table", "value": RISKS},
            {"op": "remove", "path": "/slides/3/chart"},
            {"op": "replace", "path": "/slides/3/title", "value": "Budget and risks"},
        ],
    })
    assert result["isError"] is False, result
    text = result["content"][0]["text"]
    assert text.startswith("Revised version 1 into a new version") and "Version 2" in text
    assert "Version 1 is unchanged." in text
    assert _resource(result)["uri"].endswith("/v2/Network-Modernisation-Programme-v2.pptx")

    prs = Presentation(io.BytesIO(base64.b64decode(_resource(result)["blob"])))
    bullets = next(s for s in prs.slides[1].shapes if s.name == "mtn:bullets")
    assert [p.text for p in bullets.text_frame.paragraphs] == ["On track overall", "One decision needed"]
    table = next(s for s in prs.slides[4].shapes if s.has_table)
    assert table.table.cell(0, 0).text == "Risk" and len(table.table.rows) == 4

    doc = store.get_document(ALICE, doc_id)
    assert [(v.version, v.status) for v in doc.versions] == [(1, "complete"), (2, "complete")]
    assert doc.versions[1].checks["bounds"]["issues"] == []
    assert _sha(v1_path) == v1_hash and v1_path.read_bytes() == v1_bytes  # v1 untouched
    assert doc.versions[0].spec["slides"][3].get("table") is None  # v1 content untouched
    assert store.file_path(ALICE, doc_id, 2, "file").name.endswith("-v2.pptx")


def test_another_user_cannot_revise_or_see_status(client, store):
    doc_id = _doc_id(call(client, "create_word_document", incident_process_spec(), user=ALICE))
    for tool, args in (
        ("revise_office_file", {"document_id": doc_id, "changes": [{"op": "replace", "path": "/title", "value": "x"}]}),
        ("get_generation_status", {"document_id": doc_id}),
    ):
        result = call(client, tool, args, user=BOB)
        assert result["isError"] is True
        assert result["content"][0]["text"] == "No generated file with that document_id was found for you."
    missing = call(client, "get_generation_status", {"document_id": "0" * 32}, user=BOB)
    assert missing["content"][0]["text"] == "No generated file with that document_id was found for you."
    assert [v.version for v in store.get_document(ALICE, doc_id).versions] == [1]
    assert call(client, "get_generation_status", {}, user=BOB)["content"][0]["text"] == "You have no generated files yet."


def test_valid_token_and_another_users_id_gets_404_for_every_version_over_rest(client):
    doc_id = _doc_id(call(client, "create_word_document", incident_process_spec(), user=ALICE))
    call(client, "revise_office_file", {
        "document_id": doc_id, "changes": [{"op": "replace", "path": "/subtitle", "value": "Revised"}]
    }, user=ALICE)
    for version in (1, 2):
        assert client.get(f"/v1/documents/{doc_id}/versions/{version}/file", headers=headers()).status_code == 200
        assert client.get(f"/v1/documents/{doc_id}/versions/{version}/file", headers=headers(user=BOB)).status_code == 404


def test_bad_path_returns_the_outline(client, store):
    doc_id = _doc_id(call(client, "create_powerpoint_presentation", deck_spec()))
    result = call(client, "revise_office_file", {
        "document_id": doc_id, "changes": [{"op": "replace", "path": "/slides/9/title", "value": "x"}]
    })
    assert result["isError"] is True
    message = result["content"][0]["text"]
    assert "index 9 is out of range" in message
    result = call(client, "revise_office_file", {
        "document_id": doc_id, "changes": [{"op": "remove", "path": "/slides/0/table"}]
    })
    assert 'Slide 2 "Summary" (4 bullets, key_message, notes): /slide/2' in result["content"][0]["text"]
    assert [v.version for v in store.get_document(ALICE, doc_id).versions] == [1]


def test_revision_is_revalidated_with_the_same_rules(client, store):
    doc_id = _doc_id(call(client, "create_powerpoint_presentation", deck_spec()))
    result = call(client, "revise_office_file", {
        "document_id": doc_id, "changes": [{"op": "add", "path": "/slides/-", "value": {"title": "Extra", "bullets": ["x"]}}]
    })
    assert result["isError"] is True
    assert "target_slides is 5 but the deck has 6 slides" in result["content"][0]["text"]
    assert [v.version for v in store.get_document(ALICE, doc_id).versions] == [1]


def test_adding_a_table_to_a_chart_slide_explains_the_fix_and_remove_works(client, store):
    doc_id = _doc_id(call(client, "create_powerpoint_presentation", deck_spec()))
    bad = call(client, "revise_office_file", {
        "document_id": doc_id, "changes": [{"op": "add", "path": "/slide/5/table", "value": RISKS}]
    })
    assert bad["isError"] is True and "remove the chart (op remove, path /slide/N/chart)" in bad["content"][0]["text"]
    good = call(client, "revise_office_file", {
        "document_id": doc_id,
        "changes": [{"op": "add", "path": "/slide/5/table", "value": RISKS}, {"op": "remove", "path": "/slide/5/chart"}],
    })
    assert good["isError"] is False, good
    assert [v.version for v in store.get_document(ALICE, doc_id).versions] == [1, 2]


def test_full_content_revision_and_template_is_kept(client, store):
    doc_id = _doc_id(call(client, "create_excel_workbook", plan_spec()))
    content = plan_spec(template="action_tracker", title="Portal Rollout Plan v2")
    content["sheets"][0]["rows"] = content["sheets"][0]["rows"][:2]
    result = call(client, "revise_office_file", {"document_id": doc_id, "content": content})
    assert result["isError"] is False, result
    doc = store.get_document(ALICE, doc_id)
    assert doc.versions[1].spec["template"] == "project_plan"  # the document's template wins
    assert doc.versions[1].spec["title"] == "Portal Rollout Plan v2"


def test_status_lists_versions_and_outline_for_the_owner(client):
    doc_id = _doc_id(call(client, "create_powerpoint_presentation", deck_spec()))
    call(client, "revise_office_file", {"document_id": doc_id, "changes": [{"op": "replace", "path": "/subtitle", "value": "Q3 v2"}]})
    text = call(client, "get_generation_status", {"document_id": doc_id})["content"][0]["text"]
    assert "- v1 complete" in text and "- v2 complete" in text
    assert "Outline of v2" in text and 'Slide 5 "Budget by category" (chart, key_message): /slide/5' in text
    listing = call(client, "get_generation_status", {})["content"][0]["text"]
    assert doc_id in listing and "latest v2 (complete)" in listing


def test_exactly_one_of_changes_or_content(client):
    doc_id = _doc_id(call(client, "create_word_document", incident_process_spec()))
    result = call(client, "revise_office_file", {"document_id": doc_id})
    assert result["content"][0]["text"] == "Pass exactly one of changes or content."


def test_visible_slide_numbers_address_the_slide_the_user_sees(client, store):
    created = call(client, "create_powerpoint_presentation", deck_spec())
    assert 'Slide 2 "Summary" (4 bullets, key_message, notes): /slide/2' in created["content"][0]["text"]
    doc_id = _doc_id(created)
    result = call(client, "revise_office_file", {
        "document_id": doc_id,
        "changes": [
            {"op": "replace", "path": "/slide/2/bullets", "value": ["Shortened"]},
            {"op": "add", "path": "/slide/5/table", "value": RISKS},
            {"op": "remove", "path": "/slide/5/chart"},
            {"op": "replace", "path": "/slide/1/subtitle", "value": "Q3 review, revised"},
        ],
    })
    assert result["isError"] is False, result
    spec = store.get_document(ALICE, doc_id).versions[1].spec
    assert spec["slides"][0]["bullets"] == ["Shortened"]  # slide 2 = first content slide
    assert spec["slides"][3]["table"]["columns"][0] == "Risk"  # slide 5 = fourth content slide
    assert spec["subtitle"] == "Q3 review, revised"
    bad = call(client, "revise_office_file", {
        "document_id": doc_id, "changes": [{"op": "replace", "path": "/slide/9/title", "value": "x"}]
    })
    assert bad["isError"] is True and "/slide/5" in bad["content"][0]["text"]
