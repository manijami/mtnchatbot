"""Excel insights: a validated analysis spec, computed with pandas. The results are the ONLY numbers
the model may quote. Each result says where it came from: sheet, columns, rows used and left out."""

from __future__ import annotations

from typing import Annotated, Literal, Union

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .errors import ToolError
from .insights_data import TYPE_DATE, TYPE_NUMBER, Sheet, Workbook, _number

MAX_GROUPS = 50
MAX_PERIODS = 400
MAX_BINS = 20
Agg = Literal["sum", "average", "count", "min", "max", "median"]
Period = Literal["day", "week", "month", "quarter", "year"]
_AGG = {"sum": "sum", "average": "mean", "count": "count", "min": "min", "max": "max", "median": "median"}
_FREQ = {"day": "D", "week": "W-MON", "month": "M", "quarter": "Q", "year": "Y"}


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str | None = Field(default=None, max_length=40)
    sheet: str | None = None


class GroupSummary(_Base):
    type: Literal["group_summary"]
    group_by: str
    measure: str | None = None
    agg: Agg = "sum"


class TimeTrend(_Base):
    type: Literal["time_trend"]
    date_column: str
    measure: str | None = None
    period: Period = "month"
    agg: Agg = "sum"


class TopN(_Base):
    type: Literal["top_n"]
    group_by: str
    measure: str | None = None
    n: int = Field(default=5, ge=1, le=MAX_GROUPS)
    order: Literal["top", "bottom"] = "top"
    agg: Agg = "sum"


class ShareOfTotal(_Base):
    type: Literal["share_of_total"]
    group_by: str
    measure: str | None = None


class PeriodChange(_Base):
    type: Literal["period_change"]
    date_column: str
    measure: str | None = None
    period: Period = "month"
    compare: Literal["previous", "year_ago"] = "previous"
    agg: Agg = "sum"


class Distribution(_Base):
    type: Literal["distribution"]
    column: str
    bins: int = Field(default=10, ge=2, le=MAX_BINS)


Analysis = Annotated[Union[GroupSummary, TimeTrend, TopN, ShareOfTotal, PeriodChange, Distribution], Field(discriminator="type")]


class Filter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str
    op: Literal["eq", "ne", "in", "gt", "gte", "lt", "lte", "between"]
    value: str | float | int | bool | list[str | float | int]


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: str
    sheet: str | None = None
    analyses: list[Analysis] = Field(min_length=1)
    filters: list[Filter] = Field(default_factory=list, max_length=10)

    @field_validator("analyses", mode="before")
    @classmethod
    def _one_or_many(cls, value):
        return [value] if isinstance(value, dict) else value


def parse_request(arguments: dict, max_analyses: int) -> Request:
    try:
        request = Request.model_validate(arguments)
    except ValidationError as exc:
        problems = []
        for err in exc.errors()[:6]:
            where = ".".join(str(p) for p in err["loc"] if not isinstance(p, str) or p not in {
                "group_summary", "time_trend", "top_n", "share_of_total", "period_change", "distribution"})
            problems.append(f"{where or 'request'}: {err['msg']}")
        raise ToolError("The analysis request is not valid: " + "; ".join(problems)) from exc
    if len(request.analyses) > max_analyses:
        raise ToolError(f"Ask for at most {max_analyses} analyses per call; this request has {len(request.analyses)}.")
    return request


# -- helpers --------------------------------------------------------------------------------------------


def _column(sheet: Sheet, name: str, *, kind: str | None = None, role: str = "column") -> str:
    lookup = {c.lower(): c for c in sheet.frame.columns}
    real = lookup.get((name or "").strip().lower())
    if real is None:
        names = ", ".join(f"'{c}'" for c in sheet.frame.columns)
        raise ToolError(f"Sheet '{sheet.name}' has no column '{name}'. Columns: {names}.")
    if kind and sheet.types[real] != kind:
        raise ToolError(f"Column '{real}' is {sheet.types[real]}, but the {role} must be a {kind} column.")
    return real


def _apply_filters(sheet: Sheet, frame: pd.DataFrame, filters: list[Filter]) -> tuple[pd.DataFrame, list[str]]:
    described = []
    for f in filters:
        column = _column(sheet, f.column)
        series = frame[column]
        value = f.value
        if sheet.types[column] == TYPE_DATE:
            convert = lambda v: pd.Timestamp(str(v))  # noqa: E731
        elif sheet.types[column] == TYPE_NUMBER:
            convert = float
        else:
            convert = lambda v: str(v).strip().lower()  # noqa: E731
            series = series.map(lambda v: v.lower() if isinstance(v, str) else v)
        try:
            if f.op in ("in", "between"):
                values = [convert(v) for v in (value if isinstance(value, list) else [value])]
            else:
                values = [convert(value)]
        except (TypeError, ValueError) as exc:
            raise ToolError(f"Filter on '{column}': '{value}' does not fit a {sheet.types[column]} column.") from exc
        if f.op == "between" and len(values) != 2:
            raise ToolError(f"Filter on '{column}': 'between' needs two values.")
        mask = {
            "eq": lambda: series == values[0], "ne": lambda: series != values[0], "in": lambda: series.isin(values),
            "gt": lambda: series > values[0], "gte": lambda: series >= values[0], "lt": lambda: series < values[0],
            "lte": lambda: series <= values[0], "between": lambda: series.between(values[0], values[1]),
        }[f.op]()
        frame = frame[mask.fillna(False)]
        described.append(f"{column} {f.op} {value}")
    return frame, described


def _measure(sheet: Sheet, measure: str | None, agg: str) -> str | None:
    if measure is None:
        if agg != "count":
            raise ToolError(f"Give a measure (a number column) for '{agg}', or use agg 'count'.")
        return None
    if agg == "count":
        return _column(sheet, measure)
    return _column(sheet, measure, kind=TYPE_NUMBER, role="measure")


def _aggregate(frame: pd.DataFrame, keys, measure: str | None, agg: str) -> pd.Series:
    grouped = frame.groupby(keys, dropna=True, observed=True)
    if measure is None:
        return grouped.size()
    return grouped[measure].agg(_AGG[agg])


def _label(value) -> str:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return str(value)


def _period_label(ts: pd.Timestamp, period: str) -> str:
    if period == "year":
        return f"{ts.year}"
    if period == "quarter":
        return f"{ts.year}-Q{ts.quarter}"
    if period == "month":
        return f"{ts.year}-{ts.month:02d}"
    if period == "week":
        return f"week of {(ts - pd.Timedelta(days=6)).date().isoformat()}"
    return ts.date().isoformat()


def _title(measure: str | None, agg: str) -> str:
    if measure is None:
        return "Number of rows"
    return {"sum": "Total", "average": "Average", "count": "Count of", "min": "Lowest", "max": "Highest", "median": "Median"}[agg] + f" {measure}"


# -- analyses ---------------------------------------------------------------------------------------------


def run_analysis(sheet: Sheet, base: pd.DataFrame, filters: list[str], analysis, index: int) -> dict:
    a = analysis
    result = {"id": a.id or f"A{index}", "type": a.type, "sheet": sheet.name, "filters": filters}
    frame = base
    excluded: dict[str, int] = {}

    def drop_blank(column: str, why: str):
        nonlocal frame
        blank = int(frame[column].isna().sum())
        if blank:
            excluded[why] = excluded.get(why, 0) + blank
            frame = frame[frame[column].notna()]

    if a.type in ("group_summary", "top_n", "share_of_total"):
        agg = getattr(a, "agg", "sum")
        group = _column(sheet, a.group_by)
        measure = _measure(sheet, a.measure, agg)
        drop_blank(group, f"blank {group}")
        if measure and agg != "count":
            drop_blank(measure, f"blank {measure}")
        values = _aggregate(frame, group, measure, agg).sort_values(ascending=getattr(a, "order", "top") == "bottom")
        if a.type == "top_n":
            values = values.head(a.n)
        groups_total = int(values.shape[0])
        rows = [[_label(k), _number(v)] for k, v in values.head(MAX_GROUPS).items()]
        name = _title(measure, agg)
        result.update(columns_used=[c for c in (group, measure) if c], title=f"{name} by {group}" if a.type != "top_n"
                      else f"{'Top' if a.order == 'top' else 'Bottom'} {a.n} {group} by {name.lower()}",
                      table={"columns": [group, name], "rows": rows})
        if a.type == "share_of_total":
            total = float(values.sum())
            for row, raw in zip(rows, values.head(MAX_GROUPS).values):
                row.append(_number(100 * float(raw) / total, 1) if total else None)
            result["table"]["columns"].append("Share of total (%)")
            result["total"] = _number(total)
        if groups_total > MAX_GROUPS:
            result["note"] = f"Showing the first {MAX_GROUPS} of {groups_total} groups."
    elif a.type in ("time_trend", "period_change"):
        date_col = _column(sheet, a.date_column, kind=TYPE_DATE, role="date column")
        measure = _measure(sheet, a.measure, a.agg)
        drop_blank(date_col, f"blank {date_col}")
        if measure and a.agg != "count":
            drop_blank(measure, f"blank {measure}")
        keys = frame[date_col].dt.to_period(_FREQ[a.period].split("-")[0] if a.period != "week" else "W-SUN").dt.to_timestamp(how="end")
        values = _aggregate(frame.assign(_period=keys), "_period", measure, a.agg).sort_index()
        if len(values) > MAX_PERIODS:
            raise ToolError(f"'{date_col}' spans more than {MAX_PERIODS} {a.period}s; use a longer period.")
        name = _title(measure, a.agg)
        labels = [_period_label(ts, a.period) for ts in values.index]
        if a.type == "time_trend":
            result.update(columns_used=[c for c in (date_col, measure) if c], title=f"{name} by {a.period}",
                          table={"columns": [a.period.capitalize(), name], "rows": [[l, _number(v)] for l, v in zip(labels, values.values)]})
        else:
            lag = 1 if a.compare == "previous" else {"month": 12, "quarter": 4, "year": 1, "week": 52, "day": 365}[a.period]
            by_label = dict(zip(labels, values.values))
            rows = []
            for i, (label, value) in enumerate(zip(labels, values.values)):
                previous_label = _shift_label(values.index[i], a.period, lag)
                if previous_label not in by_label:
                    continue
                prev = float(by_label[previous_label])
                change = float(value) - prev
                rows.append([label, _number(value), previous_label, _number(prev), _number(change),
                             _number(100 * change / prev, 1) if prev else None])
            result.update(columns_used=[c for c in (date_col, measure) if c],
                          title=f"{name}: change vs {'previous ' + a.period if a.compare == 'previous' else 'same ' + a.period + ' a year earlier'}",
                          table={"columns": [a.period.capitalize(), name, "Compared with", "Earlier value", "Change", "Change (%)"], "rows": rows})
            if not rows:
                result["note"] = "Not enough data: no two periods to compare."
    else:  # distribution
        column = _column(sheet, a.column)
        drop_blank(column, f"blank {column}")
        if sheet.types[column] == TYPE_NUMBER:
            series = frame[column]
            if series.nunique() < 2:
                counts = series.value_counts().sort_index()
                rows = [[_label(_number(k)), int(v)] for k, v in counts.items()]
            else:
                binned = pd.cut(series, bins=a.bins, include_lowest=True)
                counts = binned.value_counts(sort=False)
                rows = [[f"{_number(iv.left)} to {_number(iv.right)}", int(v)] for iv, v in counts.items()]
        else:
            counts = frame[column].value_counts()
            rows = [[_label(k), int(v)] for k, v in counts.head(MAX_GROUPS).items()]
            if len(counts) > MAX_GROUPS:
                result["note"] = f"Showing the {MAX_GROUPS} most common of {len(counts)} values."
        result.update(columns_used=[column], title=f"Distribution of {column}", table={"columns": [column, "Rows"], "rows": rows})
    result["rows_used"] = int(len(frame))
    if excluded:
        result["rows_left_out"] = excluded
    if result["rows_used"] == 0:
        result["note"] = "Not enough data: no rows are left after filters and blanks."
    return result


_PERIOD_FREQ = {"day": "D", "week": "W-SUN", "month": "M", "quarter": "Q", "year": "Y"}


def _shift_label(ts: pd.Timestamp, period: str, lag: int) -> str:
    """The label of the period ``lag`` periods before ``ts`` (period arithmetic, no timedeltas)."""
    earlier = pd.Period(pd.Timestamp(ts), freq=_PERIOD_FREQ[period]) - int(lag)
    return _period_label(earlier.end_time, period)


def analyse(book: Workbook, request: Request) -> dict:
    results = []
    for i, analysis in enumerate(request.analyses, start=1):
        sheet = book.sheet(analysis.sheet or request.sheet)
        frame, described = _apply_filters(sheet, sheet.frame, request.filters)
        results.append(run_analysis(sheet, frame, described, analysis, i))
    return {"file": book.name, "results": results}
