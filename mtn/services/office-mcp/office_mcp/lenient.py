"""Lenient argument repair: fix mistakes whose intent is clear instead of failing the call.

Applied before strict validation. Every change is recorded as a short note, stored in the
version's ``checks["coercions"]`` and reported back to the model. Anything that could produce a
wrong document stays a strict, fixable error: column names (formulas use them), table cells,
counts of slides/sections/rows, row/column mismatches, templates and page/slide targets.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

TRIM_RATIO = 1.5  # trim only text up to 1.5x its limit; longer text means real content would be lost
ELLIPSIS = "…"

# Display-text fields that may be shortened at a word boundary (leaf key -> applies at any depth).
TRIMMABLE_KEYS = frozenset(
    {"title", "subtitle", "heading", "key_message", "caption", "label", "value", "bullets", "numbered"}
)
# Short scalar values in unknown fields are presumed harmless (e.g. "layout": "bullets").
HARMLESS_SCALAR_CHARS = 40


def _path(loc) -> str:
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def _get_parent(data, loc):
    node = data
    for part in loc[:-1]:
        node = node[part]
    return node, loc[-1]


def trim_words(text: str, limit: int) -> str:
    """Shortens text to at most ``limit`` characters at a word boundary, ending with an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[: max(1, limit - len(ELLIPSIS))]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:-–—") + ELLIPSIS


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def normalise(kind: str, data: Any, notes: list[str]) -> Any:
    """Kind-specific alias mapping for content that would otherwise be dropped."""
    if not isinstance(data, dict):
        return data
    if kind == "powerpoint":
        for index, slide in enumerate(data.get("slides") or []):
            if not isinstance(slide, dict):
                continue
            bullets = list(slide.get("bullets") or [])
            numbered = slide.pop("numbered", None)
            if isinstance(numbered, list) and numbered:
                bullets += [f"{n}. {item}" for n, item in enumerate(numbered, start=1)]
                notes.append(f"slides[{index}].numbered: shown as numbered bullets (slides have bullets only)")
            paragraphs = slide.pop("paragraphs", None)
            if isinstance(paragraphs, list) and paragraphs:
                bullets += [str(p) for p in paragraphs]
                notes.append(f"slides[{index}].paragraphs: shown as bullets")
            if bullets or "bullets" in slide:
                slide["bullets"] = bullets
    if kind in ("word", "powerpoint"):
        sections = data.get("sections") or []
        slides = data.get("slides") or []
        for container in [*sections, *slides]:
            if not isinstance(container, dict):
                continue
            level = container.get("level")
            if isinstance(level, str) and level.strip().isdigit():
                container["level"] = int(level.strip())
            table = container.get("table")
            if isinstance(table, dict) and isinstance(table.get("rows"), list):
                converted = False
                for row in table["rows"]:
                    if isinstance(row, list):
                        for i, cell in enumerate(row):
                            if _number(cell) or cell is None:
                                row[i] = "" if cell is None else (f"{cell:g}" if isinstance(cell, float) else str(cell))
                                converted = True
                if converted:
                    notes.append("table numbers converted to text cells")
    return data


def _repair(error: dict, data, notes: list[str]) -> bool:
    """Repairs one validation error in place when the intent is clear. Returns True if fixed."""
    loc, kind = tuple(error["loc"]), error["type"]
    path = _path(loc)
    try:
        parent, key = _get_parent(data, loc)
    except (KeyError, IndexError, TypeError):
        return False
    if kind == "extra_forbidden":
        value = parent.get(key) if isinstance(parent, dict) else None
        harmless = value is None or isinstance(value, bool) or _number(value) or (
            isinstance(value, str) and len(value) <= HARMLESS_SCALAR_CHARS
        )
        if harmless and isinstance(parent, dict):
            parent.pop(key, None)
            notes.append(f"{path}: unknown field ignored")
            return True
        return False
    if kind == "string_too_long":
        limit = (error.get("ctx") or {}).get("max_length")
        leaf = next((p for p in reversed(loc) if isinstance(p, str)), "")
        value = parent[key]
        if limit and leaf in TRIMMABLE_KEYS and isinstance(value, str) and len(value) <= limit * TRIM_RATIO:
            parent[key] = trim_words(value, limit)
            notes.append(f"{path}: shortened to {limit} characters")
            return True
        return False
    if kind == "too_long" and loc[-1:] == ("value_columns",):
        limit = (error.get("ctx") or {}).get("max_length", 4)
        dropped = parent[key][limit:]
        parent[key] = parent[key][:limit]
        notes.append(f"{path}: chart shows the first {limit} series (left out: {', '.join(map(str, dropped))})")
        return True
    return False


def repair_until_valid(model: type[BaseModel], data: Any, notes: list[str], max_rounds: int = 8):
    """Validates, repairing clear-intent errors between rounds. Raises the last ValidationError."""
    for _ in range(max_rounds):
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            repaired = [_repair(error, data, notes) for error in exc.errors(include_url=False)]
            if not any(repaired):
                raise
    return model.model_validate(data)
