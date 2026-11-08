"""Errors shared by tools and validators (kept import-free to avoid cycles)."""


class ToolError(Exception):
    """A failure the model can act on; its message is returned verbatim as the tool error."""
