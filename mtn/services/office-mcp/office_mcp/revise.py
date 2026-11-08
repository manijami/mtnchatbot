"""Revision support: outlines of stored content and a small JSON Patch (add/replace/remove).

Paths address the stored spec of the version being revised, e.g. ``/slides/0/bullets`` or
``/sections/2/table``; ``slides[0].bullets`` is accepted too. For decks, ``slides`` excludes the
title slide, so visible slide N is ``/slides/N-2`` when the deck has a title slide.
"""

from __future__ import annotations

import copy
import re

from .errors import ToolError

_DOTTED = re.compile(r"\[(\d+|-)\]")


def outline(kind: str, spec: dict) -> list[str]:
    if kind == "word":
        return [
            f"/sections/{i}: \"{s.get('heading')}\" ("
            + ", ".join(f"{len(s[k])} {k}" for k in ("paragraphs", "bullets", "numbered") if s.get(k))
            + (", table" if s.get("table") else "")
            + ")"
            for i, s in enumerate(spec.get("sections", []))
        ]
    if kind == "powerpoint":
        # One number per slide, exactly as the user sees it; the path uses the same number.
        has_title = spec.get("include_title_slide", True)
        offset = 2 if has_title else 1
        lines = ['Slide 1 "' + str(spec.get("title")) + '" (title slide): /slide/1'] if has_title else []
        for i, s in enumerate(spec.get("slides", [])):
            parts = [f"{len(s['bullets'])} bullets"] if s.get("bullets") else []
            parts += [k for k in ("table", "chart", "key_message", "notes") if s.get(k)]
            lines.append(f'Slide {i + offset} "{s.get("title")}" ({", ".join(parts)}): /slide/{i + offset}')
        return lines
    if kind == "excel":
        return [
            f"/sheets/{i}: \"{s.get('name')}\" ({len(s.get('rows', []))} rows; columns: "
            + ", ".join(c.get("name", "?") for c in s.get("columns", []))
            + ")"
            for i, s in enumerate(spec.get("sheets", []))
        ]
    return []


def _tokens(path: str) -> list[str]:
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + _DOTTED.sub(r".\1", path).replace(".", "/")
    return [t.replace("~1", "/").replace("~0", "~") for t in path.split("/")[1:] if t != ""]


def _step(node, token: str, path: str, *, allow_append: bool = False):
    if isinstance(node, list):
        if token == "-" and allow_append:
            return len(node)
        if not token.isdigit() or int(token) >= len(node) + (1 if allow_append else 0):
            raise ToolError(f"Change path {path}: index {token} is out of range (list has {len(node)} items).")
        return int(token)
    if isinstance(node, dict):
        return token
    raise ToolError(f"Change path {path}: cannot go into a {type(node).__name__}.")


def _visible_slide_alias(tokens: list[str], spec: dict, kind: str, path: str) -> list[str]:
    """/slide/N/... (visible slide number, as the user sees it) -> /slides/<index>/..."""
    if kind != "powerpoint" or len(tokens) < 2 or tokens[0] != "slide":
        return tokens
    has_title = spec.get("include_title_slide", True)
    if not tokens[1].isdigit():
        raise ToolError(f"Change path {path}: use /slide/<number>, e.g. /slide/2/bullets.")
    number = int(tokens[1])
    if has_title and number == 1:
        if len(tokens) == 2:
            raise ToolError("Slide 1 is the title slide; change /title or /subtitle instead.")
        return tokens[2:]  # /slide/1/title -> /title
    index = number - (2 if has_title else 1)
    if index < 0 or index >= len(spec.get("slides", [])):
        raise ToolError(_missing(path, spec, kind))
    return ["slides", str(index), *tokens[2:]]


def apply_changes(spec: dict, changes: list, kind: str) -> dict:
    """Applies add/replace/remove operations to a deep copy of ``spec``."""
    if not isinstance(changes, list) or not changes:
        raise ToolError("changes must be a non-empty list of {op, path, value} operations.")
    result = copy.deepcopy(spec)
    for number, change in enumerate(changes[:50]):
        if not isinstance(change, dict):
            raise ToolError(f"changes[{number}] must be an object with op, path and value.")
        op, path = change.get("op"), str(change.get("path", ""))
        tokens = _visible_slide_alias(_tokens(path), spec, kind, path)
        if op not in ("add", "replace", "remove") or not tokens:
            raise ToolError(f"changes[{number}]: op must be add, replace or remove, with a path like /slides/0/bullets.")
        parent = result
        for token in tokens[:-1]:
            key = _step(parent, token, path)
            if isinstance(parent, dict) and key not in parent:
                raise ToolError(_missing(path, spec, kind))
            parent = parent[key]
        last = tokens[-1]
        if isinstance(parent, list):
            index = _step(parent, last, path, allow_append=(op == "add"))
            if op == "add":
                parent.insert(index, change.get("value"))
            elif op == "replace":
                parent[index] = change.get("value")
            else:
                parent.pop(index)
        elif isinstance(parent, dict):
            if op == "remove":
                if parent.get(last) in (None, [], ""):  # removing something that is not there
                    raise ToolError(_missing(path, spec, kind))
                parent.pop(last)
            elif op == "replace" and last not in parent:
                parent[last] = change.get("value")  # replacing an unset optional field acts as add
            else:
                parent[last] = change.get("value")
        else:
            raise ToolError(_missing(path, spec, kind))
    return result


def _missing(path: str, spec: dict, kind: str) -> str:
    return f"Change path {path} does not exist in the current version. Its structure is:\n" + "\n".join(
        outline(kind, spec)
    )
