"""Builds an MTN workbook from a validated :class:`WorkbookSpec`, and checks its formulas.

Layout per sheet: title (row 1), classification line (row 2), header (row 4), data, an optional
total row, and an optional formula-driven summary block plus native chart to the right. The data
range is a real Excel table (filters, banding) with MTN header styling, frozen header, typed
number formats, dropdown validation and conditional formatting.
"""

from __future__ import annotations

import datetime as dt
import io
import re
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.chart.series import DataPoint
from openpyxl.chart.text import RichText, Text
from openpyxl.chart.title import Title
from openpyxl.drawing.text import CharacterProperties, Font as DrawingFont, Paragraph, ParagraphProperties, RegularTextRun
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

from . import brand
from .schemas import WorkbookSpec, SheetSpec
from .templates import Template

TITLE_ROW, NOTE_ROW, HEADER_ROW = 1, 2, 4
FIRST_DATA_ROW = HEADER_ROW + 1
ERROR_VALUES = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!", "Err:", "#ERR")
NUMBER_FORMATS = {
    "number": "#,##0.##########",
    "integer": "#,##0",
    "currency": "#,##0.00",
    "percent": "0%",
    "date": "yyyy-mm-dd",
}
STYLES = {
    "good": ("C6EFCE", "006100"),
    "warning": ("FFEB9C", "9C5700"),
    "bad": ("FFC7CE", "9C0006"),
    "highlight": (brand.TINT, brand.BLACK),
}
OPERATORS = {
    "equal": "equal",
    "not_equal": "notEqual",
    "greater_than": "greaterThan",
    "less_than": "lessThan",
    "greater_or_equal": "greaterThanOrEqual",
    "less_or_equal": "lessThanOrEqual",
}
CHART_COLOURS = (brand.YELLOW, brand.BLACK, "808080", "C9A400")
_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


def _sheet_ref(title: str) -> str:
    return title if re.fullmatch(r"[A-Za-z0-9_]+", title) else "'" + title.replace("'", "''") + "'"


class CellError(ValueError):
    """A data cell that does not match its column type; the message names the cell."""


def _coerce(value, kind: str, where: str):
    if value is None or value == "":
        return None
    if kind == "text":
        return str(value)
    if kind == "date":
        try:
            return dt.date.fromisoformat(str(value)[:10])
        except ValueError:
            raise CellError(f"{where}: '{value}' is not a date; use YYYY-MM-DD") from None
    if kind == "percent" and isinstance(value, str) and value.strip().endswith("%"):
        value = value.strip()[:-1]
        try:
            return float(value.replace(",", "")) / 100
        except ValueError:
            raise CellError(f"{where}: '{value}%' is not a percentage") from None
    if isinstance(value, bool):
        raise CellError(f"{where}: expected a number, got {value}")
    if isinstance(value, (int, float)):
        return int(value) if kind == "integer" else value
    try:
        number = float(str(value).replace(",", "").strip())
    except ValueError:
        raise CellError(f"{where}: '{value}' is not a number") from None
    return int(number) if kind == "integer" else number


def _formula(template: str, letters: dict[str, str], row: int) -> str:
    def replace(match):
        name = match.group(1)
        return str(row) if name == "row" else f"{letters[name]}{row}"

    return _PLACEHOLDER.sub(replace, template)


def _width(values) -> float:
    longest = max((len(str(v)) for v in values if v is not None), default=8)
    return max(9.0, min(48.0, longest * 1.1 + 2))


PIE_COLOURS = (*CHART_COLOURS, "B3B3B3", "FFE680", "595959", "E6B800")


def _chars(size_hundredths: int, bold: bool = False) -> CharacterProperties:
    """Chart text in the MTN font (Arial metrics where it is not installed), never the theme default."""
    return CharacterProperties(latin=DrawingFont(typeface=brand.FONT), sz=size_hundredths, b=bold, solidFill=brand.INK)


def _rich(size_hundredths: int) -> RichText:
    props = _chars(size_hundredths)
    return RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=props), endParaRPr=props)])


def _title(text: str) -> Title:
    props = _chars(1200, bold=True)
    paragraph = Paragraph(pPr=ParagraphProperties(defRPr=props), r=[RegularTextRun(rPr=props, t=text)])
    return Title(tx=Text(rich=RichText(p=[paragraph])), overlay=False)


def _colour_series(chart, kind: str, points: int) -> None:
    for i, series in enumerate(chart.series):
        colour = CHART_COLOURS[i % len(CHART_COLOURS)]
        if kind == "pie":
            for index in range(points):
                point = DataPoint(idx=index)
                point.graphicalProperties.solidFill = PIE_COLOURS[index % len(PIE_COLOURS)]
                point.graphicalProperties.line.solidFill = "FFFFFF"
                series.dPt.append(point)
        elif kind == "line":
            series.graphicalProperties.line.solidFill = colour
            series.graphicalProperties.line.width = 28000
            series.smooth = False
        else:
            series.graphicalProperties.solidFill = colour
            series.graphicalProperties.line.solidFill = colour


def _make_chart(kind: str, title: str | None):
    if kind in ("bar", "column"):
        chart = BarChart()
        chart.type = "bar" if kind == "bar" else "col"
        chart.gapWidth = 80
    elif kind == "line":
        chart = LineChart()
    else:
        chart = PieChart()
    if title:
        chart.title = _title(title)
    chart.height, chart.width = 7.5, 13.0
    chart.style = 2
    if kind != "pie":
        for axis in (chart.x_axis, chart.y_axis):
            axis.delete = False  # openpyxl 3.1 hides axes in current Excel unless told otherwise
            axis.txPr = _rich(900)
    return chart


def _sheet(workbook, sheet_spec: SheetSpec, title: str, logo: bytes | None, first: bool) -> dict:
    ws = workbook.active if first else workbook.create_sheet()
    ws.title = sheet_spec.name
    columns = sheet_spec.columns
    letters = {c.name: get_column_letter(i + 1) for i, c in enumerate(columns)}
    last_col = get_column_letter(len(columns))
    n_rows = len(sheet_spec.rows)
    last_row = HEADER_ROW + max(n_rows, 1)

    ws.cell(TITLE_ROW, 1, title).style = "MTN Title"
    ws.cell(NOTE_ROW, 1, f"{brand.CLASSIFICATION} · {sheet_spec.name}").style = "MTN Subtitle"
    ws.row_dimensions[TITLE_ROW].height = 30
    for i, column in enumerate(columns, start=1):
        cell = ws.cell(HEADER_ROW, i, column.name)
        cell.style = "MTN Header"
    ws.row_dimensions[HEADER_ROW].height = 30

    for r, row in enumerate(sheet_spec.rows):
        excel_row = FIRST_DATA_ROW + r
        for c, (column, value) in enumerate(zip(columns, row), start=1):
            cell = ws.cell(excel_row, c)
            cell.style = "MTN Cell"
            if column.formula:
                cell.value = _formula(column.formula, letters, excel_row)
            else:
                where = f"sheets['{sheet_spec.name}'].rows[{r}][{c - 1}] ({column.name})"
                cell.value = _coerce(value, column.type, where)
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    # Text that looks like a formula stays text: openpyxl would otherwise store it as
                    # a live formula (formula injection from user data, e.g. "=HYPERLINK(...)").
                    cell.data_type = "s"
            if column.type in NUMBER_FORMATS:
                cell.number_format = NUMBER_FORMATS[column.type]
                cell.alignment = Alignment(vertical="top", horizontal="right")

    for i, column in enumerate(columns, start=1):
        values = [column.name, *(row[i - 1] for row in sheet_spec.rows)]
        width = 14 if column.formula else _width(values)
        if column.type in ("number", "integer", "currency", "percent") or column.formula:
            width = max(width, 15)  # room for totals such as 1,155,000.00 in bold
        ws.column_dimensions[get_column_letter(i)].width = width

    if n_rows:
        table = Table(displayName=f"T_{re.sub(r'[^A-Za-z0-9]', '_', sheet_spec.name)}_{len(workbook.sheetnames)}",
                      ref=f"A{HEADER_ROW}:{last_col}{last_row}")
        table.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
        ws.add_table(table)

    for column in columns:
        if column.allowed_values:
            joined = ",".join(v.replace(",", " ") for v in column.allowed_values)
            if len(joined) <= 250:
                validation = DataValidation(type="list", formula1=f'"{joined}"', allow_blank=True)
                validation.error = f"Choose one of: {', '.join(column.allowed_values)}"
                validation.showErrorMessage = True
                ws.add_data_validation(validation)
                letter = letters[column.name]
                validation.add(f"{letter}{FIRST_DATA_ROW}:{letter}{max(last_row, FIRST_DATA_ROW + 200)}")

    for rule in sheet_spec.conditional_formats:
        letter = letters[rule.column]
        area = f"{letter}{FIRST_DATA_ROW}:{letter}{last_row}"
        fill_hex, font_hex = STYLES[rule.style]
        fill = PatternFill("solid", start_color=fill_hex, end_color=fill_hex)
        font = Font(color=font_hex, bold=rule.style != "highlight")
        value = rule.value
        literal = value if isinstance(value, (int, float)) else '"' + str(value).replace('"', '""') + '"'
        if rule.operator == "contains":
            formula = f'ISNUMBER(SEARCH({literal},{letter}{FIRST_DATA_ROW}))'
            ws.conditional_formatting.add(area, FormulaRule(formula=[formula], fill=fill, font=font))
        else:
            ws.conditional_formatting.add(
                area, CellIsRule(operator=OPERATORS[rule.operator], formula=[str(literal)], fill=fill, font=font)
            )

    total_row = None
    if sheet_spec.totals and n_rows:
        total_row = last_row + 1
        ws.cell(total_row, 1, "Total").style = "MTN Total"
        for total in sheet_spec.totals:
            letter = letters[total.column]
            col = columns.index(next(c for c in columns if c.name == total.column)) + 1
            function = total.function.upper() if total.function != "count" else "COUNTA"
            cell = ws.cell(total_row, col, f"={function}({letter}{FIRST_DATA_ROW}:{letter}{last_row})")
            cell.style = "MTN Total"
            kind = next(c.type for c in columns if c.name == total.column)
            if kind in NUMBER_FORMATS and total.function != "count":
                cell.number_format = NUMBER_FORMATS[kind]

    summary_ref = None
    if sheet_spec.summary and n_rows:
        summary = sheet_spec.summary
        group_letter = letters[summary.group_by]
        group_index = [c.name for c in columns].index(summary.group_by)
        labels = []
        for row in sheet_spec.rows:
            label = row[group_index]
            if label not in (None, "") and str(label) not in labels:
                labels.append(str(label))
        start_col = len(columns) + 2
        s_letter, v_letter = get_column_letter(start_col), get_column_letter(start_col + 1)
        ws.cell(HEADER_ROW, start_col, summary.group_by).style = "MTN Header"
        heading = "Count" if summary.function == "count" else f"Total {summary.value_column}"
        ws.cell(HEADER_ROW, start_col + 1, heading).style = "MTN Header"
        group_range = f"${group_letter}${FIRST_DATA_ROW}:${group_letter}${last_row}"
        for i, label in enumerate(labels):
            r = FIRST_DATA_ROW + i
            ws.cell(r, start_col, label).style = "MTN Cell"
            if summary.function == "count":
                formula = f"=COUNTIF({group_range},{s_letter}{r})"
            else:
                v = letters[summary.value_column]
                formula = f"=SUMIF({group_range},{s_letter}{r},${v}${FIRST_DATA_ROW}:${v}${last_row})"
            ws.cell(r, start_col + 1, formula).style = "MTN Cell"
        ws.column_dimensions[s_letter].width = _width([summary.group_by, *labels])
        ws.column_dimensions[v_letter].width = 14
        summary_ref = (start_col, FIRST_DATA_ROW, FIRST_DATA_ROW + len(labels) - 1)

    chart_spec = sheet_spec.chart
    if chart_spec and n_rows:
        chart = _make_chart(chart_spec.type, chart_spec.title)
        if chart_spec.source == "summary" and summary_ref:
            col, top, bottom = summary_ref
            data = Reference(ws, min_col=col + 1, min_row=HEADER_ROW, max_row=bottom)
            cats = Reference(ws, min_col=col, min_row=top, max_row=bottom)
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(cats)
            anchor_col = col
            anchor_row = bottom + 3
        else:
            for name in chart_spec.value_columns:
                index = [c.name for c in columns].index(name) + 1
                chart.add_data(Reference(ws, min_col=index, min_row=HEADER_ROW, max_row=last_row), titles_from_data=True)
            cat_index = [c.name for c in columns].index(chart_spec.category_column) + 1
            chart.set_categories(Reference(ws, min_col=cat_index, min_row=FIRST_DATA_ROW, max_row=last_row))
            anchor_col = len(columns) + (5 if summary_ref else 2)
            anchor_row = HEADER_ROW
        if chart_spec.type != "pie" and len(chart.series) == 1:
            chart.legend = None  # one series: the title says what it is
        points = (summary_ref[2] - summary_ref[1] + 1) if (chart_spec.source == "summary" and summary_ref) else n_rows
        _colour_series(chart, chart_spec.type, points)
        if chart.legend is not None:
            chart.legend.txPr = _rich(900)
        ws.add_chart(chart, f"{get_column_letter(anchor_col)}{anchor_row}")

    if logo:
        from openpyxl.drawing.image import Image

        image = Image(io.BytesIO(logo))
        image.width = image.height = 40
        ws.add_image(image, f"{get_column_letter(max(len(columns), 2))}1")

    if sheet_spec.freeze_header:
        ws.freeze_panes = f"A{FIRST_DATA_ROW}"
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{HEADER_ROW}:{HEADER_ROW}"
    ws.oddFooter.left.text = brand.CLASSIFICATION
    ws.oddFooter.right.text = "Page &P of &N"
    formulas = sum(1 for c in columns if c.formula) * n_rows + len(sheet_spec.totals) * bool(total_row)
    if summary_ref:
        formulas += summary_ref[2] - summary_ref[1] + 1
    return {"rows": n_rows, "formulas": formulas, "chart": bool(chart_spec and n_rows)}


def build(spec: WorkbookSpec, template: Template, target: Path, logo: bytes | None) -> dict:
    workbook = load_workbook(template.path)
    stats = {"sheets": len(spec.sheets), "rows": 0, "formulas": 0, "charts": 0}
    for index, sheet_spec in enumerate(spec.sheets):
        result = _sheet(workbook, sheet_spec, spec.title, logo, first=index == 0)
        stats["rows"] += result["rows"]
        stats["formulas"] += result["formulas"]
        stats["charts"] += int(result["chart"])
    workbook.calculation.fullCalcOnLoad = True  # Excel computes every formula when opened
    props = workbook.properties
    props.title = spec.title
    props.subject = template.title
    props.creator = "MTN Employee AI"
    props.description = f"Generated from MTN template {template.name} {template.version}"
    workbook.save(target)
    return stats


def reopen(path: Path) -> dict:
    workbook = load_workbook(path)
    return {"sheets": len(workbook.sheetnames), "tables": sum(len(ws.tables) for ws in workbook.worksheets)}


def recalc_report(original: Path, recalculated: Path) -> dict:
    """Compares formula cells of the original with a LibreOffice-recalculated copy.

    Returns the number of formula cells, how many got a computed value, and every error value as
    'Sheet!A1: #DIV/0!'. Zero computed values for a workbook with formulas means the recalculation
    did not run, which is itself a failure.
    """
    formulas = load_workbook(original)
    values = load_workbook(recalculated, data_only=True)
    report = {"formulas": 0, "computed": 0, "errors": []}
    for ws in formulas.worksheets:
        computed = values[ws.title]
        for row in ws.iter_rows():
            for cell in row:
                is_formula = cell.data_type == "f"
                value = computed[cell.coordinate].value
                if is_formula:
                    report["formulas"] += 1
                    if value not in (None, ""):
                        report["computed"] += 1
                # Only formula results count: "#N/A" typed into a data cell is the user's text.
                if is_formula and isinstance(value, str) and value.startswith(ERROR_VALUES):
                    report["errors"].append(f"{_sheet_ref(ws.title)}!{cell.coordinate}: {value}")
    return report


def scan_errors(recalculated: Path) -> list[str]:
    """Error values in a recalculated workbook, as 'Sheet!A1: #DIV/0!' strings."""
    workbook = load_workbook(recalculated, data_only=True)
    found = []
    for ws in workbook.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                value = cell.value
                if isinstance(value, str) and value.startswith(ERROR_VALUES):
                    found.append(f"{_sheet_ref(ws.title)}!{cell.coordinate}: {value}")
    return found


def formula_count(path: Path) -> int:
    workbook = load_workbook(path)
    return sum(
        1
        for ws in workbook.worksheets
        for row in ws.iter_rows()
        for cell in row
        if cell.data_type == "f"
    )
