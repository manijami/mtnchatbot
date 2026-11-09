"""Excel insights E2: every number the tools return is checked against pandas on the source data."""

import asyncio
import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from openpyxl import Workbook as XLWorkbook

from office_mcp.auth import Identity
from office_mcp.errors import ToolError
from office_mcp.files import InsightLimits, LocalUploadsSource
from office_mcp.insights_analyse import analyse, parse_request
from office_mcp.insights_data import describe, read_workbook
from office_mcp.tools import ToolContext
from office_mcp.tools.insights_tool import analyse_workbook, inspect_workbook, load_run

ALICE, BOB = "a" * 24, "b" * 24
LIMITS = InsightLimits()


# -- synthetic workbooks ------------------------------------------------------------------------------


def sales_frame() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    months = pd.date_range("2025-01-01", "2026-06-01", freq="MS")
    rows = []
    for m in months:
        for region in ("Gauteng", "Western Cape", "KwaZulu-Natal", "Eastern Cape", "Limpopo"):
            for product in ("Fibre 50", "Fibre 100", "LTE Home", "5G Home"):
                units = int(rng.integers(5, 80))
                rows.append([m.to_pydatetime(), region, product, units, round(units * float(rng.uniform(300, 900)), 2)])
    frame = pd.DataFrame(rows, columns=["Month", "Region", "Product", "Units", "Revenue"])
    frame.loc[[3, 40, 77], "Revenue"] = np.nan          # blanks
    frame.loc[10, "Revenue"] = 950_000.0                 # an outlier
    frame = pd.concat([frame, frame.iloc[[5, 6]]], ignore_index=True)  # two duplicate rows
    return frame


def write_sales(path: Path) -> pd.DataFrame:
    frame = sales_frame()
    wb = XLWorkbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Synthetic sales report"])                # a title row above the header
    ws.append([])
    ws.append(list(frame.columns))
    for i, row in enumerate(frame.itertuples(index=False)):
        values = [None if (isinstance(v, float) and np.isnan(v)) else v for v in row]
        if i == 20:
            values[4] = f"R {values[4]:,.2f}"            # a number typed as text
        ws.append(values)
    wb.save(path)
    # What a careful analyst would compute from the same file:
    expected = frame.copy()
    return expected


def write_incidents(path: Path) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    start = datetime(2026, 1, 1)
    rows = []
    for i in range(400):
        opened = start + timedelta(hours=int(rng.integers(0, 24 * 300)))
        rows.append([opened.strftime("%Y-%m-%d %H:%M"), rng.choice(["P1", "P2", "P3", "P4"], p=[.05, .15, .4, .4]),
                     rng.choice(["Network", "Billing", "Access", "Hardware"]), round(float(rng.gamma(2, 6)), 1),
                     rng.choice(["Closed", "Open"], p=[.85, .15])])
    frame = pd.DataFrame(rows, columns=["Opened", "Priority", "Category", "Resolution hours", "Status"])
    frame.to_csv(path, index=False, sep=";")
    frame["Opened"] = pd.to_datetime(frame["Opened"])
    return frame


def write_budget(path: Path) -> pd.DataFrame:
    frame = pd.DataFrame({
        "Workstream": ["Core network", "Core network", "IT", "IT", "Retail", "Retail"],
        "Quarter end": [date(2026, 3, 31), date(2026, 6, 30)] * 3,
        "Planned": [1_200_000, 1_300_000, 400_000, 420_000, 250_000, 260_000],
        "Actual": [1_150_000, 1_420_000, 380_000, 455_000, 240_000, 300_000],
    })
    wb = XLWorkbook()
    ws = wb.active
    ws.title = "Budget"
    ws.append(list(frame.columns))
    for row in frame.itertuples(index=False):
        ws.append(list(row))
    wb.create_sheet("Empty")
    wb.create_sheet("Headings only").append(["Item", "Owner"])
    notes = wb.create_sheet("Notes")
    notes.append(["Note"])
    notes.append(["All figures are synthetic."])
    wb.save(path)
    return frame


@pytest.fixture
def uploads(tmp_path):
    root = tmp_path / "uploads"
    (root / ALICE).mkdir(parents=True)
    (root / BOB).mkdir()
    expected = {
        "sales": write_sales(root / ALICE / "1111aaaa-0000-4000-8000-000000000001__sales.xlsx"),
        "incidents": write_incidents(root / ALICE / "2222bbbb-0000-4000-8000-000000000002__incidents.csv"),
        "budget": write_budget(root / ALICE / "3333cccc-0000-4000-8000-000000000003__budget.xlsx"),
    }
    return root, expected


def book(root, name, **limits):
    src = LocalUploadsSource(root, InsightLimits(**limits)).open_for(ALICE, name)
    return read_workbook(src, InsightLimits(**limits))


def run(root, name, analyses, **extra):
    return analyse(book(root, name), parse_request({"file": name, "analyses": analyses, **extra}, 8))["results"]


def rows_to_dict(result, value_index=1):
    return {r[0]: r[value_index] for r in result["table"]["rows"]}


def r2(x):
    return round(float(x), 2)


# -- inspect ------------------------------------------------------------------------------------------------


def test_inspect_finds_header_types_and_quality_issues(uploads):
    root, _ = uploads
    info = describe(book(root, "sales.xlsx"))["sheets"][0]
    assert info["header_row"] == 3 and info["rows"] == 362
    types = {c["name"]: c["type"] for c in info["columns"]}
    assert types == {"Month": "date", "Region": "text", "Product": "text", "Units": "number", "Revenue": "number"}
    revenue = next(c for c in info["columns"] if c["name"] == "Revenue")
    assert revenue["blank"] == 3 and revenue["read_from_text"] == 1 and revenue["outliers"] >= 1
    quality = " ".join(info["data_quality"])
    assert "2 row(s) are exact duplicates" in quality and "'Revenue' has 3 blank" in quality


def test_inspect_skips_empty_sheets_and_reports_headings_only(uploads):
    root, _ = uploads
    info = describe(book(root, "budget.xlsx"))
    names = [s["sheet"] for s in info["sheets"]]
    assert names == ["Budget", "Headings only", "Notes"]  # "Empty" is not listed
    headings = next(s for s in info["sheets"] if s["sheet"] == "Headings only")
    assert headings["rows"] == 0 and "no data rows" in headings["data_quality"][0]


def test_csv_with_semicolons_and_datetime_text(uploads):
    root, _ = uploads
    info = describe(book(root, "incidents.csv"))["sheets"][0]
    assert info["rows"] == 400
    assert {c["name"]: c["type"] for c in info["columns"]}["Opened"] == "date"


# -- analyses vs pandas ---------------------------------------------------------------------------------------


def test_group_summary_sum_and_average_match_pandas(uploads):
    root, exp = uploads
    sales = exp["sales"]
    res = run(root, "sales.xlsx", [{"type": "group_summary", "group_by": "Region", "measure": "Revenue", "agg": "sum"},
                                   {"type": "group_summary", "group_by": "Product", "measure": "Units", "agg": "average"}])
    want = sales.dropna(subset=["Revenue"]).groupby("Region")["Revenue"].sum()
    assert rows_to_dict(res[0]) == {k: r2(v) for k, v in want.items()}
    assert res[0]["rows_used"] == 359 and res[0]["rows_left_out"] == {"blank Revenue": 3}
    assert [r[0] for r in res[0]["table"]["rows"]] == list(want.sort_values(ascending=False).index)
    assert rows_to_dict(res[1]) == {k: r2(v) for k, v in sales.groupby("Product")["Units"].mean().items()}


def test_time_trend_by_month_and_quarter_match_pandas(uploads):
    root, exp = uploads
    sales = exp["sales"].dropna(subset=["Revenue"])
    res = run(root, "sales.xlsx", [{"type": "time_trend", "date_column": "Month", "measure": "Revenue", "period": "month"},
                                   {"type": "time_trend", "date_column": "Month", "measure": "Units", "period": "quarter", "agg": "sum"}])
    want = sales.groupby(sales["Month"].dt.strftime("%Y-%m"))["Revenue"].sum()
    assert rows_to_dict(res[0]) == {k: r2(v) for k, v in want.items()}
    q = exp["sales"].groupby(exp["sales"]["Month"].dt.to_period("Q"))["Units"].sum()
    assert rows_to_dict(res[1]) == {f"{p.year}-Q{p.quarter}": r2(v) for p, v in q.items()}


def test_top_and_bottom_n_match_pandas(uploads):
    root, exp = uploads
    sales = exp["sales"].dropna(subset=["Revenue"])
    res = run(root, "sales.xlsx", [{"type": "top_n", "group_by": "Region", "measure": "Revenue", "n": 3},
                                   {"type": "top_n", "group_by": "Product", "measure": "Revenue", "n": 2, "order": "bottom"}])
    totals = sales.groupby("Region")["Revenue"].sum().sort_values(ascending=False).head(3)
    assert res[0]["table"]["rows"] == [[k, r2(v)] for k, v in totals.items()]
    bottom = sales.groupby("Product")["Revenue"].sum().sort_values().head(2)
    assert res[1]["table"]["rows"] == [[k, r2(v)] for k, v in bottom.items()]


def test_share_of_total_matches_pandas_and_adds_up(uploads):
    root, exp = uploads
    sales = exp["sales"].dropna(subset=["Revenue"])
    res = run(root, "sales.xlsx", [{"type": "share_of_total", "group_by": "Region", "measure": "Revenue"}])[0]
    totals = sales.groupby("Region")["Revenue"].sum()
    shares = {r[0]: r[2] for r in res["table"]["rows"]}
    assert shares == {k: round(100 * v / totals.sum(), 1) for k, v in totals.items()}
    assert res["total"] == r2(totals.sum())
    assert abs(sum(shares.values()) - 100) < 0.6


def test_period_change_previous_and_year_ago_match_pandas(uploads):
    root, exp = uploads
    sales = exp["sales"].dropna(subset=["Revenue"])
    monthly = sales.groupby(sales["Month"].dt.strftime("%Y-%m"))["Revenue"].sum()
    res = run(root, "sales.xlsx", [{"type": "period_change", "date_column": "Month", "measure": "Revenue", "period": "month"},
                                   {"type": "period_change", "date_column": "Month", "measure": "Revenue", "period": "month", "compare": "year_ago"}])
    prev = res[0]["table"]["rows"]
    assert len(prev) == len(monthly) - 1
    row = next(r for r in prev if r[0] == "2026-03")
    assert row[2] == "2026-02" and row[4] == r2(monthly["2026-03"] - monthly["2026-02"])
    assert row[5] == round(100 * (monthly["2026-03"] - monthly["2026-02"]) / monthly["2026-02"], 1)
    year_ago = {r[0]: r for r in res[1]["table"]["rows"]}
    assert set(year_ago) == {f"2026-0{m}" for m in range(1, 7)}
    assert year_ago["2026-06"][2] == "2025-06" and year_ago["2026-06"][4] == r2(monthly["2026-06"] - monthly["2025-06"])


def test_count_without_measure_and_text_distribution(uploads):
    root, exp = uploads
    inc = exp["incidents"]
    res = run(root, "incidents.csv", [{"type": "group_summary", "group_by": "Priority", "agg": "count"},
                                      {"type": "distribution", "column": "Category"}])
    assert rows_to_dict(res[0]) == {k: int(v) for k, v in inc.groupby("Priority").size().items()}
    assert rows_to_dict(res[1]) == {k: int(v) for k, v in inc["Category"].value_counts().items()}


def test_number_distribution_bins_cover_every_row(uploads):
    root, exp = uploads
    res = run(root, "incidents.csv", [{"type": "distribution", "column": "Resolution hours", "bins": 6}])[0]
    assert len(res["table"]["rows"]) == 6
    assert sum(r[1] for r in res["table"]["rows"]) == len(exp["incidents"])


def test_filters_apply_before_aggregating(uploads):
    root, exp = uploads
    inc = exp["incidents"]
    res = run(root, "incidents.csv", [{"type": "group_summary", "group_by": "Category", "measure": "Resolution hours", "agg": "average"}],
              filters=[{"column": "Status", "op": "eq", "value": "closed"},
                       {"column": "Opened", "op": "between", "value": ["2026-03-01", "2026-06-30"]}])[0]
    sel = inc[(inc["Status"] == "Closed") & inc["Opened"].between(pd.Timestamp("2026-03-01"), pd.Timestamp("2026-06-30"))]
    assert rows_to_dict(res) == {k: r2(v) for k, v in sel.groupby("Category")["Resolution hours"].mean().items()}
    assert res["rows_used"] == len(sel)


def test_budget_sheet_by_name_with_variance_inputs(uploads):
    root, exp = uploads
    res = run(root, "budget.xlsx", [{"type": "group_summary", "group_by": "Workstream", "measure": "Actual"}], sheet="Budget")[0]
    assert rows_to_dict(res) == {k: r2(v) for k, v in exp["budget"].groupby("Workstream")["Actual"].sum().items()}


# -- bad input -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("analysis,message", [
    ({"type": "group_summary", "group_by": "Area", "measure": "Revenue"}, "no column 'Area'"),
    ({"type": "group_summary", "group_by": "Region", "measure": "Product"}, "must be a number column"),
    ({"type": "time_trend", "date_column": "Region", "measure": "Revenue"}, "must be a date column"),
    ({"type": "group_summary", "group_by": "Region"}, "Give a measure"),
    ({"type": "pivot", "group_by": "Region"}, "not valid"),
    ({"type": "top_n", "group_by": "Region", "measure": "Revenue", "n": 500}, "not valid"),
])
def test_clear_errors_for_bad_requests(uploads, analysis, message):
    root, _ = uploads
    with pytest.raises(ToolError, match=message):
        run(root, "sales.xlsx", [analysis])


def test_several_sheets_require_a_sheet_name(uploads):
    root, _ = uploads
    with pytest.raises(ToolError, match="several sheets"):
        run(root, "budget.xlsx", [{"type": "group_summary", "group_by": "Workstream", "measure": "Actual"}])


def test_headings_only_sheet_says_not_enough_data(uploads):
    root, _ = uploads
    res = run(root, "budget.xlsx", [{"type": "distribution", "column": "Item"}], sheet="Headings only")[0]
    assert res["rows_used"] == 0 and "Not enough data" in res["note"]


def test_row_column_and_analysis_limits(uploads):
    root, _ = uploads
    with pytest.raises(ToolError, match="more than 100 rows"):
        book(root, "sales.xlsx", max_rows=100)
    with pytest.raises(ToolError, match="more than 3 columns"):
        book(root, "sales.xlsx", max_columns=3)
    with pytest.raises(ToolError, match="at most 2 analyses"):
        parse_request({"file": "x", "analyses": [{"type": "distribution", "column": "a"}] * 3}, 2)


def test_mixed_text_and_numbers_are_flagged_and_treated_as_text(tmp_path):
    (tmp_path / ALICE).mkdir()
    (tmp_path / ALICE / "1111aaaa-0000-4000-8000-000000000001__mixed.csv").write_text(
        "Site,Value\n" + "".join(f"S{i},{i}\n" for i in range(10)) + "S10,n/a\nS11,pending\n")
    info = describe(read_workbook(LocalUploadsSource(tmp_path, LIMITS).open_for(ALICE, "mixed.csv"), LIMITS))["sheets"][0]
    assert {c["name"]: c["type"] for c in info["columns"]}["Value"] == "text"
    assert any("mixes text with numbers" in q for q in info["data_quality"])


# -- through the tools (child process, saved runs, owner isolation) ------------------------------------------------


class _Settings:
    def __init__(self, uploads_dir, data_dir, limits=LIMITS):
        self.uploads_dir, self.data_dir, self.insight_limits = uploads_dir, data_dir, limits


def ctx(root, tmp_path, user=ALICE, limits=LIMITS):
    return ToolContext(settings=_Settings(root, tmp_path / "data", limits), store=None, identity=Identity(user_id=user))


def test_tools_return_json_and_save_the_run_for_its_owner(uploads, tmp_path):
    root, exp = uploads
    out = asyncio.run(analyse_workbook(ctx(root, tmp_path), {"file": "sales.xlsx", "analyses": [
        {"type": "group_summary", "group_by": "Region", "measure": "Revenue"}]}))
    text = out[0].text
    assert text.startswith("Computed results. Quote ONLY these numbers")
    result = json.loads(text.split("\n", 1)[1])
    saved = load_run(tmp_path / "data", ALICE, result["run_id"])
    assert saved["results"][0]["table"] == result["results"][0]["table"]
    with pytest.raises(ToolError, match="Unknown analysis run"):
        load_run(tmp_path / "data", BOB, result["run_id"])
    inspect = asyncio.run(inspect_workbook(ctx(root, tmp_path), {"file": "budget.xlsx"}))
    assert '"sheet": "Budget"' in inspect[0].text


def test_a_second_user_cannot_analyse_another_users_upload(uploads, tmp_path):
    root, _ = uploads
    with pytest.raises(ToolError, match="No uploaded file named 'sales.xlsx' was found for you"):
        asyncio.run(analyse_workbook(ctx(root, tmp_path, user=BOB), {"file": "sales.xlsx", "analyses": [
            {"type": "distribution", "column": "Region"}]}))


def test_time_limit_stops_the_child(uploads, tmp_path, monkeypatch):
    root, _ = uploads
    import office_mcp.tools.insights_tool as tool

    # A worker that never finishes stands in for a pathological sheet; a 1 s budget must stop it.
    monkeypatch.setattr(tool, "_inspect_worker", _sleepy_worker)
    with pytest.raises(ToolError, match="longer than 1 s"):
        asyncio.run(inspect_workbook(ctx(root, tmp_path, limits=replace(LIMITS, timeout_s=1)), {"file": "sales.xlsx"}))


def _sleepy_worker(src, limits):
    import time

    time.sleep(10)
    return {}
