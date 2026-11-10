# MTN feature register

One entry per MTN feature: what it is, where it lives, and the latest verification. Dev/demo
results use synthetic data only.

## MTN skills (added 2026-11-09)

- **What:** six MTN-curated skills (`mtn/skills/mtn-skills/`), mounted read-only as LibreChat
  deployment skills; listed per assistant with `modelSpecs[].skills`. Sharing off. Catalogue:
  `docs/mtn/skills-catalogue.md`.
- **Assistants:** MTN Smart Chat, MTN Document Assistant (Groq default; Nemotron selectable);
  future Workplace Assistant.
- **Where each skill style runs:** the **MTN Document Assistant is file-first**: when a request
  implies a document it builds the file directly and often skips the skill. **MTN Smart Chat is
  where the chat-style skills run** (minutes, briefs, emails, status reports, summaries, privacy
  checks), with a file offered or built on request.
- **Skill creation:** MTN-curated only (`interface.skills.create: false`, 2026-11-09).
- **Changes to make it work** (details in the CLAUDE.md decisions log, 2026-11-09):
  - five skill descriptions shortened to 180 characters or fewer (catalogue entries are cut at
    250 characters including the name);
  - one line in the Smart Chat and Document Assistant prompts: load a matching skill first;
  - router: tool calling on for the judged Smart Chat routes; skill tools kept on text tiers;
    LibreChat's injected skill text no longer mistaken for the user's request; skill steps on a
    fixed tier (balanced, Groq `gpt-oss-120b`); documents/skill steps fall back to their backup
    route when the provider does not answer within 45 s.

### Test run 2026-11-09 (MTN Smart Chat, synthetic prompts)

NVIDIA-hosted Nemotron 3 Ultra was not answering during the run (60 s timeouts), so turns the
router sent to it waited 45 s and then used the Groq backup.

| ID | Prompt (shortened) | Expected | Skill loaded | Result | Time |
|---|---|---|---|---|---|
| MM-T1 | "Minute this: Ops sync 10 Nov, chair Sipho…" | meeting-minutes | meeting-minutes | Pass (after the prompt line; the first try on the fast tier answered without the skill) | 5.2 s |
| MM-T2 | "Turn these notes into minutes with decisions and actions…" | meeting-minutes | none | **Miss**: good minutes, but written without the skill | 3.1 s |
| MM-N | "What time zone is Johannesburg in?" | none | none | Pass | 2.2 s |
| EB-T1 | "Brief me on Project Phoenix for the CEO…" | executive-brief | executive-brief | Pass | 4.2 s |
| EB-T2 | "One-page exec summary for leadership: uptime 99.2% vs 99.5%…" | executive-brief | executive-brief | Pass | 4.4 s |
| EB-N | "Difference between a CEO and a COO?" | none | none | Pass | 2.8 s |
| ED-T1 | "Draft an email to Thandi asking for the tower delay report…" | email-drafter | email-drafter | Pass | 3.1 s |
| ED-T2 | "Polite reply declining a vendor's golf day…" | email-drafter | email-drafter | Pass (two versions, as the skill asks) | 3.2 s |
| ED-N | "What does CC mean in an email?" | none | none | Pass | 2.7 s |
| PS-T1 | "RAG status report for Project Phoenix…" | project-status-report | project-status-report | Pass | 5.2 s |
| PS-T2 | "Steering committee update, Fibre Rollout: 120 of 200 sites…" | project-status-report | project-status-report | Pass (judge chose the capable tier: 45 s NVIDIA timeout, then backup) | ~49 s |
| PS-N | "What does RAG stand for in project management?" | none | none | Pass | 2.9 s |
| DS-T1 | "Summarise this policy: Travel policy v2…" | document-summariser | document-summariser | Pass | 5.1 s |
| DS-T2 | "What does this policy say about late claims?…" | document-summariser | none | **Miss**: correct short answer with the section, without the skill | 3.1 s |
| DS-N | "Write a haiku about the ocean." | none | none | Pass | 2.1 s |
| PP-T1 | "Is this safe to share with a supplier? 'Customer…, ID…, mobile…'" | popia-privacy-check | popia-privacy-check | Pass (risk High, masked values) | 4.1 s |
| PP-T2 | "Check this draft for POPIA issues…" | popia-privacy-check | popia-privacy-check | Pass on retry (first attempt: the browser send never started; no reply was created) | 4.6 s |
| PP-N | "What year did POPIA come into full effect?" | none | none | Pass | 2.1 s |

**Summary:** trigger prompts 10 of 12 loaded the right skill (2 answered well without it);
non-trigger prompts 6 of 6 left skills alone (no false triggers).

### File-output cases

| ID | Assistant | Steps | Result |
|---|---|---|---|
| F1 | MTN Smart Chat | MM-T1 minutes (skill) → "Yes please, create the Word document." | Pass: `create_word_document` (meeting_minutes template) → `Ops-sync-minutes.docx`, 51 KB. Slow (~95 s) only because two documents steps each waited 45 s for NVIDIA before the Groq backup |
| F2 | MTN Document Assistant (Groq fallback) | "Brief the CEO on Project Phoenix as a short PowerPoint deck…" | File pass: `create_powerpoint_presentation` → `Project-Phoenix-Update.pptx`, 55 KB. The closing message hit **Groq's free-tier rate limit** (error shown under the file). The skill was not loaded: the Document Assistant is file-first by design |

### Known issues

- Skill use depends on the model choosing it; prompts that are short or phrased as questions
  sometimes get a direct answer instead (MM-T2, DS-T2). Users can force a skill with `$`.
- Groq free tier: large requests (skill catalogue + tools + instructions) can hit the rate limit.
- When NVIDIA-hosted Nemotron does not answer, documents and capable-tier turns take about 45 s
  longer (timeout, then the Groq backup).

## Excel insights (E1–E4, 2026-11-10)

Upload a spreadsheet, get a summary whose numbers come only from office-mcp (`inspect_workbook`,
`analyse_workbook`), then files from the saved run (`create_insights_files`). Skill:
`excel-insights` (Smart Chat, Document Assistant, Groq fallback). `.xlsx`/`.csv` uploads use the
`none` delivery path, so rows never reach the model; the model lists uploads with
`inspect_workbook` and no file name. Synthetic workbook: 18 months, 5 regions, 4 products,
362 rows (3 blank Revenue, 2 duplicates, one R950k outlier in January 2025).

### Browser run 2026-11-10 (MTN Document Assistant (Nemotron), synthetic data)

| ID | Prompt | Result |
|---|---|---|
| XI-1 | "Please analyse the attached sales workbook (synthetic data) and give me the key insights." | Pass with issues: skill loaded, first `inspect_workbook` guessed `sales.xlsx` (from the tool example; fixed), then listed uploads, inspected and ran 6 analyses. Region, product, month and outlier figures match the run. **Model-derived numbers** in chat: "nearly 1.5×", LTE Home "33.5 %", 2026 vs 2025 averages; "2 duplicate rows excluded" was false (duplicates are reported, never removed). Skill rules tightened |
| XI-2 | "Create the infographic, PowerPoint, Excel workbook, chart images and HTML dashboard … also an in-chat dashboard." | Files pass: 10 files (5 chart PNGs, infographic PNG + PDF, HTML dashboard, 9-slide deck with native charts, 6-sheet workbook with native charts). The number check refused 4 drafts before the insights used only result numbers. In-chat dashboard: **markdown table, not an artifact** |
| XI-3 | New chat, analyse + "show them as an in-chat dashboard" (after the skill fix) | No ratios this time; duplicates reported as notes. No artifact: the model made the HTML file again. Asking explicitly for an artifact made it loop on `read_file`/regenerating the file (stopped) |
| XI-4 | Same in MTN Smart Chat (documents tier) | Summary as a markdown table; called the static HTML file "interactive". No artifact |

### Fixes from this run

- office-mcp worker crash (`BrokenWorkerProcess`, relative import in `__main__.py` when anyio's
  worker re-runs it by path): absolute imports + a regression test.
- Number check: category labels with digits ("Fibre 100", bin labels) are no longer read as
  quoted numbers (they blocked Smart Chat's files).
- Tool descriptions no longer give `sales.xlsx` as an example name; the example lists uploads first.
- Chart axes show 500k / 1.5m instead of a "1e6" offset.
- Workbook logo placed right of the data columns and the title (it covered the title on narrow
  sheets).
- Skill: no derived ratios/shares/averages (add an analysis instead); only `rows_left_out` counts as
  excluded; the in-chat dashboard must be an artifact; the HTML file is static.

### Known issues (Excel insights)

- **In-chat artifact dashboard not produced** by Nemotron 3 Ultra in either assistant, even when
  asked explicitly (the artifacts prompt is attached). The HTML dashboard file is the dashboard
  for now. Retest with Groq `gpt-oss-120b` once the paid tier is active.
- Words are not checked: the number check cannot stop wrong claims in prose (for example
  "1 outlier was excluded" reached the infographic and dashboard). Chat text is not checked at all.
- Deck charts show at most 12 categories (the monthly chart drops the January 2025 spike); deck
  bar charts list the largest bar at the bottom.
- Skill catalogue entries reached the model cut to 158 chars in one run (limit appears to shrink
  as the prompt grows); the descriptions still start with the trigger words.
- Nemotron once spent about 3 minutes reasoning with no output (stopped and regenerated).
