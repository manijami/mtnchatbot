"""Excel insights E3: files built from a saved run (charts, infographic, dashboard, deck, workbook)."""

import base64
import hashlib
import io
import json
import re
from dataclasses import replace

import pytest
from openpyxl import load_workbook
from pptx import Presentation
from starlette.testclient import TestClient

from office_mcp.app import build_app
from office_mcp.errors import ToolError
from office_mcp.insights_outputs import check_numbers, dashboard_html

from .conftest import ALICE, BOB, call
from .test_insights import write_sales

PNG = "image/png"
ORIGINAL = "1111aaaa-0000-4000-8000-000000000001__sales.xlsx"
# The same rule LibreChat's file-output check applies to HTML (packages/api/src/mcp/fileOutputs.ts).
ACTIVE_HTML = re.compile(r"<\s*(script|iframe|object|embed|form|meta\s+[^>]*http-equiv)|\son[a-z]+\s*=|javascript:|vbscript:", re.I)


@pytest.fixture
def uploads(tmp_path):
    root = tmp_path / "uploads"
    (root / ALICE).mkdir(parents=True)
    (root / BOB).mkdir()
    write_sales(root / ALICE / ORIGINAL)
    return root


@pytest.fixture
def iclient(settings, store, uploads):
    with TestClient(build_app(replace(settings, uploads_dir=uploads), store)) as c:
        yield c


def _json(result):
    return json.loads(result["content"][0]["text"].split("\n", 1)[1])


def _analyse(iclient, user=ALICE):
    result = call(iclient, "analyse_workbook", {"file": "sales.xlsx", "analyses": [
        {"type": "group_summary", "group_by": "Region", "measure": "Revenue"},
        {"type": "time_trend", "date_column": "Month", "measure": "Revenue", "period": "month"},
        {"type": "share_of_total", "group_by": "Product", "measure": "Revenue"},
        {"type": "period_change", "date_column": "Month", "measure": "Units", "period": "quarter"},
    ]}, user=user)
    assert result["isError"] is False, result
    return _json(result)


def _resources(result):
    return {c["resource"]["uri"].rsplit("/", 1)[1]: (c["resource"]["mimeType"], base64.b64decode(c["resource"]["blob"]))
            for c in result["content"] if c["type"] == "resource"}


def test_every_output_is_built_from_the_run_and_the_original_is_untouched(iclient, uploads):
    before = hashlib.sha256((uploads / ALICE / ORIGINAL).read_bytes()).hexdigest()
    run = _analyse(iclient)
    region = run["results"][0]["table"]["rows"][0]
    share = run["results"][2]["table"]["rows"][0]
    insight = f"{region[0]} had the highest revenue: {region[1]:,.2f}; {share[0]} took {share[2]}% of revenue."
    result = call(iclient, "create_insights_files", {"run_id": run["run_id"], "title": "Sales insights", "insights": [insight]})
    assert result["isError"] is False, result
    files = _resources(result)
    kinds = {name.rsplit(".", 1)[1] for name in files}
    assert kinds == {"png", "pdf", "html", "pptx", "xlsx"}
    charts = [n for n, (m, _) in files.items() if m == PNG and "infographic" not in n]
    assert len(charts) == 4
    for name, (mime, data) in files.items():
        if mime == PNG:
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert files["Sales-insights-infographic.pdf"][1][:5] == b"%PDF-"
    page = files["Sales-insights-dashboard.html"][1].decode()
    assert page.startswith("<!DOCTYPE html>") and not ACTIVE_HTML.search(page)
    assert f"{region[1]:,.0f}"[:3] in page or region[0] in page

    deck = Presentation(io.BytesIO(next(d for n, (m, d) in files.items() if n.endswith(".pptx"))))
    deck_charts = [shape.chart for slide in deck.slides for shape in slide.shapes if shape.has_chart]
    assert len(deck_charts) == 4
    first_values = list(deck_charts[0].plots[0].series[0].values)
    assert first_values == [r[1] for r in run["results"][0]["table"]["rows"][:12]]

    book = load_workbook(io.BytesIO(next(d for n, (m, d) in files.items() if n.endswith(".xlsx"))))
    assert book.sheetnames[0] == "Summary" and len(book.sheetnames) == 5
    region_sheet = book[book.sheetnames[1]]
    assert len(region_sheet._charts) == 1
    sheet_values = [row for row in region_sheet.iter_rows(min_row=5, values_only=True) if row[0]]
    assert [list(r[:2]) for r in sheet_values[:5]] == [r[:2] for r in run["results"][0]["table"]["rows"][:5]]
    assert any(insight in str(c) for row in book["Summary"].iter_rows(values_only=True) for c in row if c)

    assert hashlib.sha256((uploads / ALICE / ORIGINAL).read_bytes()).hexdigest() == before


def test_insights_with_numbers_not_in_the_results_are_refused(iclient):
    run = _analyse(iclient)
    result = call(iclient, "create_insights_files", {"run_id": run["run_id"], "outputs": ["dashboard"],
                                                     "insights": ["Revenue grew by 37.4% to R 9,999,999."]})
    assert result["isError"] is True
    assert "not in the analysis results" in result["content"][0]["text"] and "9,999,999" in result["content"][0]["text"]


def test_another_user_cannot_use_the_run(iclient):
    run = _analyse(iclient)
    result = call(iclient, "create_insights_files", {"run_id": run["run_id"], "outputs": ["charts"]}, user=BOB)
    assert result["isError"] is True and "Unknown analysis run" in result["content"][0]["text"]


def test_unknown_outputs_are_refused(iclient):
    run = _analyse(iclient)
    result = call(iclient, "create_insights_files", {"run_id": run["run_id"], "outputs": ["video"]})
    assert result["isError"] is True and "Unknown outputs" in result["content"][0]["text"]


RUN = {"file": "x.xlsx", "run_id": "run_abc", "results": [
    {"id": "A1", "type": "group_summary", "title": "Total Revenue by Region", "sheet": "S", "columns_used": ["Region", "Revenue"],
     "rows_used": 359, "rows_left_out": {"blank Revenue": 3},
     "table": {"columns": ["Region", "Total Revenue"], "rows": [["Gauteng", 1234567.89], ["Limpopo", 98765.4]]}},
    {"id": "A2", "type": "share_of_total", "title": "Share", "sheet": "S", "columns_used": ["Region"], "rows_used": 359,
     "table": {"columns": ["Region", "Total", "Share of total (%)"], "rows": [["Gauteng", 1234567.89, 92.6], ["Limpopo", 98765.4, 7.4]]}},
    {"id": "A3", "type": "time_trend", "title": "By month", "sheet": "S", "columns_used": ["Month"], "rows_used": 12,
     "table": {"columns": ["Month", "Total"], "rows": [["2026-01", 100.0], ["2026-02", 120.5]]}},
    {"id": "A4", "type": "group_summary", "title": "By product", "sheet": "S", "columns_used": ["Product"], "rows_used": 359,
     "table": {"columns": ["Product", "Total"], "rows": [["Fibre 100", 2034485.58], ["Fibre 50", 2541333.32]]}},
]}


@pytest.mark.parametrize("text", [
    "Gauteng led with 1,234,567.89 in revenue.",
    "Gauteng led with about 1.2m (R1.23 million), a 92.6% share.",
    "Revenue in 2026-02 was 120.5, up from 100 in 2026-01.",
    "The top 3 regions; 359 rows used and 3 left out for blanks.",
    "Gauteng: 1,234,568 (rounded).",
    "Fibre 50 (R2.54 M) sold more than Fibre 100 (R2.03 M).",
])
def test_number_check_accepts_numbers_from_the_results(text):
    check_numbers([text], RUN)


@pytest.mark.parametrize("text,bad", [
    ("Gauteng led with 1,300,000 in revenue.", "1,300,000"),
    ("Revenue grew 15% month on month.", "15%"),
    ("Limpopo had 3.7m in revenue.", "3.7m"),
    ("Fibre 100 sold 250 units.", "250"),
])
def test_number_check_refuses_invented_numbers(text, bad):
    with pytest.raises(ToolError, match=re.escape(bad)):
        check_numbers([text], RUN)


def test_dashboard_escapes_labels_from_the_data():
    run = json.loads(json.dumps(RUN))
    run["results"][0]["table"]["rows"][0][0] = "<script>alert(1)</script>"
    page = dashboard_html(run, "T <b>", ["Insight with <img src=x onerror=alert(1)>"], {}).decode()
    assert "<script>alert" not in page and "&lt;script&gt;" in page and not ACTIVE_HTML.search(page)


@pytest.mark.parametrize("value,text", [(0, "0"), (500_000, "500k"), (1_500_000, "1.5m"), (2_000_000_000, "2bn"), (0.5, "0.5")])
def test_chart_axes_use_short_numbers_not_scientific_notation(value, text):
    from office_mcp.insights_outputs import _tick
    assert _tick(value) == text
