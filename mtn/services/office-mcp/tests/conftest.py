import os
from dataclasses import replace
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from office_mcp.app import build_app
from office_mcp.config import Settings
from office_mcp.store import Store

TOKEN = "t" * 48
ALICE = "a" * 24
BOB = "b" * 24
TEMPLATES = Path(os.environ.get("OFFICE_MCP_TEMPLATES_DIR", "/app/templates"))


@pytest.fixture
def settings(tmp_path):
    return Settings(
        token=TOKEN,
        data_dir=tmp_path,
        templates_dir=TEMPLATES,
        logo_dir=tmp_path / "no-logo",
        host="127.0.0.1",
        port=8000,
        retention_days=0,
        convert_timeout_s=60,
        max_file_bytes=20 * 1024 * 1024,
        preview_image=False,
    )


@pytest.fixture
def store(settings):
    s = Store(settings.data_dir)
    yield s
    s.close()


@pytest.fixture
def client(settings, store):
    with TestClient(build_app(settings, store)) as c:
        yield c


def headers(user=ALICE, token=TOKEN, **extra):
    h = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if user is not None:
        h["X-MTN-User-Id"] = user
    h.update(extra)
    return h


def rpc(client, method, params=None, user=ALICE, **kw):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post("/mcp", json=body, headers=headers(user=user, **kw))


def call(client, tool, arguments, user=ALICE):
    response = rpc(client, "tools/call", {"name": tool, "arguments": arguments}, user=user)
    assert response.status_code == 200, response.text
    return response.json()["result"]


__all__ = ["ALICE", "BOB", "TOKEN", "TEMPLATES", "headers", "rpc", "call", "replace"]
