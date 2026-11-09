"""Tool registry. Each tool module registers a :class:`Tool` with a loose advertised schema and a
strict server-side validator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from mcp import types

from ..auth import Identity
from ..config import Settings
from ..errors import ToolError
from ..store import Store

__all__ = ["Tool", "ToolContext", "ToolError", "register", "registry"]




@dataclass
class ToolContext:
    settings: Settings
    store: Store
    identity: Identity


@dataclass
class Tool:
    definition: types.Tool
    run: Callable[[ToolContext, dict], Awaitable[list]]


registry: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    registry[tool.definition.name] = tool
    return tool


# Tool modules register themselves on import.
from . import excel_tool, powerpoint_tool, word_tool  # noqa: E402,F401
from . import revise_tool  # noqa: E402,F401  (after the create tools it reuses)
from . import insights_tool  # noqa: E402,F401  (Excel insights: inspect_workbook, analyse_workbook)
