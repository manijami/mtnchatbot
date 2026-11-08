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
