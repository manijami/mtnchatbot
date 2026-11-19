"""Offline Word contract check through real Office MCP; does not prove LibreChat delivery."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import tempfile
from pathlib import Path

from docx import Document
from starlette.testclient import TestClient

from office_mcp.app import build_app
from office_mcp.config import Settings
from office_mcp.store import Store

OUTPUT = Path("/out")
OWNER = "a" * 24
HEADERS = {"Authorization": "Bearer " + "offline-test-token-" * 3,
           "X-MTN-User-Id": OWNER, "Accept": "application/json, text/event-stream"}


def main():
    spec = {
        "template": "incident_report",
        "title": "Phoenix Payment Incident - Offline Fixture",
        "subtitle": "SYNTHETIC - template verification only; no live Splunk searches executed",
        "cover_fields": [{"label": "Incident ID", "value": "SYNTHETIC-CHG-2240"},
                         {"label": "Status", "value": "Offline verification"}],
        "sections": [
            {"heading": "Timeline", "table": {"columns": ["Time (SAST)", "Fixture event"], "rows": [
                ["22:40", "Connection pool configuration changed from 80 to 2."],
                ["After 22:40", "Payment 5xx and timeouts on pay-api-01 and pay-api-02."],
                ["23:20", "Rollback restored the original pool configuration."]]}},
            {"heading": "Impact", "paragraphs": ["The generator plants failures on two payment hosts. Customer and financial impact: Not stated. These are fixture facts, not live observations."]},
            {"heading": "Root cause", "paragraphs": ["Confirmed fixture facts: configuration change precedes errors, followed by rollback. Hypothesis: connection pool exhaustion. Runtime evidence has not been retrieved."]},
            {"heading": "Evidence", "paragraphs": ["Source: mtn/demo/splunk/seed.py. Synthetic change ID: SYNTHETIC-CHG-2240. Searches used: None. No live searches were executed for this offline fixture."]},
            {"heading": "Remediation", "paragraphs": ["Fixture includes rollback to pool-v1. Proposed: review pool settings and verify recovery using bounded aggregate searches."]},
            {"heading": "Follow-up actions", "bullets": ["Run live Splunk and browser acceptance after operator setup. Owner and due date: Not stated.", "MSISDN masking remains pending; this document does not verify masking."]},
        ],
    }
    with tempfile.TemporaryDirectory() as directory:
        settings = Settings(token="offline-test-token-" * 3, data_dir=Path(directory), templates_dir=Path("/app/templates"),
                            logo_dir=Path(directory) / "no-logo", host="127.0.0.1", port=8000, retention_days=0,
                            convert_timeout_s=60, max_file_bytes=20 * 1024 * 1024, preview_image=False)
        store = Store(settings.data_dir)
        with TestClient(build_app(settings, store)) as client:
            response = client.post("/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "id": 1,
                "method": "tools/call", "params": {"name": "create_word_document", "arguments": spec}})
            assert response.status_code == 200
            result = response.json()["result"]
            assert not result["isError"], result
            resource = next(c["resource"] for c in result["content"] if c["type"] == "resource")
            data = base64.b64decode(resource["blob"])
            document = Document(io.BytesIO(data))
            headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
            assert all(s["heading"] in headings for s in spec["sections"])
            record, = store.list_documents(OWNER)
            path = f"/v1/documents/{record.id}/versions/1"
            download = client.get(path + "/file", headers=HEADERS)
            assert download.status_code == 200 and download.content == data
            other = client.get(path + "/file", headers=dict(HEADERS, **{"X-MTN-User-Id": "b" * 24}))
            assert other.status_code == 404
            pdf = client.get(path + "/preview.pdf", headers=HEADERS)
            png = client.get(path + "/preview.png", headers=HEADERS)
            assert pdf.status_code == png.status_code == 200
            assert record.latest.checks["render"] == "ok"
            OUTPUT.mkdir(parents=True, exist_ok=True)
            (OUTPUT / "phoenix-offline-fixture.docx").write_bytes(data)
            (OUTPUT / "phoenix-offline-fixture.pdf").write_bytes(pdf.content)
            (OUTPUT / "phoenix-offline-fixture.png").write_bytes(png.content)
            evidence = {"status": "passed-offline-only", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                        "pages": record.latest.pages, "headings": headings, "checks": record.latest.checks,
                        "download_matches": True, "other_owner_status": other.status_code,
                        "browser_attachment": "blocked", "live_splunk": "blocked"}
            (OUTPUT / "word-verification.json").write_text(json.dumps(evidence, indent=2) + "\n")
            print(json.dumps(evidence, indent=2))
        store.close()


if __name__ == "__main__":
    main()
