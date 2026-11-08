from .conftest import ALICE, headers, rpc


def test_healthz_is_public(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_mcp_requires_bearer_token(client):
    no_auth = client.post("/mcp", json={}, headers={"Content-Type": "application/json"})
    assert no_auth.status_code == 401
    assert rpc(client, "tools/list", token="wrong" * 10).status_code == 401
    assert rpc(client, "tools/list", token="").status_code == 401


def test_rest_requires_bearer_token(client):
    assert client.get("/v1/documents/abc").status_code == 401


def test_malformed_user_id_is_rejected(client):
    # An unresolved LibreChat placeholder must never become an owner.
    assert rpc(client, "tools/list", user="{{LIBRECHAT_USER_ID}}").status_code == 400
    assert rpc(client, "tools/list", user="../" + "a" * 21).status_code == 400


def test_tools_list_with_token(client):
    response = rpc(client, "tools/list")
    assert response.status_code == 200
    assert "tools" in response.json()["result"]


def test_tool_call_without_identity_is_an_error(client):
    response = rpc(client, "tools/call", {"name": "get_generation_status", "arguments": {}}, user=None)
    result = response.json()["result"]
    assert result["isError"] is True


def test_rest_without_identity_is_400(client):
    response = client.get("/v1/documents/abc", headers=headers(user=None))
    assert response.status_code == 400


def test_error_bodies_do_not_echo_the_token(client):
    response = rpc(client, "tools/list", token="x" * 48)
    assert "x" * 48 not in response.text
    assert ALICE not in response.text
