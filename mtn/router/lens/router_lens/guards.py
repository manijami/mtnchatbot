"""Turn guards: answers router-lens gives itself, before or instead of a routed model call.

- Image turns: the text tiers (Groq gpt-oss, NVIDIA Nemotron 3 Ultra) reject image parts, so
  router-lens sends the latest image turn to the vision tier, or answers it politely when the
  vision tier is off or fails. Images in earlier messages become a short note so one image
  does not break the rest of the conversation.
- Office file requests: with the MTN Office tools in the request they go to the documents tier
  (see the end of this module); without them, the reply says how to switch to the MTN Document
  Assistant instead of producing a long text "deck".
- Slow or stalled models: callers get a clear message instead of an endless spinner.
"""

from __future__ import annotations

import json
import re
import time
import uuid

IMAGE_PART_TYPES = {"image_url", "input_image", "image"}
IMAGE_NOTE = "[image omitted: Smart Chat cannot read images]"

IMAGE_REPLY = (
    "Smart Chat can't read images yet, so I couldn't look at your attachment. "
    "Please describe what's in it, or paste the text you need help with, and I'll take it from there."
)
OFFICE_REPLY = (
    "I can't create files in Smart Chat. To get an MTN-branded {kind}, switch to **MTN Document "
    "Assistant** (open the model menu at the top, then MTN → MTN Document Assistant) and ask again; "
    "it builds the file and attaches it to the chat. If you'd like, I can draft the content here first."
)
TIMEOUT_REPLY = (
    "Sorry, the model is taking much longer than usual to start answering, so I stopped waiting. "
    "Please try again in a moment, or ask a shorter question."
)
VISION_FAILED_REPLY = (
    "Sorry, I couldn't read your image just now. Please try again in a moment, or describe "
    "what's in it and I'll help from there."
)
STALLED_NOTE = "\n\n*The answer was cut short because the model stopped responding. Please try again.*"

# A create verb followed (within a few words) by an Office file noun. Questions about a product
# ("what is an Excel pivot table?") do not match because they have no create verb.
_CREATE = r"(?:make|create|build|generate|draft|prepare|produce|put together|turn (?:this|it) into|give me|can (?:you|u) (?:do|make|create))"
_OFFICE = {
    "PowerPoint presentation": r"(?:power\s?point|pptx?|slide\s?deck|slides|deck|presentation)",
    "Word document": r"(?:word\s+(?:doc|document|file)|docx|\.doc\b)",
    "Excel workbook": r"(?:excel|xlsx|spreadsheet|workbook)",
}
_OFFICE_PATTERNS = {
    kind: re.compile(rf"\b{_CREATE}\b(?:\W+\w+){{0,6}}?\W+(?:an?\s+|the\s+)?{noun}", re.IGNORECASE)
    for kind, noun in _OFFICE.items()
}


def _parts(message: dict) -> list:
    content = message.get("content")
    return content if isinstance(content, list) else []


def has_image(message: dict) -> bool:
    return any(isinstance(p, dict) and p.get("type") in IMAGE_PART_TYPES for p in _parts(message))


def strip_history_images(messages: list) -> int:
    """Replaces image parts in all but the last user message with a text note. Returns the count."""
    last_user = max((i for i, m in enumerate(messages or []) if m.get("role") == "user"), default=-1)
    replaced = 0
    for index, message in enumerate(messages or []):
        if index == last_user or not has_image(message):
            continue
        kept = []
        for part in _parts(message):
            if isinstance(part, dict) and part.get("type") in IMAGE_PART_TYPES:
                replaced += 1
                kept.append({"type": "text", "text": IMAGE_NOTE})
            else:
                kept.append(part)
        # Text-only providers want a string: join the remaining text parts.
        message["content"] = "\n".join(p.get("text", "") for p in kept if isinstance(p, dict) and p.get("text"))
    return replaced


def latest_user(messages: list) -> dict | None:
    return next((m for m in reversed(messages or []) if m.get("role") == "user"), None)


def office_request(text: str) -> str | None:
    """Returns the requested Office file kind, or None."""
    for kind, pattern in _OFFICE_PATTERNS.items():
        if pattern.search(text or ""):
            return kind
    return None


def reply_stream(text: str, model: str = "mtn-smart") -> bytes:
    """A complete OpenAI-style streamed reply (content, finish, usage, [DONE])."""
    chunk_id = f"router-lens-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    def event(choices, usage=None):
        data = {"id": chunk_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": choices}
        if usage is not None:
            data["usage"] = usage
        return b"data: " + json.dumps(data).encode() + b"\n\n"

    return (
        event([{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}])
        + event([{"index": 0, "delta": {}, "finish_reason": "stop"}])
        + event([], usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        + b"data: [DONE]\n\n"
    )


def reply_json(text: str, model: str = "mtn-smart") -> dict:
    return {
        "id": f"router-lens-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def stalled_event(model: str = "mtn-smart") -> bytes:
    data = {"id": "router-lens-stalled", "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "delta": {"content": STALLED_NOTE}, "finish_reason": "stop"}]}
    return b"data: " + json.dumps(data).encode() + b"\n\ndata: [DONE]\n\n"


# -- Office documents tier ----------------------------------------------------------------------
#
# When the Smart Chat request carries the MTN Office tool definitions (the spec lists the
# mtn-office MCP server), Office turns go to the documents tier with those tools; every other turn
# goes to the text tiers without them, and any earlier tool exchange is flattened to plain text so
# a text model that has no tools still accepts the history.

OFFICE_TOOL_PREFIXES = (
    "create_word_document",
    "create_powerpoint_presentation",
    "create_excel_workbook",
    "revise_office_file",
    "get_generation_status",
)
TOOL_RESULT_NOTE_CHARS = 400

_REVISION = re.compile(
    r"\b(?:revise|edit|update|change|add|insert|remove|delete|rename|shorten|expand|make|move|"
    r"replace|fix|reword|swap)\b(?:\W+\w+){0,8}?\W+(?:the\s+|a\s+|an\s+)?(?:slides?|sheets?|columns?|"
    r"rows?|sections?|pages?|titles?|charts?|tables?|documents?|decks?|workbooks?|files?|headings?|"
    r"bullets?|paragraphs?|version|v\d)\b",
    re.IGNORECASE,
)


def _tool_name(tool: dict) -> str:
    return ((tool or {}).get("function") or {}).get("name") or (tool or {}).get("name") or ""


def is_office_tool(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in OFFICE_TOOL_PREFIXES)


def has_office_tools(tools) -> bool:
    return any(is_office_tool(_tool_name(tool)) for tool in tools or [] if isinstance(tool, dict))


def _last_user_index(messages: list) -> int:
    return max((i for i, m in enumerate(messages or []) if m.get("role") == "user"), default=-1)


def in_tool_loop(messages: list) -> bool:
    """True while the model is mid tool exchange: a tool call or result follows the last user turn."""
    start = _last_user_index(messages)
    for message in (messages or [])[start + 1:]:
        if message.get("role") == "tool" or message.get("tool_calls"):
            return True
    return False


def has_office_history(messages: list) -> bool:
    """True when an earlier turn called an MTN Office tool (a file exists to revise)."""
    for message in messages or []:
        for call in message.get("tool_calls") or []:
            if is_office_tool(_tool_name(call)):
                return True
        if message.get("role") == "tool" and is_office_tool(message.get("name") or ""):
            return True
    return False


def revision_request(text: str) -> bool:
    return bool(_REVISION.search(text or ""))


def strip_tools(body: dict) -> None:
    for key in ("tools", "tool_choice", "parallel_tool_calls"):
        body.pop(key, None)


def flatten_tool_history(messages: list) -> int:
    """Turns tool calls and tool results into plain assistant text. Returns how many changed."""
    changed = 0
    for message in messages or []:
        calls = message.pop("tool_calls", None)
        if calls:
            names = ", ".join(_tool_name(call) or "tool" for call in calls)
            text = message.get("content") if isinstance(message.get("content"), str) else ""
            message["content"] = (text + "\n" if text else "") + f"[Used tool: {names}]"
            changed += 1
        if message.get("role") == "tool":
            result = message.get("content")
            if isinstance(result, list):
                result = " ".join(p.get("text", "") for p in result if isinstance(p, dict))
            result = (result or "").strip()
            if len(result) > TOOL_RESULT_NOTE_CHARS:
                result = result[:TOOL_RESULT_NOTE_CHARS] + "…"
            message.clear()
            message.update({"role": "assistant", "content": f"[Tool result] {result}"})
            changed += 1
    return changed
