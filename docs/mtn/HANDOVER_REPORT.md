# MTN Employee AI Assistant — Handover Report

**Last updated:** 2026-11-08 (Phase 0 accepted; **Phase 1 done**, with MTN copy, URLs and policy text still placeholders. Phase 4 is next)
**Prepared for:** external reviewer / incoming contributor
**Scope:** an **unchanged** upstream LibreChat running locally via Docker, with MTN configuration and
a thin branding image layered on top. **No LibreChat source code has been modified.**

---

## 1. Repository state

| Field | Value |
|---|---|
| Branch | `mtn/employee-ai` |
| Upstream base | `f4154b649` — "🦿 chore: Bump Agents SDK to 4.2.1 (#17664)" (2026-10-31) |
| `package.json` version | `v0.8.9-rc1` (`git describe`: `v0.8.9-rc1-84-gf4154b649`) |
| Remotes | `origin` → `https://github.com/manijami/mtnchatbot.git`; `upstream` → `https://github.com/LibreChat-AI/LibreChat.git` (no credentials in URLs) |
| MTN commits | 6 commits on top of upstream (4 docs, 1 Phase 1 branding, 1 dark-mode fix). Full list in §8. **None pushed.** |
| Source diff vs upstream | **None** in LibreChat code. MTN files only: `CLAUDE.md`, `docs/mtn/`, `mtn/` (config, branding image, theme check script), plus 3 lines in `.gitignore`. |
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
| Deployment theming | v0.8.9-rc1 | `interface.theme` + branding image | Dev: inline **MTN** theme, official logo, **MTN Brighter Sans** | Apply inline theme, check light and dark, fonts, contrast, mobile | **Tested OK** (Phase 1): theme accepted by the server validator. Light mode: black primary buttons, yellow-tint user bubble and selected nav. Dark mode: MTN yellow for focus, links, primary buttons (black label) and a yellow-tinted selected row. Brand font **loaded** (computed `"MTN Brighter Sans"`; faces 300/400/500–600 loaded). Contrast: 100/102 pairs pass; **dark mode 51/51**. The 2 failures are light-mode selection fills at the upstream level (§10). Login, chat and sidebar checked at 390px in both modes (§10). |
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
| `SCHEDULES_SINGLE_PROCESS` | `true` (added after Phase 0 acceptance, local dev only). Asserts a single API replica so the schedules engine arms without Redis. API log now shows `[schedules] engine started`. Do **not** carry this to multi-replica deployments; use Redis streams there. |

Everything else is the upstream `.env.example` default (e.g. `PORT=3080`, `SEARCH=false`, provider
keys `user_provided`).

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
| `LibreChat` (api) | **`mtn-librechat:local`** (`sha256:422615021d62…`), built by `mtn/branding/Dockerfile` FROM `librechat-dev:latest` | Up; `/health` → `OK`; `[schedules] engine started` | `3080` |
| `admin-panel` | `librechat-admin-panel:latest` | Up **(healthy)** | `3001→3000` |
| `chat-mongodb` | `mongo:8.0.20` | Up | internal |
| `chat-meilisearch` | `getmeili/meilisearch:v1.35.1` | Up | internal |
| `vectordb` | `pgvector/pgvector:0.8.0-pg15-trixie` | Up | internal |
| `rag_api` | `librechat-rag-api-dev-lite:latest` | Up; "Application startup complete" | internal |

Only `admin-panel` defines a Docker healthcheck; the others were verified by state + logs + HTTP.

- Start/stop: `docker compose up -d` / `docker compose down` (data persists in named volumes).
- After upstream image updates: `docker compose pull && docker compose build api && docker compose up -d`.
  `pull_policy: never` on `api` stops compose trying to pull the local-only branding image.
- The branding image contains licensed fonts and the official logo. **Never push it to a public registry.**

---

## 7. Known issues and notes

- **Groq + native PDF parts** → 400. Worked around in config (§5). Any future `custom` endpoint
  that is not document-capable needs the same `defaultLLMDeliveryPath` override.
- **RAG/file search not validated** — needs an embeddings provider (OpenAI key or MTN-approved
  alternative). Decide alongside the primary-provider choice.
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
- **Image tags are `:latest`/`-dev`** (upstream compose default). Pin digests before any shared or
  production environment.
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

### Decisions waiting on MTN

- Phase 1 content: welcome copy, footer, help/privacy/terms URLs and terms text; the exact dark-mode
  palette; a **vector (SVG) logo**; confirmation that the **Newlyn Works font licence** covers web embedding.
- IdP: OIDC discovery URL + client, SAML metadata/certificate (Phase 2).
- Primary model provider **and embeddings provider** (curate `modelSpecs`).
- Storage / data-residency target (`s3` vs `azure_blob`, managed Mongo/Meili/pgvector).
- Approved Office templates (Word/PowerPoint/Excel) and their versioning owner (Phase 4).

### Recommended next steps

1. **Start Phase 4 — Office document generation** (next in execution order 1 → 4 → 2 → 3 → 5 → 6).
   Step 1: self-hosted Code Interpreter (`librechat-code` service, `LIBRECHAT_CODE_BASEURL` /
   `LIBRECHAT_CODE_API_KEY`, `execute_code`) with `python-docx`, `python-pptx`, `openpyxl`,
   `pandas`, `matplotlib` in the image. Check Docker VM disk (11.7 GB free) first.
2. Push `mtn/employee-ai` to `origin` (needs the user's GitHub credentials).
3. In parallel, chase MTN for Phase 1 content (copy, URLs, terms, SVG logo, font licence) and the
   Phase 2 IdP details (OIDC/SAML); plan the prod switch to `ALLOW_REGISTRATION=false`.
4. Choose an embeddings provider so RAG/file search can be validated.
5. Run Lighthouse once `npm ci` and a local build exist.

---

## 8. Git state (2026-11-08)

### Local branches

| Branch | Tip | Tracks | Status |
|---|---|---|---|
| `main` | `f4154b649` 🦿 chore: Bump Agents SDK to 4.2.1 (#17664) | `upstream/main` | Identical to upstream; nothing local |
| `mtn/employee-ai` (current) | see below | **none** | **Never pushed.** `origin` has no MTN branch, and there are no `origin/*` refs locally |

### Commits not yet pushed (`git log mtn/employee-ai --not --remotes`)

| Commit | Message |
|---|---|
| *(this commit)* | fix(mtn): dark-mode accents use MTN yellow |
| `d1b3f13c1` | docs(mtn): phase 1 handover refresh |
| `025e5269c` | feat(mtn): Phase 1 branding — MTN logo, fonts, theme |
| `f9c2ebd84` | docs(mtn): set execution order 1-4-2-3-5-6, Groq data rule, local schedules flag |
| `d3d5eae45` | docs(mtn): record Phase 0 commit in handover report |
| `048140573` | docs(mtn): project guide and Phase 0 baseline |

- All on top of upstream `f4154b649`. `main` has no unpushed commits.
- **Not pushed** on purpose: the push attempt failed for lack of GitHub credentials, and this
  refresh was committed with "do not push". To publish: `git push -u origin mtn/employee-ai`
  (private repo `github.com/manijami/mtnchatbot`).
- Never committed (gitignored): `.env`, root `librechat.yaml` (symlink),
  `docker-compose.override.yml`, `mtn/branding/private/` (licensed fonts, official logo).
  `mtn/config/librechat.yaml` is tracked via a one-time `git add -f`.

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
