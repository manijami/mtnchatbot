"""Tool registry. Each tool module registers a :class:`Tool` with a loose advertised schema and a
strict server-side validator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from mcp import types

from ..auth import Identity
from ..config import Settings
from ..store import Store


class ToolError(Exception):
    """A failure the model can act on; its message is returned verbatim as the tool error."""


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
from . import powerpoint_tool, word_tool  # noqa: E402,F401
