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
    return f"\n\n*Routed to {model} · {tier} · {reason} · {format_latency(latency_ms)}*"


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
        state = TurnState(time.monotonic(), snippet(last_user_text(body.get("messages")), settings.redact_prompts))

        judge_route = "primary"
        try:
            upstream = await open_upstream(body, settings.primary_route)
            retry = upstream.status_code in RETRYABLE
            if retry:
                await upstream.aread()
                await upstream.aclose()
        except httpx.HTTPError:
            retry = True
        if retry:
            judge_route = "backup"
            try:
                upstream = await open_upstream(body, settings.backup_route)
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
            if settings.show_footer and data.get("choices"):
                message = data["choices"][0].setdefault("message", {})
                message["content"] = (message.get("content") or "") + footer_text(model, tier, shown_reason, state.elapsed_ms())
            finish()
            return JSONResponse(data, headers=passthrough)

        async def relay() -> AsyncIterator[bytes]:
            buffer = b""
            footer_sent = not settings.show_footer
            status = "ok"
            try:
                async for chunk in upstream.aiter_bytes():
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
