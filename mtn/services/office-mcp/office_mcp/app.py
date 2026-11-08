"""ASGI app: MCP over streamable HTTP at ``/mcp``, owner-scoped REST reads at ``/v1``.

The MCP server uses the low-level SDK so the advertised tool schemas stay deliberately loose
(types only): providers such as Groq reject a tool call outright when arguments break the
advertised schema, whereas server-side validation can answer with errors the model can fix.
"""

from __future__ import annotations

import contextlib
import logging

import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from . import __version__
from .auth import AuthMiddleware, Identity
from .config import Settings
from .store import Store
from .tools import ToolContext, ToolError, registry

log = logging.getLogger("office_mcp")

INSTRUCTIONS = (
    "Creates MTN-branded Word, PowerPoint and Excel files from structured content. "
    "Call a create_* tool with the full content; the finished file is attached to the chat for "
    "the user automatically, so never paste file data or links. If a tool returns validation "
    "errors, fix exactly the listed fields and call it again."
)


def _identity(request: Request | None) -> Identity | None:
    if request is None:
        return None
    return request.scope.get("state", {}).get("identity")


def build_mcp_server(settings: Settings, store: Store) -> Server:
    server: Server = Server("mtn-office", version=__version__, instructions=INSTRUCTIONS)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [tool.definition for tool in registry.values()]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict) -> types.CallToolResult:
        tool = registry.get(name)
        if tool is None:
            return _error(f"Unknown tool '{name}'.")
        identity = _identity(server.request_context.request)
        if identity is None:
            return _error("Missing user identity; the request did not come from a signed-in user.")
        ctx = ToolContext(settings=settings, store=store, identity=identity)
        try:
            content = await tool.run(ctx, arguments or {})
        except ToolError as exc:
            return _error(str(exc))
        except Exception:  # noqa: BLE001 - never leak internals to the model
            log.exception("tool %s failed", name)
            return _error("The document could not be generated because of an internal error.")
        return types.CallToolResult(content=content, isError=False)

    return server


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=message)], isError=True)


def build_app(settings: Settings, store: Store | None = None) -> Starlette:
    store = store or Store(settings.data_dir, settings.retention_days)
    mcp_server = build_mcp_server(settings, store)
    sessions = StreamableHTTPSessionManager(app=mcp_server, stateless=True, json_response=True)

    class MCPEndpoint:  # a class instance, so Starlette routes it as a raw ASGI app
        async def __call__(self, scope, receive, send):
            await sessions.handle_request(scope, receive, send)

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "version": __version__})

    def _owned(request: Request):
        identity = _identity(request)
        if identity is None:
            return None, JSONResponse({"error": "missing X-MTN-User-Id"}, status_code=400)
        return identity, None

    async def get_document(request: Request) -> JSONResponse:
        identity, problem = _owned(request)
        if problem:
            return problem
        doc = store.get_document(identity.user_id, request.path_params["document_id"])
        if doc is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(document_summary(doc))

    async def get_artifact(request: Request):
        identity, problem = _owned(request)
        if problem:
            return problem
        name = {"file": "file", "preview.png": "preview.png", "preview.pdf": "preview.pdf"}.get(
            request.path_params["artifact"]
        )
        path = name and store.file_path(
            identity.user_id,
            request.path_params["document_id"],
            request.path_params["version"],
            name,
        )
        if not path:
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(path, filename=path.name)

    async def purge_loop():
        while True:
            removed = await anyio.to_thread.run_sync(store.purge_expired)
            if removed:
                log.info("retention: purged %d expired documents", removed)
            await anyio.sleep(3600)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with sessions.run(), anyio.create_task_group() as tg:
            tg.start_soon(purge_loop)
            yield
            tg.cancel_scope.cancel()

    app = Starlette(
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route("/mcp", MCPEndpoint()),
            Route("/v1/documents/{document_id:str}", get_document, methods=["GET"]),
            Route(
                "/v1/documents/{document_id:str}/versions/{version:int}/{artifact:str}",
                get_artifact,
                methods=["GET"],
            ),
        ],
        lifespan=lifespan,
    )
    app.add_middleware(AuthMiddleware, token=settings.token)
    return app


def document_summary(doc) -> dict:
    return {
        "document_id": doc.id,
        "kind": doc.kind,
        "template": doc.template,
        "title": doc.title,
        "created_at": doc.created_at,
        "versions": [
            {
                "version": v.version,
                "status": v.status,
                "template_version": v.template_version,
                "filename": v.filename,
                "bytes": v.bytes,
                "pages": v.pages,
                "checks": v.checks,
                "error": v.error,
                "duration_ms": v.duration_ms,
            }
            for v in doc.versions
        ],
    }
