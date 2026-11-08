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
| MTN commits | 5 commits on top of upstream (4 docs, 1 Phase 1 branding). Full list in §8. **None pushed.** |
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
| 1 — Configuration & branding | Title, footer, help URL, welcome, privacy/ToS, MTN theme, assets; curate `modelSpecs` later | **Done** (§9). Copy, URLs and policy text are still placeholders waiting on MTN. Theme passes WCAG AA (§10) and works at 390px (§10) |
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
| Deployment theming | v0.8.9-rc1 | `interface.theme` + branding image | Dev: inline **MTN** theme, official logo, **MTN Brighter Sans** | Apply inline theme, check light and dark, fonts, contrast, mobile | **Tested OK** (Phase 1): theme accepted by the server validator. Light mode: black primary buttons, yellow-tint user bubble and selected nav. Dark mode: yellow focus ring. Brand font **loaded** (computed `"MTN Brighter Sans"`; faces 300/400/500–600 loaded). All 74 theme text/background pairs pass WCAG AA (§10). Login, chat and sidebar checked at 390px in both modes (§10). |
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
| `LibreChat` (api) | **`mtn-librechat:local`** (`sha256:83421c0eb74d…`), built by `mtn/branding/Dockerfile` FROM `librechat-dev:latest` | Up; `/health` → `OK`; `[schedules] engine started` | `3080` |
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
- **Mobile (390px), upstream layout:** on the login page the light/dark and contrast toggle icons
  (bottom-left) overlap the "Privacy policy" link in both modes. This is upstream layout, not caused
  by the MTN theme, and cannot be fixed by config (§10).
- **Dark mode keeps LibreChat green** for the login Continue button and the auth/policy links
  (`#047857`, `#41A79D`). It passes AA, but it isn't MTN-branded. Revisit when MTN confirms the dark
  palette (§10).
- **Dark mode selected sidebar row** uses LibreChat's subtle grey, so selection is much weaker than
  the light-mode yellow (non-text indicator; not part of the text-contrast check).

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
| *(this commit)* | docs(mtn): phase 1 handover refresh |
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

## 10. Phase 1 accessibility and mobile checks (2026-11-08)

### WCAG contrast — effective theme (LibreChat defaults + MTN overrides)

Generated by `node mtn/scripts/theme-contrast.js . --md`. It reads LibreChat's default light and dark
palettes (`packages/data-provider/src/themes/{default,dark}.ts`) and applies the overrides in
`mtn/config/librechat.yaml`. **Re-run it after any palette change.**
- **Thresholds:** text needs **4.5:1** (WCAG 1.4.3 AA, normal text). UI indicators marked "(UI)" need
  **3:1** (WCAG 1.4.11).
- **Asterisk:** `*` marks a pair that involves at least one MTN-overridden token.
- **Pairs follow real component usage.** The chat send button is `surface-inverted` +
  `text-inverted` (`composerSubmitClasses`). `surface-submit` + `text-on-status` is used by the
  Save/Submit text buttons, which sit on `surface-primary`/`surface-dialog`.

**Result: 74 / 74 pairs pass AA. No theme fixes were needed.** The first draft of this check paired
`surface-submit` with `surface-composer` (2.44:1). That combination is never rendered, because the
send button uses `surface-inverted`, so the pair was replaced with the real ones (all pass). The
config comment and `CLAUDE.md`, which had attributed the dark-mode yellow decision to the send
button, were corrected.

| Mode | Foreground | Background | Colours | Ratio | Needs | AA |
|---|---|---|---|---|---|---|
| light | `text-primary` | `surface-primary` | #212121 / #FFFFFF | 16.10:1 | 4.5:1 | ✅ Pass |
| light | `text-primary` | `surface-secondary` | #212121 / #F7F7F8 | 15.04:1 | 4.5:1 | ✅ Pass |
| light | `text-primary` | `surface-chat` | #212121 / #FFFFFF | 16.10:1 | 4.5:1 | ✅ Pass |
| light | `text-primary` | `surface-sidebar` | #212121 / #F7F7F8 | 15.04:1 | 4.5:1 | ✅ Pass |
| light | `text-primary` | `surface-composer` | #212121 / #FFFFFF | 16.10:1 | 4.5:1 | ✅ Pass |
| light | `text-primary` | `surface-dialog` | #212121 / #FFFFFF | 16.10:1 | 4.5:1 | ✅ Pass |
| light | `text-primary` * | `surface-user-message` | #212121 / #FFF3C4 | 14.47:1 | 4.5:1 | ✅ Pass |
| light | `text-primary` * | `surface-nav-selected` | #212121 / #FFE380 | 12.69:1 | 4.5:1 | ✅ Pass |
| light | `text-primary` * | `surface-tab-selected` | #212121 / #FFE380 | 12.69:1 | 4.5:1 | ✅ Pass |
| light | `text-secondary` | `surface-primary` | #424242 / #FFFFFF | 10.05:1 | 4.5:1 | ✅ Pass |
| light | `text-secondary` | `surface-chat` | #424242 / #FFFFFF | 10.05:1 | 4.5:1 | ✅ Pass |
| light | `text-secondary` | `surface-sidebar` | #424242 / #F7F7F8 | 9.39:1 | 4.5:1 | ✅ Pass |
| light | `text-secondary` * | `surface-user-message` | #424242 / #FFF3C4 | 9.03:1 | 4.5:1 | ✅ Pass |
| light | `text-secondary` * | `surface-nav-selected` | #424242 / #FFE380 | 7.92:1 | 4.5:1 | ✅ Pass |
| light | `text-tertiary` | `surface-primary` | #595959 / #FFFFFF | 7.00:1 | 4.5:1 | ✅ Pass |
| light | `text-tertiary` | `surface-chat` | #595959 / #FFFFFF | 7.00:1 | 4.5:1 | ✅ Pass |
| light | `text-tertiary` | `surface-sidebar` | #595959 / #F7F7F8 | 6.54:1 | 4.5:1 | ✅ Pass |
| light | `text-tertiary` * | `surface-nav-selected` | #595959 / #FFE380 | 5.52:1 | 4.5:1 | ✅ Pass |
| light | `text-on-status` * | `surface-submit` | #FFFFFF / #000000 | 21.00:1 | 4.5:1 | ✅ Pass |
| light | `text-on-status` * | `surface-submit-hover` | #FFFFFF / #333333 | 12.63:1 | 4.5:1 | ✅ Pass |
| light | `text-on-status` | `surface-destructive` | #FFFFFF / #B91C1C | 6.47:1 | 4.5:1 | ✅ Pass |
| light | `text-inverted` * | `button-primary` | #FFFFFF / #000000 | 21.00:1 | 4.5:1 | ✅ Pass |
| light | `text-inverted` * | `button-primary-hover` | #FFFFFF / #333333 | 12.63:1 | 4.5:1 | ✅ Pass |
| light | `text-inverted` | `surface-inverted` | #FFFFFF / #171717 | 17.93:1 | 4.5:1 | ✅ Pass |
| light | `avatar-text` * | `avatar-fill` | #000000 / #FFCB05 | 13.80:1 | 4.5:1 | ✅ Pass |
| light | `link` | `surface-chat` | #2563EB / #FFFFFF | 5.17:1 | 4.5:1 | ✅ Pass |
| light | `link` | `surface-primary` | #2563EB / #FFFFFF | 5.17:1 | 4.5:1 | ✅ Pass |
| light | `link-hover` | `surface-chat` | #1D4ED8 / #FFFFFF | 6.70:1 | 4.5:1 | ✅ Pass |
| light | `link-prose` | `surface-chat` | #2563EB / #FFFFFF | 5.17:1 | 4.5:1 | ✅ Pass |
| light | `focus-outline` | `surface-chat` | #000000 / #FFFFFF | 21.00:1 | 3:1 (UI) | ✅ Pass |
| light | `focus-outline` | `surface-primary` | #000000 / #FFFFFF | 21.00:1 | 3:1 (UI) | ✅ Pass |
| light | `ring-primary` | `surface-primary` | #595959 / #FFFFFF | 7.00:1 | 3:1 (UI) | ✅ Pass |
| light | `border-field-focus` * | `field-fill` | #000000 / #FFFFFF | 21.00:1 | 3:1 (UI) | ✅ Pass |
| light | `surface-inverted` | `surface-composer` | #171717 / #FFFFFF | 17.93:1 | 3:1 (UI) | ✅ Pass |
| light | `text-inverted` | `surface-inverted` | #FFFFFF / #171717 | 17.93:1 | 3:1 (UI) | ✅ Pass |
| light | `surface-submit` * | `surface-primary` | #000000 / #FFFFFF | 21.00:1 | 3:1 (UI) | ✅ Pass |
| light | `surface-submit` * | `surface-dialog` | #000000 / #FFFFFF | 21.00:1 | 3:1 (UI) | ✅ Pass |
| dark | `text-primary` | `surface-primary` | #ECECEC / #0D0D0D | 16.45:1 | 4.5:1 | ✅ Pass |
| dark | `text-primary` | `surface-secondary` | #ECECEC / #212121 | 13.63:1 | 4.5:1 | ✅ Pass |
| dark | `text-primary` | `surface-chat` | #ECECEC / #2F2F2F | 11.33:1 | 4.5:1 | ✅ Pass |
| dark | `text-primary` | `surface-sidebar` | #ECECEC / #171717 | 15.18:1 | 4.5:1 | ✅ Pass |
| dark | `text-primary` | `surface-composer` | #ECECEC / #2F2F2F | 11.33:1 | 4.5:1 | ✅ Pass |
| dark | `text-primary` | `surface-dialog` | #ECECEC / #121212 | 15.86:1 | 4.5:1 | ✅ Pass |
| dark | `text-primary` | `surface-user-message` | #ECECEC / #2F2F2F | 11.33:1 | 4.5:1 | ✅ Pass |
| dark | `text-primary` | `surface-nav-selected` | #ECECEC / #2F2F2F | 11.33:1 | 4.5:1 | ✅ Pass |
| dark | `text-primary` | `surface-tab-selected` | #ECECEC / #2F2F2F | 11.33:1 | 4.5:1 | ✅ Pass |
| dark | `text-secondary` | `surface-primary` | #CDCDCD / #0D0D0D | 12.23:1 | 4.5:1 | ✅ Pass |
| dark | `text-secondary` | `surface-chat` | #CDCDCD / #2F2F2F | 8.42:1 | 4.5:1 | ✅ Pass |
| dark | `text-secondary` | `surface-sidebar` | #CDCDCD / #171717 | 11.28:1 | 4.5:1 | ✅ Pass |
| dark | `text-secondary` | `surface-user-message` | #CDCDCD / #2F2F2F | 8.42:1 | 4.5:1 | ✅ Pass |
| dark | `text-secondary` | `surface-nav-selected` | #CDCDCD / #2F2F2F | 8.42:1 | 4.5:1 | ✅ Pass |
| dark | `text-tertiary` | `surface-primary` | #999696 / #0D0D0D | 6.62:1 | 4.5:1 | ✅ Pass |
| dark | `text-tertiary` | `surface-chat` | #999696 / #2F2F2F | 4.56:1 | 4.5:1 | ✅ Pass |
| dark | `text-tertiary` | `surface-sidebar` | #999696 / #171717 | 6.11:1 | 4.5:1 | ✅ Pass |
| dark | `text-tertiary` | `surface-nav-selected` | #999696 / #2F2F2F | 4.56:1 | 4.5:1 | ✅ Pass |
| dark | `text-on-status` | `surface-submit` | #FFFFFF / #047857 | 5.48:1 | 4.5:1 | ✅ Pass |
| dark | `text-on-status` | `surface-submit-hover` | #FFFFFF / #065F46 | 7.68:1 | 4.5:1 | ✅ Pass |
| dark | `text-on-status` | `surface-destructive` | #FFFFFF / #991B1B | 8.31:1 | 4.5:1 | ✅ Pass |
| dark | `text-inverted` | `button-primary` | #171717 / #FFFFFF | 17.93:1 | 4.5:1 | ✅ Pass |
| dark | `text-inverted` | `button-primary-hover` | #171717 / #ECECEC | 15.18:1 | 4.5:1 | ✅ Pass |
| dark | `text-inverted` | `surface-inverted` | #171717 / #FFFFFF | 17.93:1 | 4.5:1 | ✅ Pass |
| dark | `avatar-text` * | `avatar-fill` | #000000 / #FFCB05 | 13.80:1 | 4.5:1 | ✅ Pass |
| dark | `link` * | `surface-chat` | #FFCB05 / #2F2F2F | 8.80:1 | 4.5:1 | ✅ Pass |
| dark | `link` * | `surface-primary` | #FFCB05 / #0D0D0D | 12.77:1 | 4.5:1 | ✅ Pass |
| dark | `link-hover` * | `surface-chat` | #FFDD5C / #2F2F2F | 10.04:1 | 4.5:1 | ✅ Pass |
| dark | `link-prose` * | `surface-chat` | #FFCB05 / #2F2F2F | 8.80:1 | 4.5:1 | ✅ Pass |
| dark | `focus-outline` * | `surface-chat` | #FFCB05 / #2F2F2F | 8.80:1 | 3:1 (UI) | ✅ Pass |
| dark | `focus-outline` * | `surface-primary` | #FFCB05 / #0D0D0D | 12.77:1 | 3:1 (UI) | ✅ Pass |
| dark | `ring-primary` * | `surface-primary` | #FFCB05 / #0D0D0D | 12.77:1 | 3:1 (UI) | ✅ Pass |
| dark | `border-field-focus` * | `field-fill` | #FFCB05 / #0D0D0D | 12.77:1 | 3:1 (UI) | ✅ Pass |
| dark | `surface-inverted` | `surface-composer` | #FFFFFF / #2F2F2F | 13.39:1 | 3:1 (UI) | ✅ Pass |
| dark | `text-inverted` | `surface-inverted` | #171717 / #FFFFFF | 17.93:1 | 3:1 (UI) | ✅ Pass |
| dark | `surface-submit` | `surface-primary` | #047857 / #0D0D0D | 3.54:1 | 3:1 (UI) | ✅ Pass |
| dark | `surface-submit` | `surface-dialog` | #047857 / #121212 | 3.42:1 | 3:1 (UI) | ✅ Pass |

**Rendered login page, measured in the browser** (computed colours; it catches tokens outside the
table above):

| Element | Light | Dark |
|---|---|---|
| "Welcome back" heading | #212121 on #FFFFFF — 16.10:1 ✅ | #ECECEC on #0D0D0D — 16.45:1 ✅ |
| Continue button label | #FFFFFF on #000000 — 21.00:1 ✅ | #FFFFFF on #047857 — 5.48:1 ✅ |
| "Don't have an account?" | #424242 on #FFFFFF — 10.05:1 ✅ | #CDCDCD on #0D0D0D — 12.23:1 ✅ |
| "Sign up" / "Privacy policy" links | #000000 on #FFFFFF — 21.00:1 ✅ | #41A79D on #0D0D0D — 6.70:1 ✅ |
| Field label | #595959 on #FFFFFF — 7.00:1 ✅ | #999696 on #0D0D0D — 6.62:1 ✅ |

### Mobile width (390px), light and dark

The Chrome window could not be resized (it stayed 1920px), so the app was loaded in a 390×700
same-origin iframe. The app's viewport was confirmed at **390px**, so its media queries and mobile
layout apply exactly as on a phone. Horizontal overflow was checked with
`scrollWidth > innerWidth` on every screen.

| Screen | Light | Dark |
|---|---|---|
| Login | ✅ Logo, form and Continue fit; no overflow; MTN font. ⚠️ Theme toggle icons overlap "Privacy policy" (upstream layout) | ✅ Same layout, no overflow. ⚠️ Same icon overlap; Continue and links are LibreChat green |
| Chat (new + existing conversation) | ✅ Welcome wraps cleanly; yellow-tint user bubble; composer pinned to the bottom; footer hidden at this width (upstream behaviour); no overflow | ✅ Readable; no overflow |
| Sidebar (drawer) | ✅ Opens full-width; yellow selected row; no overflow | ✅ No overflow. Selected row is a subtle grey (weak, non-text indicator) |

Follow-ups (none block Phase 4):
1. **Login icon overlap** at ≤390px. Upstream layout; fixing it needs a client change, so report it
   upstream or handle it in a later build. Not fixable by config.
2. **Dark-mode brand accents.** Login CTA, links and the selected sidebar row use LibreChat
   green/grey. Set dark `surface-submit`/link/nav-selected tokens once MTN confirms the dark palette,
   then re-run the contrast script.

Screenshots from these checks were saved locally by the browser tool (not committed).
