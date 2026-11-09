# MTN skills catalogue

MTN-curated skills for the MTN Employee AI assistants. They live in `mtn/skills/mtn-skills/`
(one folder per skill, `SKILL.md` inside), are mounted read-only into LibreChat as
**deployment skills** (`/app/skill`), and are available to **MTN Smart Chat**, **MTN Document
Assistant** (and its Groq fallback) and, later, the **Workplace Assistant** (`modelSpecs[].skills`
in `mtn/config/librechat.yaml`).

**How employees use them**

- **Automatically:** describe the task ("minute this", "brief me on…"). The assistant loads the
  matching skill and follows it.
- **On purpose:** type `$` in the message box and pick a skill.
- Skills are read-only and maintained by MTN. Employees may keep private skills of their own;
  sharing skills with others is switched off.

| Skill | Who it's for | What it produces | Example prompt | Can offer a file |
|---|---|---|---|---|
| `meeting-minutes` | Anyone who chairs or minutes meetings | MTN-style minutes: decisions, actions (owner, due date), open questions, "please check" notes | "Minute this: Ops sync 10 Nov, chair Sipho… decided to freeze changes… Naledi to send the notice by 20 Nov." | Word (`meeting_minutes` template); Excel action tracker (`action_tracker`) |
| `executive-brief` | Managers preparing updates for executives | A one-page brief: bottom line first, key points, risks, decision needed, sources | "Brief me on Project Phoenix for the CEO: go-live moved to 1 Dec, budget 85% spent." | Word (`proposal`); PowerPoint (`executive_update`) |
| `email-drafter` | All employees | A draft email with subject, in MTN's tone; two versions for sensitive messages; never sends | "Draft an email to Thandi asking for the updated tower delay report by Friday." | No |
| `project-status-report` | Project managers, PMO | Red/amber/green status report: milestones, achievements, risks, decisions needed | "Give me a RAG status report for Project Phoenix: build 2 weeks late, testing not started." | PowerPoint (`project_status`); Excel (`project_plan` / `action_tracker`) |
| `document-summariser` | Anyone reading policies, contracts or reports | Key points, obligations, dates and thresholds, exceptions, with section citations | "Summarise this travel policy and tell me the per-diem rule." | No |
| `popia-privacy-check` | Anyone about to share a draft, email or dataset | Personal information found, risk rating for the audience, suggested redactions, a redacted version | "Is this safe to share with a supplier? 'Customer …, ID …, mobile …'" | No |

All example prompts above must use synthetic data while the assistants run on the Groq and
NVIDIA dev providers.

**Notes**

- The MTN Document Assistant is file-first: when a request implies a document, it builds the file
  directly and may not load a skill. Smart Chat is the natural home for the chat-style skills.
- Skill descriptions must stay within about 180 characters: LibreChat cuts each catalogue entry at
  250 characters including the name, and anything cut off never reaches the model.
- Test results: `docs/mtn/feature-register.md` → "MTN skills".
