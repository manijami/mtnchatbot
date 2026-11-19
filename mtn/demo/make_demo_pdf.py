"""Builds the synthetic demo PDF (fictional figures, no MTN data) with office-mcp itself.

    docker run --rm --network none -v "$PWD/mtn/templates:/app/templates:ro" \
      -v "$PWD/mtn/demo:/out" -e PYTHONPATH=/app mtn-office-mcp:test python /out/make_demo_pdf.py

Writes mtn/demo/Synthetic-Portal-Pilot-Results.pdf (used by docs/mtn/phase4-demo-script.md).
"""
import asyncio, shutil
from pathlib import Path
from office_mcp.config import Settings
from office_mcp.store import Store
from office_mcp.auth import Identity
from office_mcp.tools import ToolContext, registry

P = lambda *t: list(t)
spec = {
  "template": "proposal",
  "title": "Customer Self-Service Portal: Pilot Results",
  "subtitle": "SYNTHETIC SAMPLE for testing only. Fictional figures, not MTN data.",
  "cover_fields": [{"label": "Prepared by", "value": "Digital Channels team (fictional)"},
                   {"label": "Period", "value": "Pilot weeks 1-12"}],
  "sections": [
    {"heading": "Executive summary", "paragraphs": P(
      "The 12-week pilot of the customer self-service portal ran in two regions with 40,000 invited customers. "
      "Adoption reached 31% of invited customers, above the 25% target. Calls to the contact centre for the five "
      "pilot journeys fell by 22% in the pilot regions while staying flat elsewhere.",
      "Customer satisfaction for portal users averaged 4.2 out of 5. The main complaints were slow password resets "
      "and a confusing bill-download page. The team recommends a phased national rollout starting next quarter, "
      "with the two usability fixes completed first.")},
    {"heading": "Pilot scope", "bullets": P(
      "Journeys: bill view and download, data bundle purchase, SIM swap request, complaint logging, password reset",
      "Regions: Region A (urban) and Region B (mixed urban and rural)",
      "Channels: web and mobile web; the native app was out of scope")},
    {"heading": "Results by journey", "table": {"columns": ["Journey", "Portal share", "Call reduction", "CSAT"],
      "rows": [["Bill view/download", "48%", "-35%", "4.0"], ["Data bundle purchase", "39%", "-28%", "4.5"],
               ["SIM swap request", "18%", "-12%", "4.1"], ["Complaint logging", "22%", "-15%", "3.9"],
               ["Password reset", "27%", "-9%", "3.6"]], "caption": "Table 1. Pilot results by journey (fictional)."}},
    {"heading": "Costs", "paragraphs": P(
      "Pilot spend was 410,000 against a budget of 450,000. A national rollout is estimated at 2.1 million over "
      "nine months, with expected annual contact-centre savings of 1.6 million once adoption passes 40%.")},
    {"heading": "Risks", "bullets": P(
      "Rural connectivity limits adoption in mixed regions; mitigate with a lightweight page mode",
      "Identity checks for SIM swap need stronger verification before national launch",
      "Contact-centre staffing plans must follow actual adoption, not forecasts")},
    {"heading": "Recommendation and next steps", "numbered": P(
      "Fix password reset and bill download usability issues (4 weeks).",
      "Approve phased national rollout in three waves starting next quarter.",
      "Add stronger identity verification for SIM swap before wave 2.",
      "Report adoption and call reduction monthly to the steering committee.")},
  ],
}
s = Settings(token='t'*40, data_dir=Path('/tmp/demo-pdf'), templates_dir=Path('/app/templates'), logo_dir=Path('/none'),
             host='', port=1, retention_days=0, convert_timeout_s=60, max_file_bytes=20<<20, preview_image=False)
st = Store(s.data_dir)
out = asyncio.run(registry['create_word_document'].run(ToolContext(settings=s, store=st, identity=Identity(user_id='a'*24)), spec))
print(out[0].text.split('\n')[0])
d = st.list_documents('a'*24)[0]
shutil.copy(st.files_dir/('a'*24)/d.id/'v1'/'preview.pdf', '/out/Synthetic-Portal-Pilot-Results.pdf')
