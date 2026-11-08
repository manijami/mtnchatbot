# MTN Employee AI Assistant — Handover Report

**Last updated:** 2026-11-08 (Phase 0 accepted; Phase 1 done with placeholder copy; **Phase 4 built and
acceptance-tested on branch `mtn/phase4-office`**, speed pass done; second-user API check not yet observed, §11)
**Prepared for:** external reviewer / incoming contributor
**Scope:** upstream LibreChat running locally via Docker, with MTN configuration, a thin branding
image, the **office-mcp** document service, and **one approved core change** (MCP file outputs,
§11), deployed locally as a backend overlay on the digest-pinned upstream image.

---

## 1. Repository state

| Field | Value |
|---|---|
| Branches | `mtn/employee-ai` (Phases 0–1, pushed) · `mtn/phase4-office` (Phase 4, from `d27c5098a`; remote at `587113cab`, later commits not pushed) |
| Upstream base | `f4154b649` — "🦿 chore: Bump Agents SDK to 4.2.1 (#17664)" (2026-10-31) |
| `package.json` version | `v0.8.9-rc1` (`git describe`: `v0.8.9-rc1-84-gf4154b649`) |
| Remotes | `origin` → `https://github.com/manijami/mtnchatbot.git`; `upstream` → `https://github.com/LibreChat-AI/LibreChat.git` (no credentials in URLs) |
| MTN commits | `mtn/employee-ai`: 6. `mtn/phase4-office`: +21 (Phase 4). Full list in §8. |
| Source diff vs upstream | **One approved core deviation** (MCP file outputs): `packages/data-provider` (schema field, default off), `packages/api` (logic + tests), ~75 lines of `/api` wiring. Everything else is MTN files: `CLAUDE.md`, `docs/mtn/`, `mtn/`, `.env.mtn.example`, `.gitignore`. |
| Licensed assets | MTN Brighter Sans fonts and official logo files are in gitignored `mtn/branding/private/` and were **never committed** (checked before each commit). |

### Toolchain (this machine) — all match the repo pins

| Tool | Version | Pinned by repo | Match |
|---|---|---|---|
| Node.js | `v24.22.1` | `.nvmrc` → `24.22.1` | ✅ |
| npm | `11.13.0` | `package.json` → `npm@11.13.0` | ✅ |
| Docker Engine (Docker Desktop) | `20.10.24` | — | reachable ✅ |
| Docker Compose | `v2.17.2` | — | ✅ |

The Node 22 / npm 10 mismatch and the unreachable Docker daemon reported in the previous version of
this report are **resolved**.

---

## 2. What Phase 0 changed

### Tracked (committed)

| Path | Change |
|---|---|
| `CLAUDE.md` | Now **tracked** (force-added; `.gitignore:187` still matches it, so future edits need `git add -f` again only if it is ever removed from the index). Edits listed below. |
| `docs/mtn/HANDOVER_REPORT.md` | This report. |

**`CLAUDE.md` edits in Phase 0:**

1. Removed the duplicated "privacy/ToS, inline MTN theme, brand assets" in the Phase 1 description.
2. Added **Phase 4 — Office document generation**: (a) self-hosted Code Interpreter — the
   `librechat-code` service, `LIBRECHAT_CODE_BASEURL` + `LIBRECHAT_CODE_API_KEY`, `execute_code`
   capability, sandbox image with `python-docx`, `python-pptx`, `openpyxl`, `pandas`,
   `matplotlib`; (b) MCP tools backed by versioned MTN templates — `create_word_document`,
   `create_powerpoint_presentation`, `create_excel_workbook`, `revise_office_file` — with file
   validation, previews, revision in chat, and per-user file ownership. Former Phases 4 and 5 are
   now **Phase 5** (MTN-specific capability) and **Phase 6** (hardening & observability).
3. **Auth decision replaced** (2026-11-08, supersedes 2026-11-07): local registration enabled in
   **dev** only; **production** sets `ALLOW_REGISTRATION=false`, keeps `ALLOW_EMAIL_LOGIN=true`
   for admin-provisioned accounts (`create-user` / `invite-user`), and **SSO (OIDC + SAML) is the
   main way in**. Logged in the decisions log.
4. New rule under "Security & secrets": **never commit `.claude/helpers/` or
   `.claude/settings.local.json`** (per-machine Claude Code tooling).

### Local only (gitignored — never committed)

| Path | Ignored by | Purpose |
|---|---|---|
| `.env` | `.gitignore:83` (`.env*`) | Created from `.env.example`, mode `600`. See §5. |
| `librechat.yaml` | `.gitignore:79` | Since Phase 1: a **symlink** to the tracked `mtn/config/librechat.yaml` (see §9). |
| `docker-compose.override.yml` | `.gitignore:115` | Mounts only, with no image or service changes: `mtn/config/librechat.yaml` → `/app/librechat.yaml`, plus the Phase 1 placeholder assets over `/app/client/dist/...` (see §9 for the full file). |
| `uploads/`, `logs/`, `images/` | `.gitignore` | Runtime bind mounts created by the stack. |
| `.claude/helpers/*`, `.claude/settings.local.json*` | `/.claude/` | Claude Code hook scripts / local permissions (unchanged in Phase 0). |

---

## 3. Project guide

The authoritative MTN project guide is the committed **`CLAUDE.md`** at the repo root (read
`AGENTS.md` first — upstream contributor rules). It is no longer reproduced here to avoid drift.

Current phase plan (from `CLAUDE.md`). **Execution order: 0 (done) → 1 → 4 → 2 → 3 → 5 → 6**.
Phase numbers are stable IDs. Phase 4 moved up because it is not blocked on MTN inputs and is the
key demo value.

| Phase | Description | Status |
|---|---|---|
| 0 — Baseline & environment | Clean local run, version/commit/remote confirmed | **Done** (this report) |
| 1 — Configuration & branding | Title, footer, help URL, welcome, privacy/ToS, MTN theme, assets; curate `modelSpecs` later | **Done** (§9). Copy, URLs and policy text are still placeholders waiting on MTN. Dark-mode accents use MTN yellow; contrast and 390px checks in §10 |
| 2 — Identity & access | OIDC + SAML as main way in; prod `ALLOW_REGISTRATION=false`; roles, Admin Panel | Not started — waiting on MTN IdP details |
| 3 — Infrastructure & data | Mongo/Meili/pgvector/RAG/file storage on MTN-managed services | Not started |
| 4 — Office document generation | Self-hosted Code Interpreter + template-driven Office MCP tools | Not started (new) |
| 5 — MTN-specific capability | New levers in `packages/api` with `configSchema` defaults; MTN MCP/knowledge sources | Not started |
| 6 — Hardening & observability | CSP, rate limits, moderation, OTel/Langfuse, budgets, a11y, i18n, full gates | Not started |

---

## 4. Feature register

Columns: **Feature | Available in version | Required config/service | Enabled for employees |
Validation scenario | Test result**. Tested on 2026-11-08 against the local Docker stack (§6) with
the **Groq** custom endpoint, model `openai/gpt-oss-120b`, as test user `phase0tester` (local account).

| Feature | Available in version | Required config/service | Enabled for employees | Validation scenario | Test result |
|---|---|---|---|---|---|
| Multi-provider chat (OpenAI, Azure OpenAI, Anthropic, Google, Bedrock, custom) | v0.8.9-rc1 (core) | `librechat.yaml` `endpoints` + provider API keys in `.env` | Dev: Groq and **NVIDIA** `custom` endpoints (dev-only, synthetic data). Primary MTN provider still deferred. | Send a message on each configured endpoint, confirm a response | **Tested OK** (Groq custom endpoint): message sent; response **streamed** incrementally (reasoning then answer visible mid-generation); answer complete. **NVIDIA Nemotron 3 Ultra (2026-11-08): Tested OK** — streamed; reasoning arrives in `reasoning_content` and is stored as a separate `think` part shown in the Thoughts panel, never in the answer; title generated by Groq `gpt-oss-20b` (`titleEndpoint`); NVIDIA rejects native PDF parts (400) so PDFs go as text. Other providers **not tested** — no keys. |
| Conversation history & auto titles | v0.8.9-rc1 (core) | Mongo; `titleConvo`/`titleModel` | Default-available | Reload a conversation; check sidebar and stored title | **Tested OK**: after page reload the conversation and messages reloaded from the server; sidebar listed it with a generated title ("Container Orchestrator Smoke Test", via `openai/gpt-oss-20b`). Mongo: 4 conversations, 8 messages. |
| Agents (no-code custom assistants) | v0.8.9-rc1 | Mongo; `agents` endpoint enabled | Default-available, not yet reviewed for MTN policy | Create an agent, chat with it, confirm persistence | **Tested OK**: created "Phase0 Test Agent" (provider `groq`, `openai/gpt-oss-120b`) with instructions to prefix replies `AGENT-OK:`; chat reply was `AGENT-OK: 144`; agent persisted in Mongo. |
| Agent Marketplace / sharing | v0.8.9-rc1 | Roles/permissions config | Not reviewed | Share an agent with another user/role | **Not tested** — only one test user; out of Phase 0 scope. |
| Skills (`SKILL.md` bundles) | v0.8.9-rc1 | Agent config | Not reviewed | Attach a skill to an agent, invoke it | **Not tested** — out of Phase 0 scope. |
| Subagents | v0.8.9-rc1 | Agents endpoint | Not reviewed | Delegate a task to a subagent | **Not tested end to end.** Phase 4 unit test: an MCP file output from a subagent's tool call is delivered to the parent response with no base64 in history (`mcpOutputs.subagent.spec.ts`). |
| Agent Management API (beta) | v0.8.9-rc1 (beta) | Deployment-bound OIDC client | Not configured | Call the documented endpoints | **Not tested** — needs OIDC (Phase 2). |
| Attached code workspaces (experimental) | v0.8.9-rc1 (experimental) | `librechat-code` worker | Not configured | Point an agent at a workspace, run a command | **Not tested** — no code worker (Phase 4). |
| Agent Plugins (experimental) | v0.8.9-rc1 (experimental) | Startup-loaded Skill/MCP bundles | Not configured | Bundle a plugin at startup, confirm load | **Not tested** — not configured. |
| Code approval controls | v0.8.9-rc1 | Admin role grants | Not configured | Set a policy, attempt exec, confirm enforcement | **Not tested** — no code worker. |
| MCP (Model Context Protocol) | v0.8.9-rc1 | `mcpServers` config | Dev: `mtn-office` (internal network, admin `apiKey`, per-user `X-MTN-User-Id`) | Register an MCP server, invoke a tool | **Tested OK** (Phase 4): per-user connection initialises on enable; tools called from chat (Groq and NVIDIA); see Office rows below. |
| Code Interpreter | v0.8.7+ (self-hosted ClickHouse/code-interpreter, Apache-2.0) | Code API stack + `LIBRECHAT_CODE_BASEURL` + `CODEAPI_JWT_*`; **KVM host** for safe isolation | **Deferred to Phase 3** (decision 2026-11-08). This dev Mac's Docker VM has no `/dev/kvm` | Run a snippet, confirm sandboxed output | **Not tested**: deferred. Not needed for Phase 4 (Office generation uses validated JSON, not code) |
| Python data analysis of uploaded spreadsheets | via Code Interpreter (`execute_code`) | Code Interpreter (above) with `pandas`/`openpyxl`/`matplotlib` in the sandbox | **Phase 3 requirement** (recorded 2026-11-08) | Upload an .xlsx, ask for a summary and a chart | **Not tested**: depends on the Phase 3 Code Interpreter |
| RAG / file search | v0.8.9-rc1 | `rag_api` + pgvector + embeddings provider | Dev: NVIDIA `nvidia/nemotron-3-embed-1b` via `mtn/deploy/compose.rag-nvidia.yml` (synthetic data only) | "Upload for File Search", ask about it | **Tested OK** (2026-11-08): synthetic PDF embedded (3 chunks, 2048-dim, ~1 s); question answered from retrieval (`/query` → NVIDIA embedding → pgvector) with the correct figures (CSAT 4.1, −12%). Other live NVIDIA embedding models need `input_type`, which rag_api's OpenAI client cannot send. |
| File upload → chat (PDF as context) | v0.8.9-rc1 | `fileStrategy: local` (default); `fileConfig` delivery path | Dev: enabled | Upload a PDF, ask about its contents | **Tested OK after a config fix.** 1st attempt **failed**: Groq returned 400 because LibreChat sent the PDF as a native provider document part, which Groq rejects. Fixed in `librechat.yaml` (no code): `fileConfig.endpoints.groq.defaultLLMDeliveryPath.overrides['application/pdf']: text`. Retest: model answered all three facts from the PDF correctly. |
| Web search | v0.8.9-rc1 | Search provider + scraper keys | Not configured | Ask a question needing live web data | **Not tested** — no keys. |
| Code Artifacts (React/HTML/Mermaid) | v0.8.9-rc1 | Default UI | Default-available | Request a Mermaid diagram, confirm preview | **Not tested** — out of Phase 0 scope. |
| Image generation | v0.8.9-rc1 | Provider key or MCP | Not configured | Request an image | **Not tested** — no image provider. |
| Presets, forking, branching | v0.8.9-rc1 (core) | None | Default-available | Fork a message, edit and resubmit | **Not tested** — out of Phase 0 scope. |
| Resumable streams | v0.8.9-rc1 | Optional Redis | Not configured | Drop connection mid-stream, confirm resume | **Not tested** — out of Phase 0 scope (no Redis). |
| Speech (STT/TTS) | v0.8.9-rc1 | STT/TTS provider key | Not configured | Dictate, play back | **Not tested** — no keys. |
| Import/export conversations | v0.8.9-rc1 (core) | None | Default-available | Export and re-import | **Not tested** — out of Phase 0 scope. |
| Message/conversation search | v0.8.9-rc1 | `SEARCH=true` + Meilisearch | Not configured (`SEARCH=false` default) | Search for a known string | **Not tested** — `SEARCH=false`. Meilisearch container runs. |
| Auth — local (email/password) | v0.8.9-rc1 | `ALLOW_EMAIL_LOGIN`, `ALLOW_REGISTRATION` | **Dev:** registration on. **Prod:** `ALLOW_REGISTRATION=false`, email login kept for admin-provisioned accounts. | Register a user, log in | **Tested OK**: registered via `/register`, redirected to login, logged in. User stored with `provider: local`; upstream made this **first** user `ADMIN`. |
| Auth — OIDC | v0.8.9-rc1 | OIDC client vs MTN IdP | Planned main way in (Phase 2) | OIDC login round-trip | **Not tested** — blocked on MTN IdP details. |
| Auth — SAML | v0.8.9-rc1 | SAML SP vs MTN IdP | Planned main way in (Phase 2) | SAML login round-trip | **Not tested** — blocked on MTN IdP metadata. |
| Auth — LDAP | v0.8.9-rc1 | LDAP server | Not planned | Bind against LDAP | **Not tested**. |
| Admin Panel | v0.8.9-rc1 | `ADMIN_PANEL_SESSION_SECRET`; `admin-panel` service | Dev: running on **:3001** | Log in as admin, edit a role | **Not tested** (functionally). Container is **healthy** and serves HTTP 200 on `http://localhost:3001`; admin login/role edit not exercised. |
| Observability (OTel / Langfuse) | v0.8.9-rc1 | `otel/` config | Not configured | Generate a trace | **Not tested**. |
| S3/CloudFront storage | v0.8.9-rc1 | AWS creds, `fileStrategy` | Not configured (Phase 3) | Upload, serve via CDN | **Not tested**. |
| Multilingual UI | v0.8.9-rc1 (core) | None | Default-available | Switch language | **Not tested** — out of Phase 0 scope. |
| Deployment theming | v0.8.9-rc1 | `interface.theme` + branding image | Dev: inline **MTN** theme, official logo, **MTN Brighter Sans** | Apply inline theme, check light and dark, fonts, contrast, mobile | **Tested OK** (Phase 1): theme accepted by the server validator. Light mode: black primary buttons, yellow-tint user bubble and selected nav. Dark mode: MTN yellow for focus, links, primary buttons (black label) and a yellow-tinted selected row. Brand font **loaded** (computed `"MTN Brighter Sans"`; faces 300/400/500–600 loaded). Contrast: 100/102 pairs pass; **dark mode 51/51**. The 2 failures are light-mode selection fills at the upstream level (§10). Login, chat and sidebar checked at 390px in both modes (§10). |
| Manual context compaction | v0.8.9-rc1 | None | Default-available | Trigger summarize-only turn | **Not tested** — out of Phase 0 scope. |
| **Office: MCP file outputs (MTN core change)** | MTN Phase 4 (`587113cab`, `59b989ecd`) | `mcpServers.<name>.fileOutputs.enabled` in `librechat.yaml` (default off; YAML servers only) | Dev: `mtn-office` only | Tool returns a .docx/.pptx/.xlsx resource → user-owned attachment | **Tested OK**: file card on the message; record `context: mcp_output`, owner = user; survives reload; saved message has no base64; downloaded bytes = office-mcp SHA-256. Unit/integration: 16 + 4 + 6 + 3 (packages/api) + 3 (callbacks). |
| **Office: Word documents** | MTN Phase 4 | office-mcp `create_word_document`, templates `mtn/templates/word/*/v0.1` | Dev: via MTN Document Assistant | "Create a two-page Word document explaining an IT incident process." | **Tested OK** (Nemotron): 2 pages (target met), logo, cover table, numbered steps; reopened with python-docx and rendered by LibreOffice. 2nd model call (first rejected by LibreChat's own schema check). |
| **Office: PowerPoint** | MTN Phase 4 | `create_powerpoint_presentation`, fit + bounds check | Dev: via MTN Document Assistant | "Create a five-slide presentation summarising the attached PDF" | **Tested OK** (Nemotron): 5 slides, bounds check 0 issues (36 shapes), native table, notes; figures only from the PDF. 3rd call (fixable errors: `numbered` on a slide, 7 bullets). |
| **Office: Excel** | MTN Phase 4 | `create_excel_workbook`, LibreOffice recalculation check | Dev: via MTN Document Assistant | Tracker with formulas, filters, highlighting, chart | **Tested OK** (Nemotron, 1st call): table with filters, dropdowns, conditional formats, summary + chart; 13 formulas recalculated, 0 errors. |
| **Office: revisions (v2 keeps v1)** | MTN Phase 4 | `revise_office_file`, `get_generation_status` | Dev | "Shorten slide 2 and add a risks table to slide 5" | **Tested OK** (Nemotron, 1st call): slide 2 5→4 bullets, slide 5 gains the table, slides 3–4 unchanged; v1 file byte-identical (stored hash = disk). |
| **Office: owner isolation** | MTN Phase 4 | office-mcp owner scoping; LibreChat file ACLs | Dev | Second user lists / previews / downloads the owner's file | office-mcp: **Tested OK** (valid token + other user's `X-MTN-User-Id` → 404 for every version and artifact). LibreChat API with a real second user: **not yet observed** (§11). |
| **MTN Document Assistant** | MTN Phase 4 (`cfa671e22`) | `modelSpecs` (default: NVIDIA Nemotron 3 Ultra; fallback: Groq `gpt-oss-120b`), `mcpServers: [mtn-office]`, File Search | Dev: default for new chats | Pick from the model menu, use a conversation starter | **Tested OK**: default on new chat with File Search + MTN Office chips and 3 starters; acceptance tests above ran on it. |

**Phase 4 acceptance (2026-11-08, Nemotron 3 Ultra, after the speed pass):** Word ✅ · five-slide PDF
deck ✅ · Excel tracker ✅ · revision v2 keeps v1 ✅ · files open cleanly + previews inspected ✅ ·
second-user LibreChat API check ⏳ not yet observed (§11). Demo script: `docs/mtn/phase4-demo-script.md`.

**Phase 0 acceptance (all passed):** register test user ✅ · send chat message ✅ · streaming ✅ ·
history ✅ · upload PDF and ask about it ✅ (after config fix) · create agent ✅.

---

## 5. Environment and configuration (redacted)

### `.env` (gitignored, mode 600) — names only, no values

Created by copying `.env.example` and changing only:

| Variable | Setting |
|---|---|
| `CREDS_KEY` (64 hex), `CREDS_IV` (32 hex), `JWT_SECRET`, `JWT_REFRESH_SECRET`, `MEILI_MASTER_KEY`, `ADMIN_PANEL_SESSION_SECRET` (64 hex each) | Freshly generated with `openssl rand -hex 32` / `-hex 16` (the method documented in `.env.example`). Never printed or logged. |
| `UID` / `GID` | From `id -u` / `id -g` (`501` / `20`). |
| `ALLOW_REGISTRATION` | `true` (dev). `ALLOW_EMAIL_LOGIN=true` unchanged. |
| `GROQ_API_KEY` | Uncommented; **value entered by the user**. |
| `ADMIN_PANEL_PORT` | `3001` — host port 3000 is used by a local Grafana. |
| `NVIDIA_API_KEY` | Entered by the user (Phase 4). Used by the `nvidia` endpoint and, via compose interpolation, by rag_api embeddings. |
| `MTN_OFFICE_MCP_TOKEN` | Generated with `openssl rand -hex 32` straight into `.env` (Phase 4); shared by LibreChat (`apiKey`) and office-mcp only. Never printed. |
| `COMPOSE_FILE` | `docker-compose.yml:docker-compose.override.yml:mtn/deploy/compose.office.yml:mtn/deploy/compose.rag-nvidia.yml` |
| `SCHEDULES_SINGLE_PROCESS` | `true` (added after Phase 0 acceptance, local dev only). Asserts a single API replica so the schedules engine arms without Redis. API log now shows `[schedules] engine started`. Do **not** carry this to multi-replica deployments; use Redis streams there. |

Everything else is the upstream `.env.example` default (e.g. `PORT=3080`, `SEARCH=false`, provider
keys `user_provided`). The MTN variable **names** are listed in the tracked `.env.mtn.example`.

### `librechat.yaml`

The current, tracked config is **`mtn/config/librechat.yaml`** (no secrets; keys are `${ENV}`
references). The Phase 0 snapshot that used to be here is in git history (`048140573`). It has
the same Groq endpoint and PDF `fileConfig` override, without the Phase 1 branding.

The Groq models listed in `librechat.example.yaml` (`llama3-*`, `mixtral-*`, `gemma-*`) are retired;
the defaults in `mtn/config/librechat.yaml` are models the key can actually use (verified via Groq `/models`).

---

## 6. Running stack (`docker ps`, 2026-11-08)

| Container | Image | State | Ports |
|---|---|---|---|
| `LibreChat` (api) | **`mtn-librechat-core:local`** = `mtn-librechat:local` (branding, FROM `librechat-dev@sha256:9625652b…`, commit `f4154b649`) + core-deviation overlay (`mtn/deploy/core.Dockerfile`) | Up | `3080` |
| `office-mcp` | **`mtn-office-mcp:0.1.0`** (python:3.12-slim-bookworm@sha256, LibreOffice 7.4.7, hash-locked wheels; 611 MB) | Up **(healthy)**; internal `office` network only, no published ports, no internet, 768 MB / 1 CPU, read-only rootfs | none |
| `admin-panel` | `librechat-admin-panel:latest` | Up **(healthy)** | `3001→3000` |
| `chat-mongodb` | `mongo:8.0.20` | Up | internal |
| `chat-meilisearch` | `getmeili/meilisearch:v1.35.1` | Up | internal |
| `vectordb` | `pgvector/pgvector:0.8.0-pg15-trixie` | Up | internal |
| `rag_api` | `librechat-rag-api-dev-lite:latest` | Up; embeddings via NVIDIA (`compose.rag-nvidia.yml`) | internal |

Only `admin-panel` defines a Docker healthcheck; the others were verified by state + logs + HTTP.

- Start/stop: `docker compose up -d` / `docker compose down` (data persists in named volumes; office-mcp records in `office-data`).
- Build order (api): `docker build -t mtn-librechat:local mtn/branding` → `npm run build:data-provider && npm run build:api`
  → `docker compose build api`. The overlay build **fails** unless the base matches commit `f4154b649`
  (`mtn/deploy/base-fingerprint.sha256`). Upstream upgrades: CLAUDE.md "Upgrading the upstream base".
- Docker VM: raised to **7.96 GB** RAM on 2026-11-08 (was 2.99 GB).
- The branding image contains licensed fonts and the official logo. **Never push it to a public registry.**

---

## 7. Known issues and notes

- **Groq + native PDF parts** → 400. Worked around in config (§5). Any future `custom` endpoint
  that is not document-capable needs the same `defaultLLMDeliveryPath` override.
- **RAG/file search** works in dev with NVIDIA embeddings (synthetic data only). Production needs an
  MTN-approved embeddings provider; changing provider means re-embedding (different dimensions).
- **Schedules engine — resolved for local dev.** Upstream refuses to arm the scheduler without
  Redis streams or `SCHEDULES_SINGLE_PROCESS=true`. Local `.env` now sets
  `SCHEDULES_SINGLE_PROCESS=true` and the engine starts. Production (multi-replica) needs Redis
  streams instead (Phase 3).
- **Meilisearch index check timed out at boot** (API started before Meili was ready). Harmless with
  `SEARCH=false`; recheck when search is enabled.
- **First registered user becomes `ADMIN`** (upstream behavior). In production, create the first
  admin deliberately (`npm run create-user`) before enabling SSO.
- **Docker Desktop disk** was full (58 GB VM disk) and blocked the image pull; the user removed old
  images. Now **11.7 GB free** (79% used). Monitor this before adding the Code Interpreter image (Phase 4).
- **Image tags:** the LibreChat base is now digest-pinned; `rag_api`, `vectordb`, `admin-panel`,
  Mongo and Meilisearch still use upstream compose tags. Pin them before any shared environment.
- **Grafana on host port 3000** — admin panel moved to 3001 via `ADMIN_PANEL_PORT`.
- **Push blocked on credentials:** `git push` over HTTPS fails with no GitHub credentials on this
  machine. The user must push (or set up `gh auth login`). The repo is confirmed **private**.
- **Upstream layout issue, fixed in the branding layer:** on auth pages below 768px, upstream pins
  the theme toggles (`absolute bottom-0`) over the policy footer, so they overlapped "Privacy policy".
  Fixed by CSS only: `mtn/branding/css/mtn-overrides.css` lifts the footer 3rem, scoped with
  `:has()` to the auth layout root. Measured 0px overlap at 390/320px in both modes, and desktop
  is unchanged. Worth reporting upstream; the rule becomes a no-op if upstream changes the markup.
- **Light-mode selection fills are fill-only below 3:1** (nav 1.19:1, tab 1.27:1). That matches
  LibreChat's own default (1.20:1). Conversation rows also get a 2px `text-primary` left bar,
  but nav buttons, settings tabs and prompt items rely on the fill alone. Follow-up: a design
  decision (a 3:1 light fill needs a dark-gold tone).
- **KNOWN ISSUE — local install gaps in `packages/api` tests (Phase 4, 2026-11-08).** After
  `npm ci` on this Mac, two packages do not resolve from `packages/api`:
  - `winston-daily-rotate-file` (a `@librechat/data-schemas` peer) is installed only under
    `api/node_modules`, so `packages/api` Jest suites that load the logger fail to start.
    **Workaround:** run them with `NODE_PATH=../../api/node_modules`, e.g.
    `cd packages/api && NODE_PATH=../../api/node_modules npx jest <paths>`.
  - `@opentelemetry/sdk-node` exists only nested under `@librechat/agents`, at a different
    version, so `tsc --noEmit` reports TS2307 in `src/telemetry/*`. Pre-existing and unrelated to
    MTN changes; the rest of `packages/api` typechecks clean.
  - **Before any release, confirm the full `packages/api` suite on Linux CI** (clean `npm ci`).
    Locally, the full run is also not a reliable signal: on this 4-core Mac about 600 hook
    timeouts come from `mongodb-memory-server` under parallel load, and 7 suites (plus a flaky
    ACL locking test) fail on the untouched baseline too.
- **Core change is deployed locally as an overlay, not a full image build (Phase 4).** The api
  container runs `mtn-librechat-core:local` = branding image + the backend build of the MTN core
  deviation (`mtn/deploy/core.Dockerfile`), because a full LibreChat build (Vite frontend) needs
  more memory than the 3 GB Docker VM has. Valid only while the upstream base image matches our
  base commit. Production builds the whole image from source in CI.
- **LibreChat bans non-browser API clients.** Calling `/api/*` from a script without a browser
  User-Agent scores a `non_browser` violation and bans the user **and the source IP** (the Docker
  gateway, so every local browser session) for 120 minutes. This happened once during Phase 4
  testing; the four ban entries were removed from the `logs` collection. Run API-level checks
  from the browser session instead.

- **Groq free-tier rate limit:** with Groq, the closing reply after a tool call was refused for the
  per-minute token limit in 3 of 4 browser runs (files were delivered). Nemotron on NVIDIA is now the
  default; Groq is the fallback spec.
- **LibreChat's own schema check** rejects malformed tool arguments (e.g. a JSON array sent as a
  string) with a generic "input failed schema validation" before office-mcp sees them; models
  recovered on the next call in every test. office-mcp's more specific errors apply after that check.
- **Agents REST API rejects scripted clients** (`uaParser`), so the MTN Document Assistant is a
  `modelSpecs` entry, not a seeded database agent (CLAUDE.md decisions log).

### Decisions waiting on MTN

- Phase 1 content: welcome copy, footer, help/privacy/terms URLs and terms text; the exact dark-mode
  palette; a **vector (SVG) logo**; confirmation that the **Newlyn Works font licence** covers web embedding.
- IdP: OIDC discovery URL + client, SAML metadata/certificate (Phase 2).
- Primary model provider **and embeddings provider** (curate `modelSpecs`).
- Storage / data-residency target (`s3` vs `azure_blob`, managed Mongo/Meili/pgvector).
- Approved Office templates (Word/PowerPoint/Excel) and their versioning owner (Phase 4 ships v0.1
  generated templates); whether Nemotron via NVIDIA NIM is acceptable for self-hosting (licence).

### Recommended next steps

1. **Finish Phase 4:** second-user API isolation check (§11), then review and push `mtn/phase4-office`.
2. **Phase 2 — Identity** (next in execution order 1 → 4 → **2** → 3 → 5 → 6): OIDC + SAML against
   MTN's IdP; prod switch to `ALLOW_REGISTRATION=false`.
3. Phase 4 follow-ups (§11): numbered lists on slides; confirm the full `packages/api` suite on Linux
   CI; build the api image from source in CI instead of the overlay; propose the core change upstream.
4. Chase MTN for Phase 1 content, approved Office templates, and an MTN-approved model/embeddings
   provider (Nemotron via NIM is a Phase 3 self-hosting candidate).
5. Run Lighthouse once a local build exists.

---

## 8. Git state (2026-11-08)

### Local branches

| Branch | Tip | Tracks | Status |
|---|---|---|---|
| `main` | `f4154b649` 🦿 chore: Bump Agents SDK to 4.2.1 (#17664) | `upstream/main` | Identical to upstream |
| `mtn/employee-ai` | `d27c5098a` fix(mtn): dark-mode accents use MTN yellow | `origin/mtn/employee-ai` | **Pushed** by the user |
| `mtn/phase4-office` (current) | see below | `origin/mtn/phase4-office` (at `587113cab`) | Later commits **not pushed** (the user pushes) |

### `mtn/phase4-office` commits on top of `d27c5098a`

| Commit | Message | Pushed |
|---|---|---|
| *(this commit)* | docs(mtn): phase 4 speed pass results in the handover report | no |
| `f5aa134ac` | docs(mtn): phase 4 stakeholder demo script and synthetic demo PDF | no |
| `473da6e6d` | chore(mtn): drop Muse Glimmer from the picker; shorter closing replies | no |
| `b2a9d4c48` | perf(mtn): office-mcp speed pass — lenient repairs, worked examples, faster checks | no |
| `42c972b26` | docs(mtn): phase 4 handover, feature register and acceptance results | no |
| `471d6e8dd` | fix(mtn): give the Document Assistant today's date | no |
| `cfa671e22` | feat(mtn): MTN Document Assistant as model specs (Nemotron Ultra default, Groq fallback) | no |
| `0175277b0` | fix(mtn): office-mcp guidance that models can act on (probe findings) | no |
| `740cb5fdb` | feat(mtn): NVIDIA endpoint (Nemotron Ultra, Muse Glimmer) and NVIDIA embeddings for RAG | no |
| `a03a00b81` | fix(mtn): revisions address slides by the number the user sees | no |
| `da8dfd675` | feat(mtn): revise_office_file (v2 keeps v1) and get_generation_status | no |
| `859a7cc74` | feat(mtn): create_excel_workbook with recalculation and error-value checks | no |
| `7faf4f07a` | feat(mtn): create_powerpoint_presentation with fit and bounds checks | no |
| `4f751f9d7` | build(mtn): pin upstream base by digest and guard the core overlay | no |
| `937d11471` | feat(mtn): create_word_document with validation, preview and page targets | no |
| `59b989ecd` | fix(mcp): attach subagent MCP file outputs to the parent response | no |
| `753e6f709` | feat(mtn): office templates v0.1 and build script | no |
| `560584cac` | feat(mtn): office-mcp service skeleton — pinned image, internal network, bearer auth | no |
| `587113cab` | feat(mcp): opt-in file outputs for librechat.yaml MCP servers | **yes** |
| `1adcf7728` | docs(mtn): phase 4 decisions — MCP file outputs, Code Interpreter to phase 3 | **yes** |

- Never committed (gitignored): `.env`, root `librechat.yaml` (symlink), `docker-compose.override.yml`,
  `mtn/branding/private/` (licensed fonts, official logo). An untracked `payload.json` (the user's
  own NVIDIA test request) is still in the repo root; it is not committed.

---

## 9. Phase 1 — Configuration & branding (done; MTN content pending)

Started 2026-11-08 with placeholders. The **official MTN logo and MTN Brighter Sans fonts** were
supplied the same day and are now live. **No LibreChat source changed.** Everything is config, env,
and a thin branding image layered on the unchanged upstream image.

### Brand inventory

| Item | Where | Current value | Status / next |
|---|---|---|---|
| App title | `.env` `APP_TITLE` | `MTN Employee AI` (likely final) | Confirm with MTN comms |
| Footer | `.env` `CUSTOM_FOOTER` | "MTN Employee AI — internal use only. AI can make mistakes… (PLACEHOLDER footer)" | Approved footer copy |
| Help & FAQ | `.env` `HELP_AND_FAQ_URL` | `https://example.com/mtn-employee-ai/help-placeholder` | MTN intranet help page |
| Welcome | `interface.customWelcome` | "Welcome to MTN Employee AI, {{user.name}}. How can I help today?" | Approved copy |
| Privacy policy | `interface.privacyPolicy.externalUrl` | `https://example.com/…/privacy-placeholder` | MTN privacy notice URL |
| Terms of use | `interface.termsOfService` | `example.com` URL + **modal acceptance** with placeholder text | MTN Legal text/URL |
| Theme | `interface.theme` (inline, `MTN (placeholder)`) | MTN yellow `#FFCB05` + black, partial token set | Exact palette from MTN brand |
| Font | `appearance.fontFamily` + `mtn/branding/fonts/mtn-fonts.css` + `private/fonts/*.otf` | **Official MTN Brighter Sans** (12 faces, 250–800 + italics), served from the branding image | ✅ Live. **Open:** MTN to confirm the Newlyn Works licence covers web embedding |
| Logo | `private/generated/logo.svg` (from `private/logo/yello_logo.jpg`) | **Official MTN oval on yellow**, 256px raster inside an SVG | ✅ Live. Ask MTN brand for a vector SVG (only raster JPEGs were supplied; `white_logo.png` is actually a JPEG on white, not transparent) |
| Favicons / app icons | `private/generated/*.png` (16, 32, 180, 192, 512 maskable) | Derived from the official yellow logo | ✅ Live. Tracked `mtn/branding/assets/` placeholders are the fallback for fresh clones |
| PWA manifest | `mtn/branding/manifest.webmanifest` | name "MTN Employee AI", theme colour `#FFCB05` | Confirm |

### How it is wired

- `mtn/config/librechat.yaml` (tracked) is the config source of truth. The root `librechat.yaml`
  is a gitignored symlink to it.
- The upstream `.gitignore:79` rule `librechat.yaml` matches at any depth, so the first commit of
  `mtn/config/librechat.yaml` needs `git add -f` (as with `CLAUDE.md`). After that, changes are
  tracked normally.
- **Branding image** `mtn-librechat:local` = `mtn/branding/Dockerfile` built FROM the unchanged
  upstream `librechat-dev:latest`. It copies the logo, icons and manifest into `/app/client/dist`,
  adds the `.otf` files and `mtn-fonts.css` under `assets/fonts/`, links the CSS from
  `index.html`, sets `<title>`, and drops the stale `index.html.br/.gz`. It uses a BuildKit bind
  mount, so private files exist only in their final location. Without `private/` it falls back to
  the placeholders and no font.
- **Licensed files are never in git:** `mtn/branding/private/` is gitignored (new `.gitignore`
  entry). It holds the fonts and logos the user supplied (moved there from `docs/logo_and_fonts/`)
  and `generated/` icons. Hand them over through a secure channel. **Do not push
  `mtn-librechat:local` to any public registry**, because it contains the fonts and logo.
- **Rebuild after every upstream image update:** `docker compose pull && docker compose build api && docker compose up -d`.
- Local `docker-compose.override.yml` (gitignored, recreate on other machines):

```yaml
services:
  api:
    image: mtn-librechat:local
    build:
      context: ./mtn/branding
      args:
        BASE_IMAGE: registry.librechat.ai/librechat-ai/librechat-dev:latest
    pull_policy: never
    volumes:
      - type: bind
        source: ./mtn/config/librechat.yaml
        target: /app/librechat.yaml
        read_only: true
```

### Verification (2026-11-08, browser + HTTP)

| Check | Result |
|---|---|
| Server accepts config + inline theme | ✅ No validation errors; `/api/config` returns `appTitle: "MTN Employee AI"` and theme `MTN (placeholder)` with light+dark modes |
| Served assets | ✅ `assets/logo.svg` byte-identical to `private/generated/logo.svg`; fonts CSS and `.otf` files return 200 (`font/otf`) |
| Tab title | ✅ "MTN Employee AI", now also in the static `index.html` `<title>` (set by the branding image) |
| Terms modal | ✅ Shown on first visit with placeholder title/content; accepted by the test user |
| Welcome | ✅ "Welcome to MTN Employee AI, Phase0 Tester. How can I help today?" |
| Footer + Privacy/Terms links | ✅ Placeholder footer with both links |
| Help & FAQ | ✅ Opens `https://example.com/mtn-employee-ai/help-placeholder` |
| Light theme | ✅ Black send button, yellow-tint user bubble, yellow selected nav item |
| Dark theme | ✅ Yellow focus ring. Test user's theme setting set back to System afterwards |
| Login logo | ✅ Official MTN oval on yellow (after a hard reload; static assets are cached for 2 days, plus a service worker) |
| Brand font | ✅ Computed body/heading font is `"MTN Brighter Sans", Inter, …`; `document.fonts` shows faces 300, 400 and 500–600 loaded on the login page |
| Lighthouse | **Not run.** `npm run lighthouse` needs `npm ci` and a local build, which haven't been done on this machine yet |

### Phase 1 known gaps

- **Font licence** for web embedding is unconfirmed (Newlyn Works). **No vector logo**, only raster JPEGs.
- **User avatar initials** keep LibreChat's generated colours. `rgb-avatar-fill` does not affect
  them.
- **`modelSpecs` curation** is still deferred until the primary provider is chosen.

---

## 10. Phase 1 accessibility and mobile checks (2026-11-08, updated for dark-mode accents)

### Dark-mode accents — theme tokens only

LibreChat green is gone from dark mode. MTN yellow `#FFCB05` is used as a **fill with a black
label** or as **link text on dark surfaces**:

| Token(s) | Was (LibreChat) | Now (MTN) | Where it shows |
|---|---|---|---|
| `accent-primary` / `-hover` | #41A79D / #6DC8B9 | **#FFCB05** / #FFDD5C | Auth links (Sign up, Privacy, Terms), auth field focus border |
| `surface-submit` / `-hover` | #047857 / #065F46 | **#FFCB05** / #FFDD5C | Continue, Save, Submit buttons |
| `text-on-status` | #FFFFFF | **#000000** | Label on every solid status fill |
| `surface-destructive` / `-hover`, `status-error-strong` | #991B1B / #7F1D1D | #F87171 / #FCA5A5 | Delete buttons and error badges (bright end, so the black label passes AA) |
| `status-success/warning/info-strong` | #088759 / #92400E / #424242 | #34D399 / #FBBF24 / #BDBDBD | Status badges (same reason) |
| `surface-nav-selected`, `surface-tab-selected` | #2F2F2F | **#786414** (yellow-tinted) | Selected sidebar row, account button, settings tab |

Semantic greens (success text, spreadsheet icon, syntax, chart series) and provider brand icons are
unchanged on purpose.

### WCAG contrast — effective theme

`node mtn/scripts/theme-contrast.js .` checks **102 pairs**. The full table is in
**[`theme-contrast.md`](theme-contrast.md)** (generated, do not hand-edit).
- **Thresholds:** text needs 4.5:1 (AA); UI indicators need 3:1.
- **Pairs follow real component usage.** Send button = `surface-inverted`/`text-inverted`. Save/Submit
  = `surface-submit` + `text-on-status`. Selected rows = `text-primary` text and `text-secondary`
  icons only, checked by reading `Convo`, `ChatGroupItem`, `Button` nav and the settings tabs, and
  measured in the browser.

**Result: 100 / 102 pass. Dark mode 51/51.** The two failures are both light mode and pre-existing
in kind:

| Mode | Pair | Ratio | Needs | Note |
|---|---|---|---|---|
| light | `surface-nav-selected` (#FFE380) vs `surface-sidebar` | 1.19:1 | 3:1 (UI) | LibreChat default is 1.20:1. Conversation rows also have a 2px `text-primary` bar |
| light | `surface-tab-selected` (#FFE380) vs `surface-primary` | 1.27:1 | 3:1 (UI) | LibreChat default is 1.18:1 |

Key dark-mode rows (from the generated table):

| Pair | Colours | Ratio |
|---|---|---|
| `text-on-status` on `surface-submit` | #000000 / #FFCB05 | 13.80:1 ✅ |
| `text-on-status` on `surface-destructive` | #000000 / #F87171 | 7.59:1 ✅ |
| `text-on-status` on `status-*-strong` (4 fills) | black on #34D399 / #F87171 / #FBBF24 / #BDBDBD | 7.59–12.58:1 ✅ |
| `accent-primary` on `surface-primary` / `surface-dialog` / `surface-chat` | #FFCB05 on #0D0D0D / #121212 / #2F2F2F | 12.77 / 12.31 / 8.80:1 ✅ |
| `text-primary` on `surface-nav-selected` | #ECECEC / #786414 | 4.89:1 ✅ |
| `text-secondary` icons on `surface-nav-selected` | #CDCDCD / #786414 | 3.64:1 ✅ (UI) |
| `surface-nav-selected` vs `surface-sidebar` | #786414 / #171717 | 3.10:1 ✅ (UI) |
| file-badge icons (`text-on-status` on `series-1` / `series-4`) | black on #098CEE / #C8850C | 6.00 / 6.82:1 ✅ (UI) |

**Measured in the browser, dark mode at 390px** (computed colours): Continue #000000 on #FFCB05
13.80:1; Sign up, Privacy policy and Terms of service #FFCB05 on #0D0D0D 12.77:1; "Welcome back"
16.45:1. The selected conversation row has fill #786414 (3.10:1 against the sidebar), title #ECECEC
at 4.89:1, a "…" icon at 3.64:1, and a 2px `::before` bar in `text-primary` (15.18:1 against the
sidebar). A scan of every visible element on the chat page found **no** remaining LibreChat accent
green (#047857, #41A79D, #065F46, #6DC8B9).

### Mobile width (390px)

The app was loaded in a same-origin iframe, because the Chrome window could not be resized. The app's
viewport was confirmed at 390px, and overflow was checked with `scrollWidth > innerWidth`.

| Screen | Light | Dark |
|---|---|---|
| Login | ✅ Black Continue; no overflow; footer clear of the toggles (0px overlap) | ✅ Yellow Continue with black label, yellow links; no overflow; 0px overlap |
| Chat | ✅ Yellow-tint user bubble; composer pinned; no overflow | ✅ No LibreChat green; no overflow |
| Sidebar | ✅ Yellow selected row + left bar; no overflow | ✅ Yellow-tinted selected row (#786414) + left bar; no overflow |

Overlap fix verified: footer links end at y=652px, and the toggles start at y=676px, at both 390px
and 320px in both modes. At 1000px the rule doesn't apply (upstream 16px margin; no overlap).

Screenshots were saved locally by the browser tool (not committed).

---

## 11. Phase 4 — Office document generation (built; second-user check pending)

Branch `mtn/phase4-office`. Employees ask the **MTN Document Assistant** for a Word document,
PowerPoint deck or Excel workbook; the model fills a validated JSON spec, **office-mcp** builds the
file from a versioned MTN template, checks it, and the file arrives as a normal chat attachment.
No model-written code runs anywhere.

### How it fits together

| Piece | Where | What it does |
|---|---|---|
| MCP file outputs (**core change**, approved) | `packages/api/src/mcp/fileOutputs.ts`, `packages/api/src/files/mcpOutputs.ts`, ~75 lines in `/api` callbacks; schema field in `packages/data-provider` | Turns `.docx/.pptx/.xlsx` embedded resources from **librechat.yaml-declared** MCP servers (opt-in `fileOutputs`) into user-owned files via the normal file pipeline; strips the bytes before anything is stored or sent to the model. User-added, Config-tier and plugin servers can never return files. Subagent tool calls attach to the parent response. Proposal: `docs/mtn/upstream-proposal-mcp-file-outputs.md`. |
| office-mcp | `mtn/services/office-mcp/` | Python MCP server (streamable HTTP, stateless). Tools: `create_word_document`, `create_powerpoint_presentation`, `create_excel_workbook`, `revise_office_file`, `get_generation_status`. Loose advertised schemas, strict server-side validation with numbered, fixable errors. |
| Templates v0.1 | `mtn/templates/<kind>/<name>/v0.1/` + `build_templates.py` | Word: proposal, meeting minutes, incident report. PowerPoint: executive update, project status (16:9). Excel: action tracker, project plan. MTN Brighter Sans named with Arial fallback (not embedded); SHA-256 pinned per manifest. |
| Checks before delivery | office-mcp | OOXML signature/ZIP/content types; reopen (python-docx / python-pptx / openpyxl); LibreOffice render (60 s, one at a time) and page/slide count; **page targets** (measured overflow); **PowerPoint fit + bounds** (safe margin, text overflow measured with render metrics, overlaps); **Excel recalculation** in LibreOffice (error values block delivery; formulas allowlisted). |
| Versions and owners | office-mcp SQLite (dev) | Every record is scoped to `X-MTN-User-Id`; another user's id behaves exactly like a missing one (404 / "not found"). Revisions add v2, v3… and never touch earlier files. |
| Logo | gitignored `mtn/branding/private/logo` (read-only mount) | Added at generation time; logo-free output when absent. |
| Assistant | `modelSpecs` in `librechat.yaml` | Default: NVIDIA Nemotron 3 Ultra; fallback: Groq `gpt-oss-120b`. Instructions also in `mtn/agents/document-assistant/instructions.md` (kept identical). |

**Trust model:** LibreChat reaches office-mcp only on the internal `office` network with an admin
bearer token (`apiKey`, constant-time compare); the user identity is the server-resolved
`{{LIBRECHAT_USER_ID}}` header. office-mcp has no internet and no published ports.

### Tests

| Suite | Result |
|---|---|
| office-mcp (`docker build --target test`) | **103 passed**: auth 8, store 4, templates 15, Word 21, PowerPoint 16, Excel 15, revisions 10, lenient repairs 10, description examples 4 |
| `packages/api` MCP/file suites (core change) | 290 passed (fileOutputs 16, MCPManager 265 incl. 4 new, persistence 6 with mongodb-memory-server, subagent 3) |
| `/api` callbacks | 54 passed (3 new) |
| `packages/data-provider` MCP/config | 463 passed; `tsc` clean in changed workspaces (telemetry TS2307 is pre-existing, §7) |
| Overlay guard | pinned base passes; a changed source line and a changed version both fail the build |

### Model choice — tool-call probe (2026-11-08)

12 prompts (3 Word, 3 PowerPoint incl. a PDF summary, 3 Excel, a vague request, a non-file
question, a terse incident request) plus a multi-turn revision, sent with the real tool schemas
and instructions; every call executed by a real office-mcp, errors fed back (up to 3 calls).

| | Nemotron 3 Ultra run 2 | Nemotron 3 Ultra run 3 (+10 min, after fixes) | Muse Glimmer run 2 | Muse Glimmer run 3 |
|---|---|---|---|---|
| Tasks delivered on first call | 6/11 | 7/11 | 8/11 | 8/11 |
| Tasks delivered within 3 calls | 9/11 | **11/11** | 10/11 | 10/11 |
| Over-asking (question on a clear request) | 0 | 0 | 0 | 0 |
| Vague request → one question; "2+2" → no tool | ✅ ✅ | ✅ ✅ | ✅ ✅ | ✅ ✅ |
| Latency per model call (median / p90 / max) | 10.7 / 19.3 / 25.9 s | 14.0 / 27.1 / 36.1 s | 42.7 / 117 / 209 s | 39.9 / 89 / 119 s |
| HTTP / rate limiting | 200 only; no 429; no rate-limit headers | same | same | same |

Provider-side schema rejections: none (NVIDIA accepted every tool call). Muse run 3 overlapped
with the browser acceptance runs on the same account. Probe findings fixed in office-mcp
(`0175277b0`): measured page overflow instead of a words-per-page hint, decoding of stringified
JSON fields with a precise error when the string is broken, a one-number slide map, and a clearer
table-plus-chart message.

### Acceptance (browser, MTN Document Assistant on Nemotron 3 Ultra)

Turn time = from sending the message to the saved reply. **Correction:** the first version of this
table measured from the user message's `createdAt`, which LibreChat writes only after the first
model call returns, so it understated turn times. New-conversation turns are now measured from the
conversation's creation, and the revision turn from a browser timestamp taken at send.

| # | Test | Result | Before speed pass (turn / model calls) | After speed pass (turn / model calls) | office-mcp time before → after |
|---|---|---|---|---|---|
| 1 | "Create a two-page Word document explaining an IT incident process." | ✅ 2 pages, target met | 56.2 s / 2 | 35.8 s / 1 and 34.3 s / 1; final run 68.8 s / 1 (model wrote 12 sections, ~620 words; fitted by compact layout level 2, 12.0 s) | 3.7 s → 3.4 s (12.0 s with compact level 2) |
| 2 | "Create a five-slide presentation summarising the attached PDF" (synthetic PDF) | ✅ 5 slides, bounds 0 issues, figures only from the PDF | 56.5 s / 3 | **22.3 s / 1**; 38.3 s / 1 (slide `numbered` list converted, no retry) | 3.0 s → 2.0–5.1 s |
| 3 | Excel tracker with formulas, filters, highlighting and a chart | ✅ formulas checked, 0 errors; filters, dropdowns, conditional formats, summary + chart | 31.1 s / 1 | 32.2 s / 1 before the Excel fast path; **20.4 s / 1** after | 5.2 s → 9.0 s → **1.7 s** |
| 4 | "Shorten slide 2 and add a risks table to slide 5" | ✅ v2: slide 2 shortened, table on slide 5, slides 3–4 unchanged; **v1 byte-identical** | ≥26.3 s / 1 (old method, understated) | **15.6 s / 1** | 2.7 s → 5.2 s |
| 5 | Second user cannot list / preview / download the owner's file (LibreChat API) | ⏳ **not verified by Claude.** The user reported item 4 done on 2026-11-08, but the test tab was still signed in as the owner and the second account has no session after 06:43 UTC, so no status codes were observed or recorded here. office-mcp level is ✅ (another user's id → 404). | — | — | — |
| 6 | Files open cleanly; previews inspected | ✅ all stored files reopen and render (2 pages / 5 / 1 / 5); recalculated tracker has no error cells | — | — | — |

**Against the < 25 s target:** the revision (15.6 s), Excel (20.4 s) and one PDF-deck run (22.3 s)
are under it; Word documents are not (34–69 s). The dominant cost is NVIDIA's hosted throughput,
measured at **20–32 tokens/s** during the final runs and dropping within a minute. A Word document
is ~1,000 content tokens plus reasoning, so the model alone needs 30–60 s at that rate. Retries are
now rare (one model call in every final scenario); office-mcp's share is 2–5 s (12 s when it has to
tighten a Word layout twice). Turning Nemotron's thinking off was tested and rejected: faster per
call but first-call success fell from 10/11 to 8/11.

### Speed pass (2026-11-08)

| Probe (Nemotron Ultra, 12 prompts + revision, real office-mcp) | First call | Within 3 calls | Median / p90 per model call |
|---|---|---|---|
| Before (run 3) | 7/11 | 11/11 | 14.0 / 27.1 s |
| After: lenient repairs + worked examples | 10/11 | 10/11 | 11.4 / 17.5 s |
| After, thinking off (rejected) | 8/11 | 10/11 | 9.2 / 19.4 s |
| After, final (+ compact Word layouts) | **10/11** | **11/11** | 15.4 / 24.2 s |

Changes (`b2a9d4c48`, `473da6e6d`): lenient repairs recorded in `checks["coercions"]` (slide
numbered lists → numbered bullets; display text up to 1.5× its limit trimmed at a word boundary;
harmless unknown fields ignored; chart series beyond 4 dropped from the chart; numbers in table
cells → text); compact Word layouts before a page-target error; a worked example per tool
description (tested against strict validation); one LibreOffice run for Excel; two-line slide
titles; shorter closing replies; Muse Glimmer removed from the picker.

### Follow-ups

- Word length overshoot: Nemotron sometimes writes far more than the requested pages (12 sections
  for 2 pages). Compact layouts absorb it, but the extra tokens cost 20–30 s. Options: a stricter
  word budget in the instructions, or a smaller/faster model for Word drafting.
- Turn time depends on the hosted model's throughput (20–32 tok/s on NVIDIA's free endpoint).
  A self-hosted NIM or an MTN-approved provider with higher throughput is the real lever (Phase 3).
- Second-user API isolation check (acceptance 5) still to be observed and recorded.
- Production: build the api image from source in CI (no overlay); move office-mcp records from
  SQLite to managed Postgres/Mongo (Phase 3); align `OFFICE_MCP_RETENTION_DAYS` with LibreChat retention.
- Editing **employee-uploaded** Office files (only files the same user generated can be revised now).
- Propose the MCP file-outputs change upstream; until then it is the only core deviation.
- Preview image in chat stays off (`OFFICE_MCP_PREVIEW_IMAGE=false`): MCP images are sent to the
  model, which text-only models reject.
