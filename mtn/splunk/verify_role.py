"""Read effective role configuration without authenticating or displaying secrets.

Run inside the isolated Splunk container as its OS user. This configuration
check supplements, but never substitutes for, authenticated negative tests.
"""
import json
import subprocess

ROLE = "role_mtn_ops_readonly"
text = subprocess.check_output(["/opt/splunk/bin/splunk", "btool", "authorize", "list", ROLE], text=True)
values = dict(line.split(" = ", 1) for line in text.splitlines() if " = " in line)
enabled = sorted(key for key, value in values.items() if value == "enabled")
expected = {"search", "mcp_tool_execute"}
checks = {
    "only_expected_capabilities": set(enabled) == expected,
    "index_allowlist": set(values.get("srchIndexesAllowed", "").split(";")) == {"phoenix_app", "phoenix_net", "phoenix_auth"},
    "no_inherited_roles": not values.get("importRoles", ""),
    "seven_day_window": values.get("srchTimeWin") == "604800",
    "seven_day_age": values.get("srchTimeEarliest") == "604800",
    "runtime_60_seconds": values.get("srchMaxTime") == "60s",
    "concurrency_two": values.get("srchJobsQuota") == values.get("cumulativeSrchJobsQuota") == "2",
    "bounded_queue": values.get("queuedSearchQuota") == "1",
    "storage_100_mb": values.get("srchDiskQuota") == "100",
}
print(json.dumps({"role": ROLE, "enabled_capabilities": enabled, "checks": checks,
                  "configuration_passed": all(checks.values()), "runtime_authorization_tested": False}, indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
