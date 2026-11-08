"""Bearer-token auth and per-request user identity (pure ASGI, safe for streaming responses).

Every route except ``/healthz`` needs ``Authorization: Bearer <MTN_OFFICE_MCP_TOKEN>``, compared
in constant time. The owner of a request is ``X-MTN-User-Id``, which LibreChat fills from the
signed-in user (``{{LIBRECHAT_USER_ID}}``). The token proves the caller is LibreChat; the header
says which user LibreChat is acting for. A present-but-malformed id (for example an unresolved
placeholder) is rejected outright.
"""

from __future__ import annotations

import hmac
import json
import re
from contextvars import ContextVar
from dataclasses import dataclass

USER_HEADER = b"x-mtn-user-id"
CONVERSATION_HEADER = b"x-mtn-conversation-id"
MESSAGE_HEADER = b"x-mtn-message-id"
PUBLIC_PATHS = frozenset({"/healthz"})

# LibreChat user ids are MongoDB ObjectIds.
USER_ID_PATTERN = re.compile(r"^[a-f0-9]{24}$")
# Conversation/message ids are UUIDs or LibreChat's "new" sentinel; anything else is dropped.
CONTEXT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class Identity:
    user_id: str
    conversation_id: str | None = None
    message_id: str | None = None


current_identity: ContextVar[Identity | None] = ContextVar("current_identity", default=None)


def _header(scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1").strip()
    return None


def _context_id(raw: str | None) -> str | None:
    return raw if raw and CONTEXT_ID_PATTERN.match(raw) else None


async def _reject(send, status: int, message: str) -> None:
    body = json.dumps({"error": message}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class AuthMiddleware:
    def __init__(self, app, token: str):
        self.app = app
        self._token = token.encode()

    def _authorized(self, scope) -> bool:
        header = _header(scope, b"authorization") or ""
        scheme, _, presented = header.partition(" ")
        if scheme.lower() != "bearer" or not presented:
            # Still compare, so a missing header costs the same as a wrong one.
            hmac.compare_digest(self._token, b"\0" * len(self._token))
            return False
        return hmac.compare_digest(self._token, presented.strip().encode())

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return
        if not self._authorized(scope):
            await _reject(send, 401, "unauthorized")
            return
        raw_user = _header(scope, USER_HEADER)
        identity = None
        if raw_user is not None:
            if not USER_ID_PATTERN.match(raw_user):
                await _reject(send, 400, "invalid X-MTN-User-Id")
                return
            identity = Identity(
                user_id=raw_user,
                conversation_id=_context_id(_header(scope, CONVERSATION_HEADER)),
                message_id=_context_id(_header(scope, MESSAGE_HEADER)),
            )
        scope.setdefault("state", {})["identity"] = identity
        reset = current_identity.set(identity)
        try:
            await self.app(scope, receive, send)
        finally:
            current_identity.reset(reset)
