"""router-lens: a pass-through proxy between LibreChat and Switchyard (demo only).

For each chat turn it reads Switchyard's routing headers (served model, and the patched
``x-switchyard-route-evidence`` with the judge's verdict and reason), optionally appends a
footer to the answer, records the decision for the live feed and metrics, and retries once on
the backup-judge route when the primary route fails before anything has streamed.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import AsyncIterator

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

from . import guards
from .config import TIER_RULES, Settings
from .ledger import Decision, Ledger

FOOTER_PATTERN = re.compile(r"\n*\*Routed to [^\n]*\*\s*$")
RETRYABLE = {429, 500, 502, 503, 504}
PROMPT_CHARS = 80
HOP_HEADERS = {"content-length", "transfer-encoding", "connection", "content-encoding", "host"}


def strip_footers(messages: list) -> list:
    """Removes our own footers from assistant history so models never see them."""
    for message in messages or []:
        if message.get("role") == "assistant" and isinstance(message.get("content"), str):
            message["content"] = FOOTER_PATTERN.sub("", message["content"])
    return messages


def last_user_text(messages: list) -> str:
    for message in reversed(messages or []):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def snippet(text: str, redact: bool) -> str:
    text = " ".join(text.split())
    if redact:
        return f"[redacted · {len(text)} chars]"
    return text[:PROMPT_CHARS] + ("…" if len(text) > PROMPT_CHARS else "")


def parse_evidence(raw: str | None) -> tuple[str | None, str | None, str]:
    """Returns (verdict tier, reason, source) from the evidence header."""
    if not raw:
        return None, None, "rule"
    try:
        evidence = json.loads(raw)
    except ValueError:
        return None, None, "rule"
    if evidence.get("source") == "fail_open":
        return None, None, "fail_open"
    decision = (evidence.get("verdict") or {}).get("decision") or {}
    reason = decision.get("reason")
    if isinstance(reason, str):
        reason = " ".join(reason.split()[:14]).strip().rstrip(".") or None
    return decision.get("target"), reason, ("judge" if reason else "rule")


def format_latency(ms: int) -> str:
    return f"{ms / 1000:.1f} s"


def footer_text(model: str, tier: str, reason: str, latency_ms: int) -> str:
    label = f"{tier} tier" if tier in ("vision", "documents") else tier
    return f"\n\n*Routed to {model} · {label} · {reason} · {format_latency(latency_ms)}*"


class TurnState:
    def __init__(self, started: float, prompt: str):
        self.started = started
        self.prompt = prompt
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)


def build_app(settings: Settings, ledger: Ledger, client: httpx.AsyncClient | None = None) -> Starlette:
    http = client or httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))

    def describe(model: str, verdict_tier: str | None, reason: str | None, source: str):
        tier = settings.model_tiers.get(model) or verdict_tier or "balanced"
        shown_reason = reason or ("judge unavailable, default tier" if source == "fail_open" else TIER_RULES.get(tier, ""))
        return tier, shown_reason

    async def open_upstream(body: dict, route: str) -> httpx.Response:
        payload = dict(body, model=route)
        request = http.build_request(
            "POST", f"{settings.switchyard_url}/v1/chat/completions", json=payload,
            headers={"accept": "text/event-stream" if body.get("stream") else "application/json"},
        )
        return await http.send(request, stream=True)

    async def chat(request: Request) -> Response:
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({"error": {"message": "invalid JSON"}}, status_code=400)
        strip_footers(body.get("messages"))
        if body.get("stream"):
            body["stream_options"] = {**(body.get("stream_options") or {}), "include_usage": True}
        messages = body.get("messages") or []
        state = TurnState(time.monotonic(), snippet(guards.real_user_text(messages), settings.redact_prompts))

        def handled(text: str, reason: str, status: str = "handled") -> Response:
            ledger.record(Decision(time.time(), state.prompt, "router-lens", None, "router-lens", reason,
                                   "guard", "none", state.elapsed_ms(), 0, 0, status=status))
            if body.get("stream"):
                return Response(guards.reply_stream(text), media_type="text/event-stream",
                                headers={"x-router-lens-handled": reason})
            return JSONResponse(guards.reply_json(text), headers={"x-router-lens-handled": reason})

        guards.strip_history_images(messages)
        latest = guards.latest_user(messages)
        vision = bool(latest and guards.has_image(latest))
        if vision and not settings.vision_route:
            return handled(guards.IMAGE_REPLY, "image attached")
        text = guards.real_user_text(messages)  # what the person typed, not an injected skill body
        office_kind = None if vision else guards.office_request(text)

        # Documents tier: the request carries the MTN Office tools and the turn is about a file
        # (a new file, a tool exchange in progress, or a revision of a file made earlier).
        docs_reason = None
        if not vision and settings.docs_route and guards.has_office_tools(body.get("tools")):
            if guards.in_tool_loop(messages):
                docs_reason = "Office tool follow-up"
            elif office_kind:
                docs_reason = f"{office_kind} request"
            elif guards.has_office_history(messages) and guards.revision_request(text):
                docs_reason = "revision of an Office file"
        docs = docs_reason is not None
        if docs:
            if settings.docs_instructions:
                messages.insert(0, {"role": "system", "content": settings.docs_instructions})
        else:
            # Text tiers get no tools; earlier tool exchanges become plain text they accept.
            guards.strip_tools(body)
            guards.flatten_tool_history(messages)
            if office_kind:
                return handled(guards.OFFICE_REPLY.format(kind=office_kind), f"{office_kind} request")

        # A skill step (a skill was loaded into this turn) stays on one fixed tier, with no judge.
        skill_step = not (vision or docs) and bool(settings.skill_route) and guards.in_skill_step(messages)

        # Image, Office and skill-step turns skip the judge.
        judge_route = "none" if (vision or docs or skill_step) else "primary"
        if vision:
            route = settings.vision_route
        elif docs:
            route = settings.docs_route
        elif skill_step:
            route = settings.skill_route
        else:
            route = settings.primary_route
        backup_route = settings.docs_backup_route if docs else settings.backup_route
        try:
            upstream = await asyncio.wait_for(open_upstream(body, route), settings.first_byte_timeout)
            retry = upstream.status_code in RETRYABLE
            if retry or (vision and upstream.status_code != 200):
                await upstream.aread()
                await upstream.aclose()
        except asyncio.TimeoutError:
            # No answer within the deadline: try the backup route when there is one (a slow or
            # unavailable provider), otherwise answer clearly instead of spinning.
            if vision or not backup_route:
                return handled(guards.TIMEOUT_REPLY, f"no answer within {int(settings.first_byte_timeout)} s", "timeout")
            retry = True
        except httpx.HTTPError:
            retry = True
        if vision and (retry or upstream.status_code != 200):
            # Never show a provider's raw error for an image turn.
            return handled(guards.VISION_FAILED_REPLY, "vision tier unavailable", "error")
        if retry and backup_route:
            judge_route = "backup"
            try:
                upstream = await asyncio.wait_for(open_upstream(body, backup_route), settings.first_byte_timeout)
            except asyncio.TimeoutError:
                return handled(guards.TIMEOUT_REPLY, f"no answer within {int(settings.first_byte_timeout)} s", "timeout")
            except httpx.HTTPError:
                ledger.record(Decision(time.time(), state.prompt, "error", None, "-", "router unreachable",
                                       "error", judge_route, state.elapsed_ms(), 0, 0, status="error"))
                return JSONResponse({"error": {"message": "The router is unavailable. Please try again."}},
                                    status_code=502)
        if upstream.status_code != 200:
            content = await upstream.aread()
            await upstream.aclose()
            ledger.record(Decision(time.time(), state.prompt, "error", None, "-", f"HTTP {upstream.status_code}",
                                   "error", judge_route, state.elapsed_ms(), 0, 0, status="error"))
            return Response(content, status_code=upstream.status_code,
                            media_type=upstream.headers.get("content-type", "application/json"))

        model = upstream.headers.get("x-model-router-selected-model", "unknown")
        verdict_tier, reason, source = parse_evidence(upstream.headers.get("x-switchyard-route-evidence"))
        tier, shown_reason = describe(model, verdict_tier, reason, source)
        if docs:
            tier, shown_reason, source = "documents", docs_reason, "rule"
        elif skill_step:
            shown_reason, source = TIER_RULES["skill"], "rule"
        passthrough = {k: v for k, v in upstream.headers.items()
                       if k.startswith("x-model-router") or k.startswith("x-switchyard")}

        def finish(status: str = "ok") -> None:
            ledger.record(Decision(time.time(), state.prompt, tier, verdict_tier, model, shown_reason, source,
                                   judge_route, state.elapsed_ms(), state.prompt_tokens,
                                   state.completion_tokens, status=status))

        if not body.get("stream"):
            raw = await upstream.aread()
            await upstream.aclose()
            data = json.loads(raw)
            usage = data.get("usage") or {}
            state.prompt_tokens, state.completion_tokens = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
            if settings.show_footer and data.get("choices") and not _calls_tools(data):
                message = data["choices"][0].setdefault("message", {})
                message["content"] = (message.get("content") or "") + footer_text(model, tier, shown_reason, state.elapsed_ms())
            finish()
            return JSONResponse(data, headers=passthrough)

        async def relay() -> AsyncIterator[bytes]:
            buffer = b""
            footer_sent = not settings.show_footer
            status = "ok"
            chunks = upstream.aiter_bytes().__aiter__()
            try:
                while True:
                    try:
                        chunk = await asyncio.wait_for(chunks.__anext__(), settings.idle_timeout)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        # The model went silent mid-answer: close the answer cleanly.
                        status = "stalled"
                        yield guards.stalled_event()
                        return
                    buffer += chunk
                    while b"\n\n" in buffer:
                        event, buffer = buffer.split(b"\n\n", 1)
                        out = event + b"\n\n"
                        data = _event_json(event)
                        if data is not None:
                            usage = data.get("usage")
                            if usage:
                                state.prompt_tokens = usage.get("prompt_tokens", state.prompt_tokens)
                                state.completion_tokens = usage.get("completion_tokens", state.completion_tokens)
                            if not footer_sent and _calls_tools(data):
                                # A tool-call turn ends in tool calls, not text; the footer goes on
                                # the answer that follows the tool result.
                                footer_sent = True
                            if not footer_sent and _finishes(data):
                                footer_sent = True
                                content_part, finish_part = _split_finish(data)
                                if content_part is not None:
                                    # The final chunk also carries the answer's last characters:
                                    # send them first so the footer really comes last.
                                    yield b"data: " + json.dumps(content_part).encode() + b"\n\n"
                                    out = b"data: " + json.dumps(finish_part).encode() + b"\n\n"
                                yield _footer_event(data, footer_text(model, tier, shown_reason, state.elapsed_ms()))
                        elif not footer_sent and event.strip() == b"data: [DONE]":
                            footer_sent = True
                            yield _footer_event({}, footer_text(model, tier, shown_reason, state.elapsed_ms()))
                        yield out
                if buffer.strip():
                    yield buffer
            except (httpx.HTTPError, asyncio.CancelledError):
                status = "error"
                raise
            finally:
                await upstream.aclose()
                finish(status)

        return StreamingResponse(relay(), media_type="text/event-stream", headers=passthrough)

    async def models(_: Request) -> Response:
        upstream = await http.get(f"{settings.switchyard_url}/v1/models")
        return Response(upstream.content, status_code=upstream.status_code, media_type="application/json")

    async def metrics(_: Request) -> PlainTextResponse:
        return PlainTextResponse(ledger.prometheus(), media_type="text/plain; version=0.0.4")

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def poll_judge_usage():
        while True:
            try:
                stats = (await http.get(f"{settings.switchyard_url}/v1/stats", timeout=5)).json()
                ledger.set_judge_usage((stats.get("classifier") or {}).get("models") or {})
            except (httpx.HTTPError, ValueError):
                pass
            await asyncio.sleep(settings.stats_poll_seconds)

    import contextlib

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        task = asyncio.create_task(poll_judge_usage())
        try:
            yield
        finally:
            task.cancel()

    return Starlette(
        routes=[
            Route("/v1/chat/completions", chat, methods=["POST"]),
            Route("/v1/models", models, methods=["GET"]),
            Route("/metrics", metrics, methods=["GET"]),
            Route("/healthz", healthz, methods=["GET"]),
        ],
        lifespan=lifespan,
    )


def _event_json(event: bytes) -> dict | None:
    for line in event.split(b"\n"):
        if line.startswith(b"data:"):
            payload = line[5:].strip()
            if payload == b"[DONE]":
                return None
            try:
                value = json.loads(payload)
            except ValueError:
                return None
            return value if isinstance(value, dict) else None
    return None


def _calls_tools(data: dict) -> bool:
    return any(choice.get("finish_reason") == "tool_calls" for choice in data.get("choices") or [])


def _finishes(data: dict) -> bool:
    return any(choice.get("finish_reason") for choice in data.get("choices") or [])


def _split_finish(data: dict) -> tuple[dict | None, dict]:
    """Splits a finishing chunk that also carries content into (content-only, finish-only)."""
    choices = data.get("choices") or []
    if not any((choice.get("delta") or {}).get("content") for choice in choices):
        return None, data
    content_part = dict(data, choices=[dict(c, finish_reason=None) for c in choices])
    finish_part = dict(data, choices=[
        dict(c, delta={k: v for k, v in (c.get("delta") or {}).items() if k not in ("content", "reasoning_content", "reasoning")})
        for c in choices
    ])
    content_part.pop("usage", None)
    return content_part, finish_part


def _footer_event(template: dict, text: str) -> bytes:
    chunk = {
        "id": template.get("id", "router-lens-footer"),
        "object": "chat.completion.chunk",
        "created": template.get("created", int(time.time())),
        "model": template.get("model", ""),
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
    }
    return b"data: " + json.dumps(chunk).encode() + b"\n\n"
