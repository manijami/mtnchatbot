"""Local-demo administration over verified loopback TLS; no Splunk.com access.

Run only inside the isolated Splunk container. The local bootstrap credential
stays in process memory. Never print response bodies, headers, passwords or tokens.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
from pathlib import Path
import ssl
import urllib.error
import urllib.parse
import urllib.request


class AdminError(Exception):
    def __init__(self, path: str, status: int):
        self.path = path.split("?", 1)[0]
        self.status = status


class Client:
    def __init__(self):
        password = os.environ.get("SPLUNK_PASSWORD", "")
        if not password:
            raise AdminError("local-bootstrap-credential", 0)
        self.auth = "Basic " + base64.b64encode(("admin:" + password).encode()).decode()
        self.context = ssl.create_default_context(cafile="/run/splunk-tls/ca.pem")

    def request(self, path: str, method: str = "GET", form: dict | None = None, body: dict | None = None):
        headers = {"Authorization": self.auth, "Accept": "application/json"}
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form, doseq=True).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        url = "https://127.0.0.1:8089" + path + ("&" if "?" in path else "?") + "output_mode=json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, context=self.context, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise AdminError(path, error.code) from None
        except urllib.error.URLError:
            raise AdminError(path, 0) from None


def inspect(client: Client):
    result = {}
    for key, endpoint, fields in [
        ("instance", "/services/server/info", ("version", "licenseState")),
        ("licenses", "/services/licenser/licenses", ("type", "group_id", "creation_time", "expiration_time", "relative_expiration_interval", "status")),
        ("token_auth", "/services/admin/token-auth/tokens_auth", ("disabled",)),
    ]:
        try:
            data = client.request(endpoint)
            result[key] = [{k: entry.get("content", {}).get(k) for k in fields if k in entry.get("content", {})}
                           for entry in data.get("entry", [])]
        except AdminError as error:
            result[key] = {"http_status": error.status}
    try:
        tools = client.request("/services/mcp_tools?enabled_tools=true")
        result["enabled_tools_top_keys"] = list(tools) if isinstance(tools, dict) else []
        result["enabled_tools"] = [{k: tool.get(k) for k in ("name", "tool_name", "tool_id", "id") if k in tool}
                                   for tool in tools.get("enabled_tools", [])]
    except AdminError as error:
        result["enabled_tools"] = {"http_status": error.status}
    print(json.dumps(result, indent=2))


ALLOWED_TOOLS = {
    "splunk_run_query", "splunk_get_metadata", "splunk_get_sourcetypes",
    "splunk_list_alerts", "splunk_get_alert_details", "splunk_list_fired_alerts", "splunk_get_fired_alert_details",
}


def provision(client: Client, target: Path):
    status = client.request("/services/kvstore/status")
    states = [e.get("content", {}).get("current", {}).get("status") for e in status.get("entry", [])]
    if states != ["ready"]:
        print(json.dumps({"blocked": "kvstore_not_ready", "states": states}))
        return 2
    secret_data = json.loads(target.read_text()) if target.is_file() else {}

    def save():
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump(secret_data, output)
        target.chmod(0o600)

    tools = client.request("/services/mcp_tools?enabled_tools=true")["enabled_tools"]
    for tool in tools:
        if tool["tool_name"] not in ALLOWED_TOOLS:
            client.request("/services/mcp_tools", "POST", body={"tool_id": tool["tool_id"], "tool_name": tool["tool_name"], "enabled": False})
    enabled = {t["tool_name"] for t in client.request("/services/mcp_tools?enabled_tools=true")["enabled_tools"]}
    if enabled != ALLOWED_TOOLS:
        print(json.dumps({"blocked": "tool_allowlist_mismatch", "enabled": sorted(enabled)}))
        return 1

    name = "svc_mtn_assistant"
    try:
        user = client.request("/services/authentication/users/" + name)
    except AdminError as error:
        if error.status != 404:
            raise
        password = "Aa1!" + secrets.token_urlsafe(32)
        client.request("/services/authentication/users", "POST", form={"name": name, "password": password,
                       "roles": "mtn_ops_readonly", "defaultApp": "Splunk_MCP_Server"})
        secret_data["MTN_SPLUNK_SERVICE_PASSWORD"] = password
        save()
        user = client.request("/services/authentication/users/" + name)
    roles = user["entry"][0]["content"]["roles"]
    if roles != ["mtn_ops_readonly"]:
        print(json.dumps({"blocked": "unexpected_service_roles", "roles": roles}))
        return 1
    key = client.request("/services/mcp_token/key-pair")
    if not key.get("current_key"):
        client.request("/services/mcp_token/key-pair", "POST", body={"key_size": 2048})
    if not secret_data.get("MTN_SPLUNK_MCP_TOKEN"):
        issued = client.request("/services/mcp_token/tokens", "POST", body={"username": name, "expires_on": "+30d"})
        token = issued.get("token")
        if not isinstance(token, str) or not token:
            raise AdminError("mcp-token-missing", 0)
        secret_data["MTN_SPLUNK_MCP_TOKEN"] = token
        save()
    print(json.dumps({"service_identity": name, "roles": roles, "enabled_tools": sorted(enabled),
                      "token_stored_privately": True, "requested_expiry": "30 days"}, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inspect", "provision"])
    parser.add_argument("--secrets-out", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "inspect":
            inspect(Client())
        else:
            if not args.secrets_out:
                parser.error("provision requires --secrets-out")
            raise SystemExit(provision(Client(), args.secrets_out))
    except AdminError as error:
        print(json.dumps({"failed_endpoint": error.path, "http_status": error.status}))
        raise SystemExit(1)
    except Exception as error:
        print(json.dumps({"failed": True, "error_type": type(error).__name__}))
        raise SystemExit(1)
