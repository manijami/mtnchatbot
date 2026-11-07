# MTN Employee AI Assistant — Handover Report

**Last updated:** 2026-11-08 (Phase 0 completed)
**Prepared for:** external reviewer / incoming contributor
**Scope:** state of this checkout after Phase 0 — an **unchanged** upstream LibreChat running
locally via Docker, plus the MTN project guide. **No LibreChat source code has been modified.**

---

## 1. Repository state

| Field | Value |
|---|---|
| Branch | `mtn/employee-ai` |
| Upstream base | `f4154b649` — "🦿 chore: Bump Agents SDK to 4.2.1 (#17664)" (2026-10-31) |
| `package.json` version | `v0.8.9-rc1` (`git describe`: `v0.8.9-rc1-84-gf4154b649`) |
| Remotes | `origin` → `https://github.com/manijami/mtnchatbot.git`; `upstream` → `https://github.com/LibreChat-AI/LibreChat.git` (no credentials in URLs) |
| MTN commits | One docs-only commit on top of upstream: `docs(mtn): project guide and Phase 0 baseline` (adds `CLAUDE.md`, `docs/mtn/`). See §8 for hash. **Not pushed.** |
| Source diff vs upstream | **None** outside `CLAUDE.md` and `docs/mtn/`. |

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
| `librechat.yaml` | `.gitignore:79` | Minimal Phase 0 config. See §5. |
| `docker-compose.override.yml` | `.gitignore:115` | Mounts `./librechat.yaml` into the `api` container (the base compose file does not). Follows `docker-compose.override.yml.example`; no image/service changes. |
| `uploads/`, `logs/`, `images/` | `.gitignore` | Runtime bind mounts created by the stack. |
| `.claude/helpers/*`, `.claude/settings.local.json*` | `/.claude/` | Claude Code hook scripts / local permissions (unchanged in Phase 0). |

---

## 3. Project guide

The authoritative MTN project guide is the committed **`CLAUDE.md`** at the repo root (read
`AGENTS.md` first — upstream contributor rules). It is no longer reproduced here to avoid drift.

Current phase plan (from `CLAUDE.md`):

| Phase | Description | Status |
|---|---|---|
| 0 — Baseline & environment | Clean local run, version/commit/remote confirmed | **Done** (this report) |
| 1 — Configuration & branding | Title, footer, help URL, welcome, privacy/ToS, MTN theme, assets; curate `modelSpecs` later | Not started — waiting on MTN brand assets |
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
| Multi-provider chat (OpenAI, Azure OpenAI, Anthropic, Google, Bedrock, custom) | v0.8.9-rc1 (core) | `librechat.yaml` `endpoints` + provider API keys in `.env` | Dev: Groq `custom` endpoint only. Primary MTN provider still deferred. | Send a message on each configured endpoint, confirm a response | **Tested OK** (Groq custom endpoint): message sent; response **streamed** incrementally (reasoning then answer visible mid-generation); answer complete. Other providers **not tested** — no keys (`user_provided`). |
| Conversation history & auto titles | v0.8.9-rc1 (core) | Mongo; `titleConvo`/`titleModel` | Default-available | Reload a conversation; check sidebar and stored title | **Tested OK**: after page reload the conversation and messages reloaded from the server; sidebar listed it with a generated title ("Container Orchestrator Smoke Test", via `openai/gpt-oss-20b`). Mongo: 4 conversations, 8 messages. |
| Agents (no-code custom assistants) | v0.8.9-rc1 | Mongo; `agents` endpoint enabled | Default-available, not yet reviewed for MTN policy | Create an agent, chat with it, confirm persistence | **Tested OK**: created "Phase0 Test Agent" (provider `groq`, `openai/gpt-oss-120b`) with instructions to prefix replies `AGENT-OK:`; chat reply was `AGENT-OK: 144`; agent persisted in Mongo. |
| Agent Marketplace / sharing | v0.8.9-rc1 | Roles/permissions config | Not reviewed | Share an agent with another user/role | **Not tested** — only one test user; out of Phase 0 scope. |
| Skills (`SKILL.md` bundles) | v0.8.9-rc1 | Agent config | Not reviewed | Attach a skill to an agent, invoke it | **Not tested** — out of Phase 0 scope. |
| Subagents | v0.8.9-rc1 | Agents endpoint | Not reviewed | Delegate a task to a subagent | **Not tested** — out of Phase 0 scope. |
| Agent Management API (beta) | v0.8.9-rc1 (beta) | Deployment-bound OIDC client | Not configured | Call the documented endpoints | **Not tested** — needs OIDC (Phase 2). |
| Attached code workspaces (experimental) | v0.8.9-rc1 (experimental) | `librechat-code` worker | Not configured | Point an agent at a workspace, run a command | **Not tested** — no code worker (Phase 4). |
| Agent Plugins (experimental) | v0.8.9-rc1 (experimental) | Startup-loaded Skill/MCP bundles | Not configured | Bundle a plugin at startup, confirm load | **Not tested** — not configured. |
| Code approval controls | v0.8.9-rc1 | Admin role grants | Not configured | Set a policy, attempt exec, confirm enforcement | **Not tested** — no code worker. |
| MCP (Model Context Protocol) | v0.8.9-rc1 | `mcpServers` config | Not configured | Register an MCP server, invoke a tool | **Not tested** — no `mcpServers` yet (Phase 4/5). |
| Code Interpreter | v0.8.9-rc1 | `librechat-code` + `LIBRECHAT_CODE_BASEURL` / `LIBRECHAT_CODE_API_KEY` | Not configured (planned Phase 4, self-hosted) | Run a snippet, confirm sandboxed output | **Not tested** — not configured. |
| RAG / file search | v0.8.9-rc1 | `rag_api` + pgvector + embeddings provider | Not configured | "Upload for File Search", ask about it | **Not tested** — `rag_api` and `vectordb` are running, but embeddings default to OpenAI and no OpenAI key is set; Groq has no embeddings API. |
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
| Deployment theming | v0.8.9-rc1 | `interface.theme` | Not configured (Phase 1) | Apply inline theme | **Not tested** — no branding yet by design. |
| Manual context compaction | v0.8.9-rc1 | None | Default-available | Trigger summarize-only turn | **Not tested** — out of Phase 0 scope. |

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

Everything else is the upstream `.env.example` default (e.g. `PORT=3080`, `SEARCH=false`, provider
keys `user_provided`).

### `librechat.yaml` (gitignored) — full content, no secrets

```yaml
version: 1.3.18
cache: true
interface:            # upstream default interface settings, no branding
  fileSearch: true
  modelSelect: true
  parameters: true
  presets: true
  bookmarks: true
  multiConvo: true
  agents: true
  fileCitations: true
endpoints:
  custom:
    - name: 'groq'
      apiKey: '${GROQ_API_KEY}'
      baseURL: 'https://api.groq.com/openai/v1/'
      models:
        default: ['openai/gpt-oss-120b', 'openai/gpt-oss-20b']
        fetch: true
      titleConvo: true
      titleModel: 'openai/gpt-oss-20b'
      modelDisplayLabel: 'Groq'
# Groq's chat API rejects native PDF parts (400), so deliver PDFs as extracted text.
fileConfig:
  endpoints:
    groq:
      defaultLLMDeliveryPath:
        overrides:
          'application/pdf': 'text'
```

The Groq models listed in `librechat.example.yaml` (`llama3-*`, `mixtral-*`, `gemma-*`) are retired;
the defaults above are models the key can actually use (verified via Groq `/models`).

---

## 6. Running stack (`docker compose ps`)

| Container | Image | State | Ports |
|---|---|---|---|
| `LibreChat` (api) | `librechat-dev:latest` | Up; `/health` → `OK`, "Server readiness checks passing" | `3080` |
| `admin-panel` | `librechat-admin-panel:latest` | Up **(healthy)** | `3001→3000` |
| `chat-mongodb` | `mongo:8.0.20` | Up | internal |
| `chat-meilisearch` | `getmeili/meilisearch:v1.35.1` | Up | internal |
| `vectordb` | `pgvector/pgvector:0.8.0-pg15-trixie` | Up | internal |
| `rag_api` | `librechat-rag-api-dev-lite:latest` | Up; "Application startup complete" | internal |

Only `admin-panel` defines a Docker healthcheck; the others were verified by state + logs + HTTP.

Start/stop: `docker compose up -d` / `docker compose down` (data persists in named volumes).

---

## 7. Known issues and notes

- **Groq + native PDF parts** → 400. Worked around in config (§5). Any future `custom` endpoint
  that is not document-capable needs the same `defaultLLMDeliveryPath` override.
- **RAG/file search not validated** — needs an embeddings provider (OpenAI key or MTN-approved
  alternative). Decide alongside the primary-provider choice.
- **Schedules engine not armed** (API log, error level): upstream refuses to start the scheduler
  without Redis streams or `SCHEDULES_SINGLE_PROCESS=true`. Scheduled-task writes return 503. Left
  at upstream default; revisit in Phase 3 (Redis) or set the flag for single-replica deployments.
- **Meilisearch index check timed out at boot** (API started before Meili was ready). Harmless with
  `SEARCH=false`; recheck when search is enabled.
- **First registered user becomes `ADMIN`** (upstream behavior). In production, create the first
  admin deliberately (`npm run create-user`) before enabling SSO.
- **Docker Desktop disk** was full (58 GB VM disk) and blocked the image pull; the user removed old
  images. Currently ~9 GB free in the VM — monitor before adding the Code Interpreter image.
- **Image tags are `:latest`/`-dev`** (upstream compose default). Pin digests before any shared or
  production environment.
- **Grafana on host port 3000** — admin panel moved to 3001 via `ADMIN_PANEL_PORT`.

### Decisions waiting on MTN

- Brand palette, logo, favicon, welcome copy, privacy/ToS URLs (Phase 1).
- IdP: OIDC discovery URL + client, SAML metadata/certificate (Phase 2).
- Primary model provider **and embeddings provider** (curate `modelSpecs`).
- Storage / data-residency target (`s3` vs `azure_blob`, managed Mongo/Meili/pgvector).
- Approved Office templates (Word/PowerPoint/Excel) and their versioning owner (Phase 4).

### Recommended next steps

1. Get MTN brand inputs and start Phase 1 (config/theme only).
2. Chase IdP details for Phase 2; plan the prod switch to `ALLOW_REGISTRATION=false`.
3. Choose an embeddings provider so RAG/file search can be validated.
4. Free Docker VM disk (or raise its limit) before building the Phase 4 Code Interpreter image.

---

## 8. Git state

Filled in after the Phase 0 commit — see below.
