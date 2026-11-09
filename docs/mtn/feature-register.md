# MTN feature register

One entry per MTN feature: what it is, where it lives, and the latest verification. Dev/demo
results use synthetic data only.

## MTN skills (added 2026-11-09)

- **What:** six MTN-curated skills (`mtn/skills/mtn-skills/`), mounted read-only as LibreChat
  deployment skills; listed per assistant with `modelSpecs[].skills`. Sharing off. Catalogue:
  `docs/mtn/skills-catalogue.md`.
- **Assistants:** MTN Smart Chat, MTN Document Assistant (+ Groq fallback); future Workplace
  Assistant.
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
