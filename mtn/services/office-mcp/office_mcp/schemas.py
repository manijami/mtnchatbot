"""Strict server-side input models and the loose schemas advertised to the model.

The advertised JSON Schema carries types and descriptions only. Length limits, allowed values and
cross-field rules are enforced here, and failures come back as a numbered list of field paths the
model can fix, instead of the provider rejecting the call outright.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .tools import ToolError

# Characters XML 1.0 cannot carry; models occasionally emit them.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def clean(text: str) -> str:
    return _CONTROL.sub("", text).strip()


Short = Annotated[str, Field(min_length=1, max_length=150)]
Line = Annotated[str, Field(min_length=1, max_length=600)]
Paragraph = Annotated[str, Field(min_length=1, max_length=4000)]
Cell = Annotated[str, Field(max_length=500)]


def clean_tree(value):
    """Removes XML-invalid control characters from every string in the arguments."""
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, list):
        return [clean_tree(v) for v in value]
    if isinstance(value, dict):
        return {k: clean_tree(v) for k, v in value.items()}
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CoverField(Strict):
    label: Annotated[str, Field(min_length=1, max_length=40)]
    value: Annotated[str, Field(min_length=1, max_length=300)]


class Table(Strict):
    columns: Annotated[list[Annotated[str, Field(min_length=1, max_length=60)]], Field(min_length=1, max_length=8)]
    rows: Annotated[list[list[Cell]], Field(min_length=1, max_length=80)]
    caption: Annotated[str, Field(max_length=200)] | None = None

    @model_validator(mode="after")
    def _rows_match_columns(self):
        width = len(self.columns)
        for index, row in enumerate(self.rows):
            if len(row) != width:
                raise ValueError(
                    f"rows[{index}] has {len(row)} cells but the table has {width} columns; "
                    f"give every row exactly {width} cells"
                )
        return self


class WordSection(Strict):
    heading: Short
    level: Literal[1, 2, 3] = 1
    paragraphs: Annotated[list[Paragraph], Field(max_length=30)] = []
    bullets: Annotated[list[Line], Field(max_length=30)] = []
    numbered: Annotated[list[Line], Field(max_length=30)] = []
    table: Table | None = None

    @model_validator(mode="after")
    def _has_content(self):
        if not (self.paragraphs or self.bullets or self.numbered or self.table):
            raise ValueError("a section needs at least one of paragraphs, bullets, numbered or table")
        return self


WORD_TEMPLATE_NAMES = ("proposal", "meeting_minutes", "incident_report")


class WordDocumentSpec(Strict):
    template: Literal["proposal", "meeting_minutes", "incident_report"]
    title: Short
    subtitle: Annotated[str, Field(max_length=200)] | None = None
    cover_fields: Annotated[list[CoverField], Field(max_length=12)] = []
    sections: Annotated[list[WordSection], Field(min_length=1, max_length=40)]
    target_pages: Annotated[int, Field(ge=1, le=50)] | None = None
    filename: Annotated[str, Field(max_length=80)] | None = None


# --------------------------------------------------------------------------------------------
# Error formatting


def _path(loc: tuple) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        elif part not in ("function-after", "literal", "list", "str", "int"):
            out += f".{part}" if out else str(part)
    return out or "arguments"


def parse(model: type[BaseModel], arguments: dict) -> BaseModel:
    try:
        return model.model_validate(clean_tree(arguments))
    except ValidationError as exc:
        problems = []
        for error in exc.errors(include_url=False, include_input=False)[:15]:
            message = error["msg"].removeprefix("Value error, ")
            problems.append(f"{len(problems) + 1}. {_path(error['loc'])}: {message}")
        more = len(exc.errors()) - len(problems)
        if more > 0:
            problems.append(f"... and {more} more")
        raise ToolError(
            "The arguments are not valid. Fix these fields and call the tool again:\n" + "\n".join(problems)
        ) from None


# --------------------------------------------------------------------------------------------
# Advertised (loose) JSON Schemas

_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": _STR}

TABLE_SCHEMA = {
    "type": "object",
    "description": "A table: column headings and rows; every row has one cell per column.",
    "properties": {
        "columns": {**_STR_LIST, "description": "Column headings (up to 8)."},
        "rows": {"type": "array", "items": _STR_LIST, "description": "Rows of cell text."},
        "caption": {**_STR, "description": "Optional caption shown under the table."},
    },
    "required": ["columns", "rows"],
}

WORD_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "template": {
            **_STR,
            "description": "One of: proposal, meeting_minutes, incident_report (use incident_report "
            "for incidents and IT/operational processes).",
        },
        "title": {**_STR, "description": "Document title (up to 150 characters)."},
        "subtitle": {**_STR, "description": "Optional subtitle."},
        "cover_fields": {
            "type": "array",
            "description": "Optional label/value pairs shown in a summary table under the title "
            "(e.g. Owner, Date, Version). Up to 12.",
            "items": {
                "type": "object",
                "properties": {"label": _STR, "value": _STR},
                "required": ["label", "value"],
            },
        },
        "sections": {
            "type": "array",
            "description": "Document body in order. Each section has a heading and at least one of "
            "paragraphs, bullets, numbered or table. About 450 words fill one A4 page.",
            "items": {
                "type": "object",
                "properties": {
                    "heading": _STR,
                    "level": {"type": "integer", "description": "1 (default), 2 or 3."},
                    "paragraphs": {**_STR_LIST, "description": "Body paragraphs. **bold** is supported."},
                    "bullets": {**_STR_LIST, "description": "Bulleted list items."},
                    "numbered": {**_STR_LIST, "description": "Numbered steps."},
                    "table": TABLE_SCHEMA,
                },
                "required": ["heading"],
            },
        },
        "target_pages": {
            "type": "integer",
            "description": "Set when the user asks for a length (e.g. 2 for 'a two-page document'). "
            "A file that renders longer is not delivered; you get the word budget to shorten it.",
        },
        "filename": {**_STR, "description": "Optional file name without extension."},
    },
    "required": ["template", "title", "sections"],
}


# --------------------------------------------------------------------------------------------
# PowerPoint

SlideLine = Annotated[str, Field(min_length=1, max_length=160)]


class ChartSeries(Strict):
    name: Annotated[str, Field(min_length=1, max_length=40)]
    values: Annotated[list[float], Field(min_length=1, max_length=12)]


class Chart(Strict):
    type: Literal["bar", "column", "line", "pie"]
    categories: Annotated[list[Annotated[str, Field(min_length=1, max_length=30)]], Field(min_length=1, max_length=12)]
    series: Annotated[list[ChartSeries], Field(min_length=1, max_length=4)]
    title: Annotated[str, Field(max_length=80)] | None = None

    @model_validator(mode="after")
    def _shape(self):
        n = len(self.categories)
        for index, series in enumerate(self.series):
            if len(series.values) != n:
                raise ValueError(
                    f"series[{index}] has {len(series.values)} values but there are {n} categories; "
                    f"give each series exactly {n} values"
                )
        if self.type == "pie" and len(self.series) != 1:
            raise ValueError("a pie chart takes exactly one series")
        if self.type == "pie" and any(v < 0 for v in self.series[0].values):
            raise ValueError("pie chart values must not be negative")
        return self


class SlideTable(Table):
    columns: Annotated[list[Annotated[str, Field(min_length=1, max_length=40)]], Field(min_length=1, max_length=6)]
    rows: Annotated[list[list[Annotated[str, Field(max_length=120)]]], Field(min_length=1, max_length=8)]


class SlideSpec(Strict):
    title: Annotated[str, Field(min_length=1, max_length=90)]
    bullets: Annotated[list[SlideLine], Field(max_length=6)] = []
    table: SlideTable | None = None
    chart: Chart | None = None
    key_message: Annotated[str, Field(max_length=140)] | None = None
    notes: Annotated[str, Field(max_length=3000)] | None = None

    @model_validator(mode="after")
    def _content(self):
        if self.table and self.chart:
            raise ValueError("use either table or chart on one slide, not both; split them over two slides")
        if not (self.bullets or self.table or self.chart):
            raise ValueError("a slide needs bullets, a table or a chart")
        return self


class PresentationSpec(Strict):
    template: Literal["executive_update", "project_status"]
    title: Annotated[str, Field(min_length=1, max_length=90)]
    subtitle: Annotated[str, Field(max_length=140)] | None = None
    include_title_slide: bool = True
    slides: Annotated[list[SlideSpec], Field(min_length=1, max_length=20)]
    target_slides: Annotated[int, Field(ge=1, le=21)] | None = None
    filename: Annotated[str, Field(max_length=80)] | None = None

    @model_validator(mode="after")
    def _count(self):
        total = len(self.slides) + (1 if self.include_title_slide else 0)
        if self.target_slides and total != self.target_slides:
            content = self.target_slides - (1 if self.include_title_slide else 0)
            raise ValueError(
                f"target_slides is {self.target_slides} but the deck has {total} slides "
                f"({'title slide + ' if self.include_title_slide else ''}{len(self.slides)} content); "
                f"give exactly {content} items in slides"
            )
        return self


CHART_SCHEMA = {
    "type": "object",
    "description": "Native chart. bar/column/line take up to 4 series; pie takes one series.",
    "properties": {
        "type": {**_STR, "description": "bar, column, line or pie."},
        "categories": {**_STR_LIST, "description": "Category labels (up to 12)."},
        "series": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": _STR, "values": {"type": "array", "items": {"type": "number"}}},
                "required": ["name", "values"],
            },
        },
        "title": _STR,
    },
    "required": ["type", "categories", "series"],
}

POWERPOINT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "template": {**_STR, "description": "executive_update or project_status."},
        "title": {**_STR, "description": "Deck title, shown on the title slide."},
        "subtitle": {**_STR, "description": "Optional subtitle for the title slide."},
        "include_title_slide": {"type": "boolean", "description": "Default true. The title slide counts as a slide."},
        "slides": {
            "type": "array",
            "description": "Content slides in order, NOT counting the title slide: for a five-slide "
            "deck with a title slide give exactly 4 items. Each has a title (max 90 characters) and "
            "bullets, a table or a chart (bullets may sit beside a table or chart). Up to 6 bullets, "
            "each at most 160 characters (about 25 words).",
            "items": {
                "type": "object",
                "properties": {
                    "title": _STR,
                    "bullets": _STR_LIST,
                    "table": {**TABLE_SCHEMA, "description": "Up to 6 columns and 8 rows."},
                    "chart": CHART_SCHEMA,
                    "key_message": {**_STR, "description": "Optional one-line takeaway shown at the bottom."},
                    "notes": {**_STR, "description": "Speaker notes."},
                },
                "required": ["title"],
            },
        },
        "target_slides": {
            "type": "integer",
            "description": "Set when the user asks for a number of slides. It counts the title slide, "
            "so target_slides 5 means 4 items in slides.",
        },
        "filename": {**_STR, "description": "Optional file name without extension."},
    },
    "required": ["template", "title", "slides"],
}
