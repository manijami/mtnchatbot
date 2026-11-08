"""Synthetic sample content (no real MTN data)."""

LOREM = (
    "The service desk records the incident, confirms the affected service and users, and assigns "
    "an initial severity using the impact and urgency matrix. Communication to stakeholders starts "
    "early and continues at agreed intervals until the service is restored and verified."
)


def incident_process_spec(**overrides):
    spec = {
        "template": "incident_report",
        "title": "IT Incident Management Process",
        "subtitle": "How we detect, respond to and learn from IT incidents",
        "cover_fields": [
            {"label": "Owner", "value": "IT Service Management"},
            {"label": "Version", "value": "1.0 (sample)"},
        ],
        "sections": [
            {"heading": "Purpose", "paragraphs": [LOREM, LOREM]},
            {
                "heading": "Process steps",
                "numbered": [
                    "**Detect and log** the incident in the service desk tool.",
                    "Classify the incident and set its severity.",
                    "Investigate and diagnose the cause.",
                    "Resolve the incident and restore the service.",
                    "Close the incident after the user confirms.",
                ],
            },
            {
                "heading": "Severity levels",
                "table": {
                    "columns": ["Severity", "Description", "Response target"],
                    "rows": [
                        ["P1", "Critical service down for many users", "15 minutes"],
                        ["P2", "Major degradation", "30 minutes"],
                        ["P3", "Minor issue with workaround", "4 hours"],
                        ["P4", "Request or cosmetic issue", "1 business day"],
                    ],
                    "caption": "Table 1. Severity levels and response targets.",
                },
            },
            {"heading": "Roles and responsibilities", "bullets": [LOREM[:160]] * 4},
            {"heading": "Communication", "paragraphs": [LOREM, LOREM, LOREM]},
            {"heading": "Post-incident review", "paragraphs": [LOREM, LOREM, LOREM]},
            {"heading": "Lessons learned", "level": 2, "paragraphs": [LOREM, LOREM]},
        ],
    }
    spec.update(overrides)
    return spec


def deck_spec(**overrides):
    """A five-slide deck (title + 4) exercising bullets, chart, table, key message and notes."""
    spec = {
        "template": "project_status",
        "title": "Network Modernisation Programme",
        "subtitle": "Q3 status review (synthetic sample)",
        "target_slides": 5,
        "slides": [
            {
                "title": "Summary",
                "bullets": [
                    "Programme is on track overall; two workstreams need attention",
                    "68% of sites upgraded against a 70% plan",
                    "Budget spend at 61% with 75% of the year elapsed",
                    "Decision needed on the supplier change for the northern region",
                ],
                "key_message": "On track overall; one decision needed this month",
                "notes": "Open with the overall status, then go to the decision on slide 5.",
            },
            {
                "title": "Site upgrades by quarter",
                "bullets": ["Q3 delivery beat Q2 by 18%", "Northern region still behind plan"],
                "chart": {
                    "type": "column",
                    "categories": ["Q1", "Q2", "Q3"],
                    "series": [
                        {"name": "Plan", "values": [120, 150, 170]},
                        {"name": "Actual", "values": [110, 140, 165]},
                    ],
                },
                "notes": "Actuals are within 5% of plan in every quarter.",
            },
            {
                "title": "Workstream status",
                "table": {
                    "columns": ["Workstream", "Status", "Owner", "Next milestone"],
                    "rows": [
                        ["Radio access", "On track", "Network Ops", "Phase 3 sites live"],
                        ["Transport", "At risk", "Transmission", "Fibre backhaul contract"],
                        ["Core", "On track", "Core Eng", "Cut-over rehearsal"],
                        ["IT systems", "Delayed", "IT", "OSS integration test"],
                    ],
                },
            },
            {
                "title": "Budget by category",
                "chart": {
                    "type": "pie",
                    "categories": ["Equipment", "Services", "Licences", "Other"],
                    "series": [{"name": "Spend", "values": [55, 25, 15, 5]}],
                },
                "key_message": "Equipment remains the largest cost driver",
            },
        ],
    }
    spec.update(overrides)
    return spec


STATUSES = ["Not started", "In progress", "Blocked", "Done"]


def tracker_spec(**overrides):
    owners = ["Service Desk", "Network Ops", "Security", "IT Apps"]
    rows = []
    for i in range(12):
        rows.append([
            f"A-{i + 1:03d}",
            f"Synthetic action item number {i + 1}",
            owners[i % 4],
            f"2026-12-{(i % 27) + 1:02d}",
            STATUSES[i % 4],
            ["High", "Medium", "Low"][i % 3],
            None,
        ])
    spec = {
        "template": "action_tracker",
        "title": "IT Service Improvement Actions (synthetic)",
        "sheets": [{
            "name": "Actions",
            "columns": [
                {"name": "ID"},
                {"name": "Action"},
                {"name": "Owner"},
                {"name": "Due date", "type": "date"},
                {"name": "Status", "allowed_values": STATUSES},
                {"name": "Priority", "allowed_values": ["High", "Medium", "Low"]},
                {"name": "Days left", "type": "formula",
                 "formula": "=IF({Status}=\"Done\",\"\",{Due date}-DATE(2026,11,8))"},
            ],
            "rows": rows,
            "conditional_formats": [
                {"column": "Status", "operator": "equal", "value": "Done", "style": "good"},
                {"column": "Status", "operator": "equal", "value": "Blocked", "style": "bad"},
                {"column": "Priority", "operator": "equal", "value": "High", "style": "warning"},
            ],
            "summary": {"group_by": "Status", "function": "count"},
            "chart": {"type": "pie", "title": "Actions by status", "source": "summary"},
        }],
    }
    spec.update(overrides)
    return spec


def plan_spec(**overrides):
    spec = {
        "template": "project_plan",
        "title": "Portal Rollout Plan (synthetic)",
        "sheets": [{
            "name": "Plan",
            "columns": [
                {"name": "Task"},
                {"name": "Owner"},
                {"name": "Start", "type": "date"},
                {"name": "End", "type": "date"},
                {"name": "Duration (days)", "type": "formula", "formula": "={End}-{Start}"},
                {"name": "% complete", "type": "percent"},
                {"name": "Budget", "type": "currency"},
            ],
            "rows": [
                ["Usability fixes", "Digital", "2026-11-09", "2026-12-04", None, "40%", 45000],
                ["Wave 1 rollout", "Digital", "2026-12-07", "2027-01-29", None, 0.1, 380000],
                ["Identity checks", "Security", "2026-12-01", "2027-02-12", None, 0, 210000],
                ["Wave 2 rollout", "Digital", "2027-02-15", "2027-04-09", None, 0, 520000],
            ],
            "totals": [{"column": "Budget", "function": "sum"}, {"column": "% complete", "function": "average"}],
            "chart": {"type": "bar", "title": "Duration by task", "source": "data",
                      "category_column": "Task", "value_columns": ["Duration (days)"]},
        }],
    }
    spec.update(overrides)
    return spec
