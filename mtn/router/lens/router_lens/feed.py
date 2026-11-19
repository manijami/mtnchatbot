"""Live routing decision feed (served on its own port, published on 127.0.0.1 only)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

from .ledger import Ledger

PAGE = (Path(__file__).parent / "feed.html").read_text()


def build_feed_app(ledger: Ledger) -> Starlette:
    async def page(_: Request) -> HTMLResponse:
        return HTMLResponse(PAGE)

    async def state(_: Request) -> JSONResponse:
        return JSONResponse({"summary": ledger.summary(), "recent": [ledger.public(d) for d in list(ledger.recent)[:50]]})

    async def events(request: Request) -> StreamingResponse:
        queue = ledger.subscribe()

        async def stream():
            try:
                yield b": connected\n\n"
                while not await request.is_disconnected():
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=15)
                        yield f"data: {json.dumps(payload)}\n\n".encode()
                    except asyncio.TimeoutError:
                        yield b": keep-alive\n\n"
            finally:
                ledger.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"cache-control": "no-cache"})

    return Starlette(routes=[Route("/", page), Route("/state", state), Route("/events", events)])
