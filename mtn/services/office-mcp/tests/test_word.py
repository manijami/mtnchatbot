import base64
import io
import zipfile
from dataclasses import replace

import pytest
from docx import Document
from starlette.testclient import TestClient

from office_mcp import render
from office_mcp.app import build_app

from .conftest import ALICE, BOB, call, headers
from .samples import incident_process_spec

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _parts(result):
    text = next(c["text"] for c in result["content"] if c["type"] == "text")
    resources = [c["resource"] for c in result["content"] if c["type"] == "resource"]
    return text, resources


def _document_id(text):
    return text.split("document_id ")[1].split(".")[0]


def test_creates_a_valid_two_page_word_document(client, store):
    result = call(client, "create_word_document", incident_process_spec())
    assert result["isError"] is False, result
    text, resources = _parts(result)
    assert len(resources) == 1
    resource = resources[0]
    assert resource["mimeType"] == DOCX
    assert resource["uri"].endswith("/v1/IT-Incident-Management-Process.docx")
    data = base64.b64decode(resource["blob"])
    assert data[:4] == b"PK\x03\x04"
    document = Document(io.BytesIO(data))
    assert document.paragraphs[1].text == "IT Incident Management Process"
    assert any(p.style.name == "List Number" for p in document.paragraphs)
    assert len(document.tables) == 2  # cover fields + severity table
    # The model only sees the summary text; file bytes never appear in it.
    assert len(text) < 1000 and resource["blob"][:40] not in text
    assert "2 pages" in text
    doc = store.get_document(ALICE, _document_id(text))
    version = doc.latest
    assert version.status == "complete" and version.pages == 2
    assert version.checks["render"] == "ok" and version.checks["package"] == "ok"
    assert version.checks["reopen"]["headings"] == 7
    assert version.checks["logo"] == "absent"


def test_logo_is_added_when_the_private_folder_has_one(settings, store, tmp_path):
    from PIL import Image

    logo_dir = tmp_path / "logo"
    logo_dir.mkdir()
    Image.new("RGB", (2000, 2000), "#FFCB05").save(logo_dir / "yello_logo.jpg")
    with TestClient(build_app(replace(settings, logo_dir=logo_dir), store)) as client:
        result = call(client, "create_word_document", incident_process_spec())
    text, resources = _parts(result)
    assert "Logo added" in text
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(resources[0]["blob"]))) as package:
        media = [n for n in package.namelist() if n.startswith("word/media/")]
        assert media, "logo image is embedded in the header"
        assert len(package.read(media[0])) < 60_000, "logo is downscaled"


def test_bold_markup_becomes_bold_runs_and_control_characters_are_removed(client):
    spec = incident_process_spec()
    spec["sections"][0]["paragraphs"] = ["Start **important part** end\x07."]
    result = call(client, "create_word_document", spec)
    _, resources = _parts(result)
    document = Document(io.BytesIO(base64.b64decode(resources[0]["blob"])))
    paragraph = next(p for p in document.paragraphs if p.text.startswith("Start"))
    assert paragraph.text == "Start important part end."
    assert [r.text for r in paragraph.runs if r.bold] == ["important part"]


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda s: s.update(template="memo"), "template"),
        (lambda s: s.update(sections=[]), "sections"),
        (lambda s: s["sections"][2]["table"]["rows"].append(["P5", "too short"]), "sections[2].table"),
        (lambda s: s["sections"][0].update(paragraphs=[]), "sections[0]"),
        (lambda s: s.update(title="x" * 151), "title"),
        (lambda s: s.update(colour="red"), "colour"),
    ],
)
def test_invalid_arguments_return_fixable_errors(client, store, mutate, expected):
    spec = incident_process_spec()
    mutate(spec)
    result = call(client, "create_word_document", spec)
    assert result["isError"] is True
    message = result["content"][0]["text"]
    assert message.startswith("The arguments are not valid. Fix these fields")
    assert expected in message
    assert store.list_documents(ALICE) == []  # nothing recorded for rejected input


def test_render_failure_marks_the_version_failed_and_delivers_nothing(client, store, monkeypatch):
    async def broken(*_args, **_kwargs):
        raise render.RenderError("LibreOffice did not finish within 60 seconds")

    monkeypatch.setattr(render, "convert", broken)
    result = call(client, "create_word_document", incident_process_spec())
    assert result["isError"] is True
    assert "failed validation and was not delivered" in result["content"][0]["text"]
    assert not [c for c in result["content"] if c["type"] == "resource"]
    [doc] = store.list_documents(ALICE)
    assert doc.latest.status == "failed"


def test_owner_can_download_and_preview_over_rest(client):
    text, _ = _parts(call(client, "create_word_document", incident_process_spec()))
    doc_id = _document_id(text)
    meta = client.get(f"/v1/documents/{doc_id}", headers=headers())
    assert meta.status_code == 200 and meta.json()["versions"][0]["pages"] == 2
    file = client.get(f"/v1/documents/{doc_id}/versions/1/file", headers=headers())
    assert file.status_code == 200 and file.content[:2] == b"PK"
    preview = client.get(f"/v1/documents/{doc_id}/versions/1/preview.png", headers=headers())
    assert preview.status_code == 200 and preview.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_valid_token_with_another_users_id_gets_404(client):
    """Bob presents a valid service token but cannot see Alice's document."""
    text, _ = _parts(call(client, "create_word_document", incident_process_spec(), user=ALICE))
    doc_id = _document_id(text)
    for path in (
        f"/v1/documents/{doc_id}",
        f"/v1/documents/{doc_id}/versions/1/file",
        f"/v1/documents/{doc_id}/versions/1/preview.png",
        f"/v1/documents/{doc_id}/versions/1/preview.pdf",
    ):
        response = client.get(path, headers=headers(user=BOB))
        assert response.status_code == 404, path
        assert response.json() == {"error": "not found"}
    # Same answer as a document that does not exist at all.
    assert client.get("/v1/documents/" + "0" * 32, headers=headers(user=BOB)).status_code == 404


def test_unknown_artifact_name_is_404(client):
    text, _ = _parts(call(client, "create_word_document", incident_process_spec()))
    doc_id = _document_id(text)
    for name in ("../office.db", "spec.json", "preview.gif"):
        assert client.get(f"/v1/documents/{doc_id}/versions/1/{name}", headers=headers()).status_code == 404


def test_page_target_rejects_a_longer_document_with_the_measured_overflow(client, store):
    spec = incident_process_spec(target_pages=1)
    result = call(client, "create_word_document", spec)
    assert result["isError"] is True
    message = result["content"][0]["text"]
    assert "renders to 2 pages but target_pages is 1" in message
    assert "lines spill past page 1" in message and "7 sections" in message
    assert not [c for c in result["content"] if c["type"] == "resource"]
    [doc] = store.list_documents(ALICE)
    assert doc.latest.status == "failed"
    target = doc.latest.checks["page_target"]
    assert target["target"] == 1 and target["rendered"] == 2 and target["overflow_lines"] > 10


def test_page_target_met_is_delivered(client):
    result = call(client, "create_word_document", incident_process_spec(target_pages=2))
    assert result["isError"] is False
    assert "2 pages" in result["content"][0]["text"]


def test_table_rows_do_not_split_across_pages_and_header_repeats(client):
    _, resources = _parts(call(client, "create_word_document", incident_process_spec()))
    document = Document(io.BytesIO(base64.b64decode(resources[0]["blob"])))
    table = document.tables[1]
    assert table.rows[0]._tr.trPr.xml.count("tblHeader") == 1
    assert all("cantSplit" in row._tr.trPr.xml for row in table.rows[1:])



def test_stringified_container_fields_are_decoded(client):
    import json

    spec = incident_process_spec()
    spec["sections"] = json.dumps(spec["sections"])
    result = call(client, "create_word_document", spec)
    assert result["isError"] is False, result


def test_text_that_merely_starts_with_a_bracket_stays_text(client):
    spec = incident_process_spec()
    spec["sections"][0]["paragraphs"] = ["[Draft] for review", "{placeholder} text"]
    result = call(client, "create_word_document", spec)
    assert result["isError"] is False, result


def test_broken_stringified_json_says_exactly_what_to_fix(client):
    spec = incident_process_spec()
    spec["sections"] = '[{"heading": "A", "paragraphs": ["x"] "level": 1}]'
    result = call(client, "create_word_document", spec)
    assert result["isError"] is True
    message = result["content"][0]["text"]
    assert "'sections' was sent as a string" in message and "not valid JSON" in message
