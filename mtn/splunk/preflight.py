"""Read-only prerequisite audit. Prints variable names and status, never secret values."""
from __future__ import annotations

import configparser
import json
import tarfile
import socket
from pathlib import Path

from prepare import ROOT, inspect_archive


def audit() -> list[dict]:
    checks = []
    env = {}
    path = ROOT / ".env"
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                env[name.strip()] = value.strip().strip("\"'")
    for name in ("SPLUNK_PASSWORD", "MTN_SPLUNK_MCP_TOKEN", "MTN_SPLUNK_HEC_TOKEN",
                 "MTN_OFFICE_MCP_TOKEN", "GROQ_API_KEY", "CREDS_KEY", "CREDS_IV", "JWT_SECRET", "JWT_REFRESH_SECRET"):
        checks.append({"check": name, "status": "present" if env.get(name) else "blocked", "note": "Value not displayed; validity requires runtime verification"})
    for name, expected in (("SPLUNK_START_ARGS", "--accept-license"), ("SPLUNK_GENERAL_TERMS", "--accept-sgt-current-at-splunk-com")):
        checks.append({"check": name, "status": "present" if env.get(name) == expected else "blocked",
                       "note": "Only the operator may set acceptance"})
    archive = ROOT / "mtn/splunk/private/splunk-mcp-server.tgz"
    try:
        metadata = inspect_archive(archive)
        checks.append({"check": "official app archive", "status": "present", "note": metadata})
    except (ValueError, OSError, tarfile.TarError, configparser.Error):
        checks.append({"check": "official app archive", "status": "blocked", "note": "Missing or invalid; run prepare.py after operator download"})
    checks.append({"check": "configured official app archive", "status": "present" if (archive.parent / "splunk-mcp-configured.tgz").is_file() else "blocked"})
    checks.append({"check": "generated mtn-demo.tgz", "status": "present" if (archive.parent / "mtn-demo.tgz").is_file() else "blocked"})
    for name in ("ca.pem", "server.pem"):
        checks.append({"check": f"TLS {name}", "status": "present" if (archive.parent / "tls" / name).is_file() else "blocked"})
    for port in (8001, 3081):
        with socket.socket() as probe:
            probe.settimeout(1)
            listening = probe.connect_ex(("127.0.0.1", port)) == 0
        checks.append({"check": f"localhost:{port}", "status": "listening" if listening else "not listening",
                       "note": "Inspect owner before launch if listening; no service is stopped by this audit"})
    return checks


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if any(c["status"] == "blocked" for c in result) else 0)
