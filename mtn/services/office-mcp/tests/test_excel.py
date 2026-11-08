import base64
import io

import pytest
from openpyxl import load_workbook

from .conftest import ALICE, call
from .samples import plan_spec, tracker_spec

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _resource(result):
    return next(c["resource"] for c in result["content"] if c["type"] == "resource")


def _workbook(result):
    return load_workbook(io.BytesIO(base64.b64decode(_resource(result)["blob"])))


def _version(store, result):
    text = result["content"][0]["text"]
    return store.get_document(ALICE, text.split("document_id ")[1].split(".")[0]).latest


def test_action_tracker_has_table_filters_freeze_validation_formatting_summary_and_chart(client, store):
    result = call(client, "create_excel_workbook", tracker_spec())
    assert result["isError"] is False, result
    assert _resource(result)["mimeType"] == XLSX
    ws = _workbook(result)["Actions"]
    assert ws.freeze_panes == "A5"
    [table] = ws.tables.values()
    assert table.ref == "A4:G16"  # header + 12 rows; tables carry the filter buttons
    assert ws["A4"].value == "ID" and ws["A4"].fill.fgColor.rgb.endswith("FFCB05")
    assert ws["D5"].number_format == "yyyy-mm-dd"
    assert ws["G5"].value == '=IF(E5="Done","",D5-DATE(2026,11,8))'
    assert len(ws.data_validations.dataValidation) == 2
    assert sum(len(cf.rules) for cf in ws.conditional_formatting) == 3
    assert ws["J5"].value.startswith("=COUNTIF($E$5:$E$16,I5)")
    assert len(ws._charts) == 1
    version = _version(store, result)
    recalc = version.checks["recalc"]
    assert recalc["errors"] == [] and recalc["formulas"] == 16 and recalc["computed"] >= 13
    assert version.status == "complete"


def test_project_plan_formulas_totals_and_chart_recalculate_to_the_right_values(client, store, tmp_path):
    result = call(client, "create_excel_workbook", plan_spec())
    assert result["isError"] is False, result
    ws = _workbook(result)["Plan"]
    assert ws["E5"].value == "=D5-C5"
    assert ws["G9"].value == "=SUM(G5:G8)" and ws["F9"].value == "=AVERAGE(F5:F8)"
    assert ws["F5"].value == 0.4 and ws["F5"].number_format == "0%"
    assert ws.parent.calculation.fullCalcOnLoad is True
    assert "formulas recalculated with no errors" in result["content"][0]["text"]
    assert _version(store, result).checks["recalc"]["computed"] == 6


def test_formula_errors_block_delivery_and_name_the_cells(client, store):
    spec = plan_spec()
    sheet = spec["sheets"][0]
    sheet["columns"].append({"name": "Cost per day", "type": "formula", "formula": "={Budget}/{% complete}"})
    for row in sheet["rows"]:
        row.append(None)
    result = call(client, "create_excel_workbook", spec)
    assert result["isError"] is True
    message = result["content"][0]["text"]
    assert "Plan!H7: #DIV/0!" in message and "Plan!H8: #DIV/0!" in message and "H6" not in message
    assert not [c for c in result["content"] if c["type"] == "resource"]
    [doc] = store.list_documents(ALICE)
    assert doc.latest.status == "failed" and doc.latest.checks["recalc"]["error_count"] == 2


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda s: s["sheets"][0]["columns"][4].update(formula="=WEBSERVICE(\"http://x\")", type="formula"), "WEBSERVICE is not allowed"),
        (lambda s: s["sheets"][0]["columns"][4].update(formula="=Other!A1", type="formula"), "same sheet"),
        (lambda s: s["sheets"][0]["columns"][4].update(formula="={Finish}-{Start}", type="formula"), "unknown column '{Finish}'"),
        (lambda s: s["sheets"][0]["rows"][0].pop(), "rows[0] has 6 cells"),
        (lambda s: s["sheets"][0].update(name="Plan/2026"), "sheet name"),
        (lambda s: s["sheets"][0]["totals"].append({"column": "Cost"}), "unknown column 'Cost'"),
        (lambda s: s["sheets"][0]["chart"].update(value_columns=["Nope"]), "chart.value_columns"),
        (lambda s: s["sheets"][0]["columns"][2].update(type="formula"), "needs a formula"),
    ],
)
def test_invalid_workbooks_return_fixable_errors(client, store, mutate, expected):
    spec = plan_spec()
    mutate(spec)
    result = call(client, "create_excel_workbook", spec)
    assert result["isError"] is True
    assert expected in result["content"][0]["text"]
    assert store.list_documents(ALICE) == []


def test_bad_cell_values_name_the_cell(client):
    spec = plan_spec()
    spec["sheets"][0]["rows"][2][2] = "next Tuesday"
    result = call(client, "create_excel_workbook", spec)
    assert result["isError"] is True
    assert "rows[2][2] (Start): 'next Tuesday' is not a date" in result["content"][0]["text"]


def test_charts_use_the_mtn_font_and_pie_points_use_mtn_colours(client):
    ws = _workbook(call(client, "create_excel_workbook", tracker_spec()))["Actions"]
    [chart] = ws._charts
    title_run = chart.title.tx.rich.p[0].r[0]
    assert title_run.rPr.latin.typeface == "MTN Brighter Sans"
    def hex_of(fill):
        value = fill if isinstance(fill, str) else fill.srgbClr
        return value if isinstance(value, str) else value.val

    fills = [hex_of(p.graphicalProperties.solidFill) for p in chart.series[0].dPt]
    assert fills[:2] == ["FFCB05", "000000"] and len(fills) == 4


def test_number_columns_are_wide_enough_for_totals(client):
    ws = _workbook(call(client, "create_excel_workbook", plan_spec()))["Plan"]
    assert ws.column_dimensions["G"].width >= 15
