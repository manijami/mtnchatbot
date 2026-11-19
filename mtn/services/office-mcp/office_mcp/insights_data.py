"""Excel insights: read an uploaded workbook or CSV into tables, within limits, and describe it.

No model-written code runs: this module reads cell values only (openpyxl ``data_only``, no macros)
and infers column types. Every number reported later comes from these tables.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd
from openpyxl import load_workbook

from .errors import ToolError
from .files import InsightLimits, SourceFile

TYPE_NUMBER, TYPE_DATE, TYPE_TEXT, TYPE_BOOL, TYPE_EMPTY = "number", "date", "text", "true/false", "empty"
_NUMERIC_TEXT = re.compile(r"^\s*(?:R|ZAR)?\s*[-+]?\d{1,3}(?:[ ,]\d{3})*(?:\.\d+)?\s*$|^\s*(?:R|ZAR)?\s*[-+]?\d+(?:\.\d+)?\s*$")
_PERCENT_TEXT = re.compile(r"^\s*[-+]?\d+(?:\.\d+)?\s*%\s*$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?$")
MIXED_SHARE = 0.95  # a column is one type when at least 95% of its filled cells are that type


@dataclass
class Sheet:
    name: str
    frame: pd.DataFrame
    types: dict[str, str]
    notes: list[str] = field(default_factory=list)
    converted: dict[str, int] = field(default_factory=dict)  # column -> text cells read as numbers
    header_row: int = 1
    blank_rows_dropped: int = 0


@dataclass
class Workbook:
    name: str
    sheets: list[Sheet]
    skipped_sheets: list[str] = field(default_factory=list)

    def sheet(self, name: str | None) -> Sheet:
        if not self.sheets:
            raise ToolError(f"'{self.name}' has no sheet with data.")
        if name is None:
            if len(self.sheets) == 1:
                return self.sheets[0]
            names = ", ".join(f"'{s.name}'" for s in self.sheets)
            raise ToolError(f"'{self.name}' has several sheets ({names}); say which one to analyse.")
        for sheet in self.sheets:
            if sheet.name.strip().lower() == name.strip().lower():
                return sheet
        names = ", ".join(f"'{s.name}'" for s in self.sheets)
        raise ToolError(f"There is no sheet '{name}' in '{self.name}'. Sheets: {names}.")


# -- reading ---------------------------------------------------------------------------------------


def read_workbook(src: SourceFile, limits: InsightLimits) -> Workbook:
    if src.suffix == ".csv":
        sheet = _from_rows(src.name.rsplit(".", 1)[0], _csv_rows(src, limits), limits)
        return Workbook(src.name, [sheet] if sheet is not None else [])
    try:
        book = load_workbook(src.path, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many types for damaged files
        raise ToolError(f"'{src.name}' could not be opened as an Excel workbook.") from exc
    try:
        names = [ws.title for ws in book.worksheets]
        sheets, skipped = [], names[limits.max_sheets:]
        for ws in book.worksheets[: limits.max_sheets]:
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i > limits.max_rows + 20:  # header search room + one extra row to detect "too many"
                    break
                rows.append(list(row[: limits.max_columns + 1]))
            sheet = _from_rows(ws.title, rows, limits)
            if sheet is not None:
                sheets.append(sheet)
        return Workbook(src.name, [s for s in sheets if s is not None], skipped)
    finally:
        book.close()


def _csv_rows(src: SourceFile, limits: InsightLimits) -> list[list]:
    raw = src.path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ToolError(f"'{src.name}' is not readable text.")
    sample = text[:65536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = []
    for i, row in enumerate(csv.reader(io.StringIO(text), dialect)):
        if i > limits.max_rows + 20:
            break
        rows.append([cell if cell.strip() != "" else None for cell in row[: limits.max_columns + 1]])
    return rows


def _from_rows(name: str, rows: list[list], limits: InsightLimits) -> Sheet | None:
    numbered = [(i + 1, r) for i, r in enumerate(rows) if any(_filled(v) for v in r)]  # keep sheet row numbers
    blank_rows = len(rows) - len(numbered)
    rows = [r for _, r in numbered]
    if not rows:
        return None  # an empty sheet is simply not listed
    width = max(len(r) for r in rows)
    if width > limits.max_columns:
        raise ToolError(f"Sheet '{name}' has more than {limits.max_columns} columns; the limit is {limits.max_columns}.")
    header_index = _header_index(rows)
    header = _header_names(rows[header_index], width)
    body = [list(r) + [None] * (width - len(r)) for r in rows[header_index + 1:]]
    if len(body) > limits.max_rows:
        raise ToolError(
            f"Sheet '{name}' has more than {limits.max_rows:,} rows; the limit is {limits.max_rows:,}. "
            "Upload a filtered or summarised copy."
        )
    sheet = Sheet(name=name, frame=pd.DataFrame(body, columns=header), types={},
                  header_row=numbered[header_index][0], blank_rows_dropped=blank_rows)
    if not body:
        sheet.notes.append("The sheet has headings but no data rows.")
    _type_columns(sheet)
    return sheet


def _filled(value) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def _header_index(rows: list[list]) -> int:
    """The first row (of the first 10) where at least half of the filled cells are text."""
    for i, row in enumerate(rows[:10]):
        filled = [v for v in row if _filled(v)]
        if filled and sum(isinstance(v, str) for v in filled) * 2 >= len(filled) and len(filled) >= max(1, len(row) // 2):
            return i
    return 0


def _header_names(row: list, width: int) -> list[str]:
    names, seen = [], {}
    for i in range(width):
        raw = row[i] if i < len(row) else None
        base = str(raw).strip() if _filled(raw) else f"Column {i + 1}"
        count = seen.get(base.lower(), 0)
        seen[base.lower()] = count + 1
        names.append(base if count == 0 else f"{base} ({count + 1})")
    return names


# -- types ------------------------------------------------------------------------------------------


def _cell_type(value) -> str:
    if not _filled(value):
        return TYPE_EMPTY
    if isinstance(value, bool):
        return TYPE_BOOL
    if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
        return TYPE_NUMBER
    if isinstance(value, (datetime, date)):
        return TYPE_DATE
    text = str(value).strip()
    if _NUMERIC_TEXT.match(text) or _PERCENT_TEXT.match(text):
        return "numeric text"
    if _ISO_DATE.match(text):
        return "date text"
    if text.lower() in ("true", "false", "yes", "no"):
        return TYPE_BOOL
    return TYPE_TEXT


def _to_number(value):
    if isinstance(value, bool) or not _filled(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if _PERCENT_TEXT.match(text):
        return float(text.replace("%", "").strip()) / 100
    if _NUMERIC_TEXT.match(text):
        cleaned = re.sub(r"^(?:R|ZAR)", "", text).replace(" ", "").replace(",", "")
        return float(cleaned)
    return None


def _to_date(value):
    if isinstance(value, datetime):
        return pd.Timestamp(value)
    if isinstance(value, date):
        return pd.Timestamp(value)
    if _filled(value) and _ISO_DATE.match(str(value).strip()):
        return pd.Timestamp(str(value).strip())
    return None


def _type_columns(sheet: Sheet) -> None:
    frame = sheet.frame
    for column in list(frame.columns):
        kinds = [_cell_type(v) for v in frame[column]]
        filled = [k for k in kinds if k != TYPE_EMPTY]
        if not filled:
            sheet.types[column] = TYPE_EMPTY
            continue
        numeric = sum(k in (TYPE_NUMBER, "numeric text") for k in filled)
        dates = sum(k in (TYPE_DATE, "date text") for k in filled)
        bools = sum(k == TYPE_BOOL for k in filled)
        share = max(numeric, dates, bools, len(filled) - numeric - dates - bools) / len(filled)
        if numeric / len(filled) >= MIXED_SHARE:
            sheet.types[column] = TYPE_NUMBER
            converted = sum(k == "numeric text" for k in filled)
            if converted:
                sheet.converted[column] = converted
            frame[column] = pd.to_numeric(frame[column].map(_to_number), errors="coerce")
        elif dates / len(filled) >= MIXED_SHARE:
            sheet.types[column] = TYPE_DATE
            frame[column] = pd.to_datetime(frame[column].map(_to_date), errors="coerce")
        elif bools / len(filled) >= MIXED_SHARE:
            sheet.types[column] = TYPE_BOOL
        else:
            sheet.types[column] = TYPE_TEXT
            if share < MIXED_SHARE and (numeric or dates):
                sheet.notes.append(
                    f"Column '{column}' mixes text with numbers or dates ({numeric} numeric, {dates} dates, "
                    f"{len(filled) - numeric - dates} other); it is treated as text."
                )
            frame[column] = frame[column].map(lambda v: str(v).strip() if _filled(v) else None)


# -- inspect -------------------------------------------------------------------------------------------


def _number(value, places: int = 2):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    return round(float(value), places)


def describe(book: Workbook) -> dict:
    sheets = []
    for sheet in book.sheets:
        frame = sheet.frame
        columns = []
        for column in frame.columns:
            series = frame[column]
            kind = sheet.types[column]
            info = {"name": column, "type": kind, "filled": int(series.notna().sum()), "blank": int(series.isna().sum()),
                    "distinct": int(series.nunique(dropna=True))}
            if kind == TYPE_NUMBER and info["filled"]:
                q1, q3 = series.quantile(0.25), series.quantile(0.75)
                spread = q3 - q1
                outliers = int(((series < q1 - 1.5 * spread) | (series > q3 + 1.5 * spread)).sum()) if spread > 0 else 0
                info.update(min=_number(series.min()), max=_number(series.max()), total=_number(series.sum()),
                            average=_number(series.mean()), outliers=outliers)
                if column in sheet.converted:
                    info["read_from_text"] = sheet.converted[column]
            elif kind == TYPE_DATE and info["filled"]:
                info.update(first=series.min().date().isoformat(), last=series.max().date().isoformat())
            elif kind == TYPE_TEXT and info["filled"]:
                info["examples"] = [str(v)[:40] for v in series.dropna().unique()[:3]]
            columns.append(info)
        duplicates = int(frame.duplicated().sum()) if len(frame) else 0
        quality = list(sheet.notes)
        if duplicates:
            quality.append(f"{duplicates} row(s) are exact duplicates of another row.")
        for info in columns:
            if info["filled"] and info["blank"]:
                quality.append(f"Column '{info['name']}' has {info['blank']} blank cell(s).")
            if info.get("outliers"):
                quality.append(f"Column '{info['name']}' has {info['outliers']} unusually high or low value(s).")
            if info.get("read_from_text"):
                quality.append(f"Column '{info['name']}': {info['read_from_text']} value(s) were typed as text and read as numbers.")
        sheets.append({"sheet": sheet.name, "header_row": sheet.header_row, "rows": int(len(frame)),
                       "columns": columns, "duplicate_rows": duplicates, "data_quality": quality})
    result = {"file": book.name, "sheets": sheets}
    if book.skipped_sheets:
        result["not_read"] = {"sheets": book.skipped_sheets, "reason": "over the sheet limit"}
    if not sheets:
        result["data_quality"] = ["No sheet contains data."]
    return result
