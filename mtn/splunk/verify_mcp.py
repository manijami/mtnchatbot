"""Discover installed tools using the real MCP SDK, with verified TLS.

Run explicitly after operator setup in the Office test image (which supplies the
MCP SDK). It uses only MTN_SPLUNK_MCP_TOKEN, never a Splunk admin credential.
An optional JSON case file must use the ACTUAL discovered input schemas. Never
use fabricated results or guessed tool argument names as acceptance evidence.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ALLOWED = {
    "splunk_run_query", "splunk_get_metadata", "splunk_get_sourcetypes",
    "splunk_list_alerts", "splunk_get_alert_details", "splunk_list_fired_alerts", "splunk_get_fired_alert_details",
}


async def main(args):
    token = os.environ.get("MTN_SPLUNK_MCP_TOKEN", "")
    if not token:
        raise ValueError("MTN_SPLUNK_MCP_TOKEN is required")
    context = ssl.create_default_context(cafile=str(args.ca))
    async with httpx.AsyncClient(verify=context, headers={"Authorization": f"Bearer {token}"}, timeout=60) as http:
        async with streamable_http_client("https://splunk:8089/services/mcp", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = []
                cursor = None
                while True:
                    result = await session.list_tools(cursor=cursor)
                    tools.extend(result.tools)
                    cursor = result.nextCursor
                    if not cursor:
                        break
                names = {tool.name for tool in tools}
                evidence = {"tools": [tool.model_dump(mode="json") for tool in tools],
                            "unexpected_tools": sorted(names - ALLOWED), "missing_tools": sorted(ALLOWED - names),
                            "tool_policy_passed": names == ALLOWED, "cases": []}
                if args.cases and names == ALLOWED:
                    for case in json.loads(args.cases.read_text()):
                        if case["tool"] not in ALLOWED:
                            raise ValueError("Case file attempted a disabled tool")
                        result = await session.call_tool(case["tool"], case["arguments"])
                        # Synthetic fixtures only. Raw result records are local/gitignored,
                        # require human assessment, and must never be published with secrets.
                        evidence["cases"].append({"name": case["name"], "result": result.model_dump(mode="json"),
                                                  "status": "requires assessment"})
                args.output.write_text(json.dumps(evidence, indent=2) + "\n")
                print(json.dumps({"tool_policy_passed": names == ALLOWED, "unexpected_tools": sorted(names - ALLOWED),
                                  "missing_tools": sorted(ALLOWED - names), "case_count": len(evidence["cases"])}))
                return 0 if names == ALLOWED else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=Path)
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(main(args)))
    except Exception:
        # An SDK/network exception can echo auth headers or upstream details.
        print("MCP verification failed. Check local setup; no exception text disclosed.")
        raise SystemExit(1)
