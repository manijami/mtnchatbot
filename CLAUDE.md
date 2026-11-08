# MTN Employee AI Assistant — Project Guide (CLAUDE.md)

This repository is a fork of **LibreChat** used as the foundation for the **MTN Employee AI
Assistant**. This file records project-specific architecture, commands, and decisions for the MTN
effort. It does **not** replace upstream contributor guidance.

> **Read `AGENTS.md` first.** `AGENTS.md` is the authoritative upstream contributor guide (module
> boundaries, auth-cache rules, state ownership, service-failure contracts, testing, theming). This
> file layers MTN context on top of it. When the two appear to conflict, follow `AGENTS.md` for how
> to change core code, and this file for *what* the MTN product needs.

## Upstream baseline

- **Project:** LibreChat (`package.json` `version: v0.8.9-rc1`)
- **Checked-out tag:** `v0.8.9-rc1` (+84 commits)
- **Commit:** `f4154b649efa37e1345ccc517a4d8d1ed2178c82` ("chore: Bump Agents SDK to 4.2.1", #17664)
- **Working branch:** `mtn/employee-ai`
- **Upstream remote:** `https://github.com/LibreChat-AI/LibreChat.git`
- **Runtimes:** Node `24.22.1` (`.nvmrc`), optional Bun `1.4.4` (`.bun-version`). Package manager
  `npm@11.13.0`.

## Guiding principles (MTN)

1. **Preserve upstream features.** Do not remove or disable LibreChat capabilities unless MTN
   explicitly requires it. Prefer additive change.
2. **Configuration over code.** Achieve MTN requirements through `librechat.yaml`, `.env`, themes,
   and extension points before touching core LibreChat source.
3. **Keep core changes small.** New backend behavior lives in `packages/api` (TypeScript); `/api`
   stays wiring only. New config levers get a `configSchema` field with a backward-compatible
   default. See `AGENTS.md` → "Module boundaries and configuration".
4. **Stay upgradeable.** Isolate MTN customizations so upstream merges remain tractable. Document
   every deviation in "Implementation decisions" below.

## Architecture (as inherited)

Monorepo (npm workspaces + Turbo). Key workspaces:

| Workspace | Role |
|-----------|------|
| `api/` | Legacy Express wiring (CJS): routes, middleware, strategies, server bootstrap. Behavior-light. |
| `packages/api/` (`@librechat/api`) | TypeScript backend: agents, tools, code execution, files, MCP, services. New backend logic goes here. |
| `packages/data-schemas/` (`@librechat/data-schemas`) | Mongoose models and database methods. Owns DB contracts. |
| `packages/data-provider/` (`librechat-data-provider`) | Shared API types, React Query keys, data services, and `configSchema` (`src/config.ts`, ~6.2k lines). |
| `packages/client/` (`@librechat/client`) | Shared React primitives, theme system, variants. |
| `packages/chat/` (`@librechat/chat`) | Chat state/transport/message components (migration target; never imports the app). |
| `client/` | The React SPA (Vite). State migrating Recoil → Jotai (new state is Jotai). |

**Request/data flow:** React SPA → Express (`api/server`) → `@librechat/api` services → models in
`@librechat/data-schemas` → MongoDB. Search via **Meilisearch**. RAG/file embeddings via the
external **RAG API** + **pgvector**. Code execution via the external **LibreChat Code API**
(`LIBRECHAT_CODE_API_KEY`). Caching/streams/rate-limits optionally via **Redis**.

**Model endpoints** (`EModelEndpoint`): `openAI`, `azureOpenAI`, `anthropic`, `google`, `bedrock`,
`agents`, `custom` (any OpenAI-compatible provider).

**Authentication strategies** (`api/strategies`): local (email/password), JWT, Google, GitHub,
Discord, Facebook, Apple, **OpenID Connect**, **LDAP**, **SAML**. Multi-user with roles/permissions
and an optional bundled **Admin Panel**. See `AGENTS.md` → "Backend auth cache" before mutating user
documents.

**File handling** (`fileStrategy` in `configSchema`): `local`, `firebase`, `s3`, `azure_blob`,
`cloudfront`. SDKs already present for AWS S3/CloudFront, Azure Blob, Firebase. Office/PDF parsing
via `mammoth`, `pdfjs-dist`, `xlsx`.

## Deployment topology

`docker-compose.yml` services: `api` (LibreChat), `admin-panel`, `mongodb` (Mongo 8), `meilisearch`,
`vectordb` (pgvector), `rag_api`. `deploy-compose.yml` is the production stack; `helm/` provides
Kubernetes charts; `rag.yml` runs RAG + pgvector standalone. OpenTelemetry/Langfuse observability
via `otel/` and the langfuse-fanout compose files.

## Upgrading the upstream base

> **Since 2026-11-08 (MTN UI/UX phase) the local api image is built from this repo's source**:
> `docker build -f Dockerfile -t mtn-librechat-src:local .` (context rules in
> `Dockerfile.dockerignore`), then `docker compose build api` adds the branding layer on top
> (`BASE_IMAGE: mtn-librechat-src:local` in `mtn/deploy/compose.office.yml`). Upgrading upstream
> is then a normal merge plus rebuild; the overlay and fingerprint guard below are no longer used
> locally. Measured on the dev Mac (8 GB Docker VM, full stack running): cold build 655 s
> (`npm ci` 224 s, frontend build 188 s, image export 73 s), peak VM memory 4.4 GB, image 2.75 GB
> (upstream 2.71 GB); the branding layer takes about 3 s.

Previously, the local api image was three layers: **upstream LibreChat** (pinned by digest) → **branding**
(`mtn/branding/Dockerfile`) → **core-deviation overlay** (`mtn/deploy/core.Dockerfile`, the backend
build of our MTN core changes). The overlay replaces built files, so it is only valid on the exact
upstream build our source is based on.

- **Current base:** commit `f4154b649efa37e1345ccc517a4d8d1ed2178c82` (`v0.8.9-rc1`), image
  `registry.librechat.ai/librechat-ai/librechat-dev@sha256:9625652b9d9ac9fbf9ff3505fc34770f822c7aa079f58d06b4e66eed2dc93aeb`.
  Pinned in `mtn/branding/Dockerfile` (`ARG BASE_IMAGE`) and the local `docker-compose.override.yml`.
- **Guard:** upstream images carry no commit label, so `core.Dockerfile` checks the base image's
  `package.json` version and the SHA-256 of 392 upstream source files against
  `mtn/deploy/base-fingerprint.sha256`. Any other upstream build fails the overlay build.

To move to a new upstream commit:

1. Merge or rebase onto the new upstream commit on a branch; resolve conflicts in the MTN core
   deviations (decisions log); run the tests in each touched workspace.
2. Find the upstream image built from **that** commit (its creation time follows the commit) and
   pull it by digest: `docker pull registry.librechat.ai/librechat-ai/librechat-dev@sha256:<digest>`.
3. Confirm it is that commit: `mtn/scripts/base-fingerprint.sh <commit>` regenerates the
   fingerprint, then build the overlay. If the check fails, the image is not that commit; do
   not proceed (or build the full image from source in CI instead).
4. Update the digest in `mtn/branding/Dockerfile` and the override, plus `BASE_COMMIT` /
   `BASE_VERSION` in `core.Dockerfile`, and this section.
5. Rebuild in order: `docker build -t mtn-librechat:local mtn/branding`, then
   `npm run build:data-provider && npm run build:api`, then `docker compose build api`.
6. Re-run the Phase 4 checks (file card, reload, second-user isolation) before committing.

Production never uses the overlay: CI builds the whole image from source.

## Development commands

Install (root): `npm ci`

Build:
- `npm run build:packages` — build all shared packages in dependency order
- `npm run frontend` — build packages + client (production SPA)
- `npm run build` — Turbo build everything

Run locally (two terminals):
- `npm run backend:dev` — Express API with nodemon (dev)
- `npm run frontend:dev` — Vite dev server for the client
- Redis variants: `npm run backend:dev:redis:single` / `:cluster` (plus `npm run redis:single`)

Docker (full stack): `docker compose up -d` (needs a populated `.env`; copy from `.env.example`).

Config/admin CLIs (`config/`): `npm run create-user`, `invite-user`, `list-users`,
`reset-password`, `ban-user`, `delete-user`, `add-balance`, `update-banner`, `reset-terms`,
plus `migrate:*` scripts for index/permission migrations.

## Testing & verification expectations

Follow `AGENTS.md` → "Testing" and "Verification". In short:

- **Typecheck is separate from build.** Builds use `tsdown` (no type checking). Run
  `npx tsc --noEmit` in every workspace you change.
- **Focused tests from the owning workspace**, not the whole monorepo:
  `npm run test:api`, `npm run test:client`, `npm run test:packages:api`,
  `:data-provider`, `:data-schemas`, `:chat`. `npm run test:all` runs everything.
- Prefer real logic + spies; `mongodb-memory-server` for DB; real MCP SDK for MCP; mock only
  external HTTP.
- Frontend tests cover loading / success / failure states in colocated `__tests__`.
- Static checks: `npm run static-checks -- --against origin/dev` (slow gates:
  `static-checks:full`). Lint: `npm run lint` / `lint:fix`. Imports: `npm run sort-imports -- <paths>`
  (never argument-less — it rewrites every root).
- Performance budgets: `npm run lighthouse` for startup/auth/config/file/message-loading changes.
- Always run tests after code changes and verify the build before committing (per project rules).

## MTN design requirements

> Fill in concrete values as MTN brand/governance confirms them. Implement via config/theme first.

- **Branding / identity**
  - App title via `APP_TITLE`; footer via `CUSTOM_FOOTER`; help link via `HELP_AND_FAQ_URL`.
  - Welcome copy via `interface.customWelcome` in `librechat.yaml`.
  - **Where MTN branding lives (isolated from upstream files):**
    - `mtn/config/librechat.yaml`: tracked source of truth for the LibreChat config. The root
      `librechat.yaml` (gitignored) is a symlink to it, and the compose override mounts it.
    - `mtn/branding/Dockerfile`: a thin **branding image** (`mtn-librechat:local`) built `FROM` the
      unchanged upstream image. It copies the logo, favicons, PWA manifest and MTN Brighter Sans
      into `/app/client/dist`, links `fonts/mtn-fonts.css` and `css/mtn-overrides.css` from
      `index.html`, and sets `<title>`.
      `client/public/assets/` stays upstream-identical. Rebuild with `docker compose build api`
      after every base-image update.
    - `mtn/branding/private/` (**gitignored, never commit**): licensed MTN Brighter Sans `.otf`
      files (© Newlyn Works), the official logo source files, and `generated/` icons derived from
      them. Distribute out-of-band (secret store / secure share), not via git.
    - `mtn/branding/assets/` + `manifest.webmanifest` + `fonts/mtn-fonts.css` (tracked): placeholder
      icons used when `private/` is absent, the manifest, and the font-face CSS (no font data).
  - Copy, URLs and policy text are still **PLACEHOLDERS** (marked "PLACEHOLDER"). The logo, icons
    and font are now official MTN assets, supplied 2026-11-08.
  - **Theme:** use `interface.theme` — a bundled name (`librechat`, `clickhouse`) **or an inline
    definition** with `rgb-*` color tokens per light/dark mode and `appearance` roles
    (`controlRadius`, etc.). This is the preferred path for the MTN palette (brand yellow/black).
    Do not hard-code colors in feature code; deepen the shared theme token registry instead
    (`AGENTS.md` → "Frontend theming and styling").
- **Authentication:** support **both OpenID Connect and SAML** against MTN's IdP; **SSO is the
  main way in.**
  - **Dev:** `ALLOW_REGISTRATION=true` (local self-registration enabled for testing).
  - **Production:** `ALLOW_REGISTRATION=false` (no self-registration); keep
    `ALLOW_EMAIL_LOGIN=true` so admin-provisioned accounts (`npm run create-user` /
    `npm run invite-user`) can still sign in with email/password.
  - (Decision 2026-11-08, supersedes 2026-11-07.)
- **Terms / privacy:** set `interface.privacyPolicy` and `interface.termsOfService` (supports modal
  acceptance) to MTN-approved URLs/content.
- **Data residency & storage:** choose `fileStrategy` (likely `s3`/`azure_blob` on MTN cloud) and
  point Mongo/Meilisearch/pgvector at MTN-managed infrastructure.
- **Models:** route through MTN-approved providers (Azure OpenAI, Bedrock, Anthropic, or a `custom`
  OpenAI-compatible gateway). Use `modelSpecs` to curate the models employees see.
- **Governance:** consider moderation, rate limits, token/balance accounting, and audit logging.

## Implementation plan (phased)

> **Execution order (decided 2026-11-08):** Phase 0 (done) → **1 → 4 → 2 → 3 → 5 → 6**. Phase
> numbers below are stable identifiers, not the run order. Phase 4 (Office document generation)
> runs right after Phase 1 because it is not blocked on MTN inputs and is the key demo value.

1. **Phase 0 — Baseline & environment.** Reproduce a clean local run (Docker stack + `.env` from
   `.env.example`), confirm version/commit, record upstream remote for future merges. No behavior
   change. *(this inspection step)*
2. **Phase 1 — Configuration & branding (no core changes).** MTN `librechat.yaml` + `.env`:
   `APP_TITLE`, footer, help URL, `customWelcome`, privacy/ToS, inline MTN theme, brand assets.
   **Models: keep all endpoints available for now** (decision deferred); curate `modelSpecs` once
   MTN's primary provider is confirmed. Validate via the running app + Lighthouse.
3. **Phase 2 — Identity & access.** Wire **both OIDC and SAML** SSO against MTN's IdP as the main
   way in. Local registration stays on in dev only; production sets `ALLOW_REGISTRATION=false` and
   keeps email login for admin-provisioned accounts (`create-user`/`invite-user`). Configure roles/
   permissions and the Admin Panel. Verify auth-cache invalidation rules.
4. **Phase 3 — Infrastructure & data.** Point Mongo, Meilisearch, pgvector/RAG, and file storage
   (`s3`/`azure_blob`) at MTN-managed services. Confirm RAG connectivity. Also (moved/added
   2026-11-08):
   - **Self-hosted Code Interpreter** (ClickHouse/code-interpreter, Apache-2.0) on a **Linux host
     with KVM** (libkrun microVM isolation). Connect via `LIBRECHAT_CODE_BASEURL` and per-user
     `CODEAPI_JWT_*` auth; pin `sha-` image tags; no sandbox internet. Sandbox image must include
     `python-docx`, `python-pptx`, `openpyxl`, `pandas`, `matplotlib`.
   - **Requirement: Python data analysis of uploaded spreadsheets** (via `execute_code`), which
     depends on the Code Interpreter above.
   - **office-mcp storage:** move its SQLite job/version store to managed Postgres or Mongo for
     multi-replica production.
   - **Redis streams** for multi-replica API (replaces `SCHEDULES_SINGLE_PROCESS`).
5. **Phase 4 — Office document generation** (template-driven MCP tools, no Code Interpreter).
   `mtn/services/office-mcp/` (Python, streamable HTTP, internal network, bearer-token auth,
   owner from `{{LIBRECHAT_USER_ID}}`): `create_word_document`, `create_powerpoint_presentation`,
   `create_excel_workbook`, `revise_office_file`, `get_generation_status`. Versioned MTN
   templates (`mtn/templates/`), validation (reopen, MIME, bounds, LibreOffice recalc, preview),
   v1/v2 versioning, per-user ownership. Files reach the chat through the MCP file-outputs core
   change (decisions log). `revise_office_file` edits only files the same user generated; editing
   **employee-uploaded** Office files is a later item.
6. **Phase 5 — MTN-specific capability (only if config can't express it).** Any new backend lever
   lands in `packages/api` with a `configSchema` field + backward-compatible default; `/api` stays
   wiring. MCP servers / custom tools / agents for MTN knowledge sources.
7. **Phase 6 — Hardening & observability.** Security headers/CSP, rate limits, moderation, OTel/
   Langfuse, performance budgets, accessibility, localization. Full test + static-check gates before
   release.

## Implementation decisions (log)

Record every deviation from upstream here with rationale, so future upstream merges stay tractable.

- _2026-11-07_ — Created this `CLAUDE.md`. No application behavior changed; inspection only.
  Established the config/theme-first, preserve-upstream, small-core-change policy above.
- _2026-11-07_ — **Auth:** support both OIDC and SAML SSO **and keep local registration + admin
  user creation enabled** (SSO is additive). **Models:** defer primary-provider choice; keep all
  endpoints available and curate `modelSpecs` later.
- _2026-11-08_ — **Auth (supersedes the 2026-11-07 auth decision):** local registration enabled in
  dev only. Production disables self-registration (`ALLOW_REGISTRATION=false`), keeps email login
  for admin-provisioned accounts, and SSO (OIDC + SAML) is the main way in.
- _2026-11-08_ — **Plan:** added Phase 4 "Office document generation" (self-hosted Code
  Interpreter + template-driven MCP Office tools); later phases renumbered to 5 and 6.
- _2026-11-08_ — **Execution order:** 1 → 4 → 2 → 3 → 5 → 6 (phase numbers unchanged). Rationale:
  Office document generation does not depend on MTN inputs (brand assets, IdP, infrastructure) and
  is the key demo value, so it moves ahead of Identity (2) and Infrastructure (3), which are blocked
  on MTN.
- _2026-11-08_ — **Phase 1 starts with placeholders:** logo, font files, and policy/help URLs use
  clearly marked placeholders; do not wait for MTN brand assets. Swap in real assets when received.
- _2026-11-08_ — **Phase 1 layout:** MTN config and brand assets live under `mtn/` and reach the
  app through a branding image layered on the upstream image (see below), not by editing
  `client/public/assets/`, so there is no upstream file diff. Inline theme is a **partial** token
  set (unnamed tokens keep LibreChat's defaults). The chat send button uses
  `surface-inverted`/`text-inverted`. Check contrast with `node mtn/scripts/theme-contrast.js .`
  (full table in `docs/mtn/theme-contrast.md`) after **any** palette change.
- _2026-11-08_ — **Dark-mode accents = MTN yellow (supersedes "no yellow `surface-submit` in
  dark").** `accent-primary` and `surface-submit` are `#FFCB05`, with a **black** `text-on-status`
  label. Because that label sits on every solid status fill, `surface-destructive`/`-hover` and
  `status-*-strong` move to their bright ends so black text passes AA. The selected row/tab fill is
  `#786414`: 3.1:1 against the sidebar, with `text-primary` at 4.89:1. Semantic greens and provider
  icons are unchanged. Light-mode selection fills stay at the upstream level (1.19:1, fill-only);
  open design follow-up.
- _2026-11-08_ — **Branding-layer CSS:** `mtn/branding/css/mtn-overrides.css` (linked by the
  Dockerfile) holds tiny layout fixes for upstream issues only; colours stay in `interface.theme`.
  The first fix lifts the auth footer clear of the theme toggles below 768px, scoped with `:has()`
  to the auth layout. It is a no-op if upstream changes that markup. Report the overlap upstream.
- _2026-11-08_ — **Brand fonts via a branding image (option 1 of 3, chosen by the user):** there is
  no config lever for extra `@font-face` files, so `mtn/branding/Dockerfile` layers fonts, assets
  and an `index.html` stylesheet link onto the unchanged upstream image. Rejected: a new
  `configSchema` lever (core change) and relying on locally installed fonts. Font files and the
  official logo stay in gitignored `mtn/branding/private/`. **Open:** MTN must confirm that the
  Newlyn Works licence covers web embedding for this app.
- _2026-11-08_ — **Phase 4 design (approved):** Office generation is a Python MCP server
  (`mtn/services/office-mcp/`) that turns validated JSON into documents from versioned templates.
  No model-written code runs. The **Code Interpreter is deferred to Phase 3** (KVM host): this dev
  Mac's Docker VM has no `/dev/kvm`, and the upstream project labels NsJail-only mode
  "not for untrusted code". The agent's model is configurable (Groq dev tier now, MTN-approved
  provider later) without code changes. The official logo is added at generation time from
  gitignored `mtn/branding/private/`; output is logo-free when it is absent. office-mcp keeps
  SQLite for dev, with retention matching LibreChat's file retention.
- _2026-11-08_ — **FIRST MTN CORE DEVIATION — MCP file outputs** (approved). Upstream v0.8.9-rc1
  turns non-image MCP embedded-resource blobs into a text summary, so an MCP tool cannot deliver a
  `.docx`/`.pptx`/`.xlsx` as a chat attachment, and upstream `dev` has no equivalent. Added an
  opt-in per-server `fileOutputs` config (default **off**). Conditions:
  - It is honoured **only for admin-defined `librechat.yaml` servers**; user-added (UI/DB) servers
    never return files, even if they set the field. This is enforced in code and tested.
  - Files are saved through the existing file pipeline and `fileStrategy` as normal user-owned
    files, so access checks, per-user limits and the Files list apply.
  - Logic lives in `packages/api`; `/api` has wiring only.
  - Upstream proposal: `docs/mtn/upstream-proposal-mcp-file-outputs.md`.
- _2026-11-08_ — **Upstream base pinned by digest + overlay guard.** The local api image is
  upstream (digest-pinned, commit `f4154b649`) → branding → core-deviation overlay. The overlay
  build fails unless the base image's sources match `mtn/deploy/base-fingerprint.sha256`. Upgrade
  procedure: "Upgrading the upstream base" above.
- _2026-11-08_ — **Dev model: NVIDIA Nemotron 3 Ultra is the MTN Document Assistant default;
  Groq `gpt-oss-120b` is the fallback.** Chosen on a 12-prompt + multi-turn-revision tool-call
  probe run against the real office-mcp (Nemotron: median ~11 s per call, no over-asking, no 429s;
  Muse Glimmer was as accurate but 4x slower, p90 ~2 min). The assistant is two `modelSpecs`
  entries (instructions in `promptPrefix`, `mcpServers: [mtn-office]`, File Search), not a
  database agent: the agents REST API rejects non-browser clients (`uaParser`), so a scripted REST
  seed would need a faked browser User-Agent. **NVIDIA-hosted endpoints are dev-only and take
  synthetic data only.** Nemotron is a candidate for self-hosting via NVIDIA NIM in Phase 3
  (licence to be confirmed). RAG embeddings in dev also use NVIDIA (`nvidia/nemotron-3-embed-1b`,
  `mtn/deploy/compose.rag-nvidia.yml`).
- _2026-11-08_ — **Muse Glimmer removed from the model picker.** `meta/muse-glimmer-30b` was the
  backup NVIDIA candidate. On the tool-call probe it was as accurate as Nemotron Ultra (10/11 tasks
  within 3 calls) but 3-4x slower (median 40-43 s per call, p90 up to ~2 min), and in an early
  run it answered two deck requests in text instead of calling the tool. Only Nemotron Ultra is
  listed for the `nvidia` endpoint; Groq `gpt-oss-120b` remains the fallback spec.
- _2026-11-08_ — **Phases 2 (Identity), 3 (Infrastructure & data) and 6 (Hardening) paused** by the
  user. Next: finish Phase 4's second-user API check, then a **"Model router demo"** (NVIDIA NeMo
  Switchyard routing chat turns across Groq and NVIDIA models) on branch `mtn/router-switchyard`,
  dev/demo only with synthetic data. Phase 3 items recorded above (Code Interpreter, managed
  stores, Redis streams, NIM self-hosting) stay on the list for when the phase resumes.
- _2026-11-08_ — **Model router demo (approved plan).** NVIDIA NeMo Switchyard (Apache-2.0,
  pre-alpha; standalone server is demo-only upstream) routes each "MTN Smart Chat" turn across
  three tiers with a `llm_classifier` **custom** route: fast = Groq `gpt-oss-20b`, balanced =
  Groq `gpt-oss-120b`, capable = NVIDIA Nemotron 3 Ultra; judge = Groq `gpt-oss-20b`. Built from
  pinned `v0.3.0` (`336196f6`) with one local patch so custom mode records the judge's verdict and
  a short reason (`docs/mtn/upstream-proposal-switchyard-reason.md`). A small sidecar
  (`router-lens`) proxies LibreChat → Switchyard to add an optional routing footer
  (`SHOW_ROUTING_FOOTER`, default off) and a live decision feed. Switchyard publishes no ports;
  Prometheus is published on `127.0.0.1:9091` only for the local Grafana. The MTN Document
  Assistant stays pinned to Nemotron Ultra. Dev/demo only, synthetic data only; no LibreChat
  core change. Cost is shown as a relative index (100 = every turn on the capable tier) from
  published list prices, not in currency.
- _2026-11-08_ — **Local dev:** `SCHEDULES_SINGLE_PROCESS=true` in `.env` (single API replica, no
  Redis) so the schedules engine arms. Not for multi-replica deployments.
- _2026-11-08_ — **Router fixes (branch `mtn/ui-brand`).** router-lens answers Word/PowerPoint/Excel
  requests in Smart Chat with a pointer to the Document Assistant, caps the wait for an answer
  (45 s to first response, 45 s of silence mid-stream; both configurable), and replaces images in
  earlier turns with a text note. **Vision tier (approved):** turns whose latest message has an
  image skip the judge and go to NVIDIA `nemotron-3-nano-omni-30b-a3b-reasoning` through a
  Switchyard passthrough route (`mtn-smart-vision`); footer and feed show "vision tier"; vision
  turns are left out of the cost index. Synthetic images only.
- _2026-11-08_ — **MTN UI/UX phase (plan approved).** Stages A (config/CSS) → B (layout) → C (Office
  card, preview panel, chips). MTN components live in `client/src/mtn/` behind a new
  **`interface.mtnLayout`** `configSchema` flag (default `false`: upstream look and behaviour).
  Sidebar "Projects" links to LibreChat's existing Projects; no notifications icon; help opens
  `HELP_AND_FAQ_URL`; "Internal workspace" is a static label. Stage C adds an "Open in Document
  Assistant" chip to Smart Chat's Office reply (client-side; starts a new Document Assistant chat
  with the request pre-filled).
- _2026-11-08_ — **UI/UX approach B approved; decisions for the build:**
  - Assistants nav lists the MTN assistants (model specs); agents marketplace hidden
    (`interface.marketplace.use: false`).
  - **Shared links off** (`interface.sharedLinks` create/share/public `false`) until MTN sets a
    sharing policy: a shared link is a public snapshot, and file downloads in it would not work
    for other people anyway.
  - Dark mode top bar: black with a yellow bottom line, logo on a yellow tile.
  - Office icons: generic DOCX/PPTX/XLSX/PDF; official ones only if supplied with approval.
  - Placeholders: Document Assistant "What would you like to create?"; Smart Chat "Ask anything
    about your work…". Card headline from the tool result ("Your <file type> is ready."), note
    "Sample content: check before sharing.", "Needs review" + reason when validation flags anything.
  - Quick-create chips ("Word document", "PowerPoint deck", "Excel workbook") on the empty screen
    and in the "+" menu only; at most 3 follow-ups, suggested by office-mcp per file type.
  - User card role: static "MTN employee" until SSO provides a title.
  - Build order: 1 shell → 3 file card → 2 header/composer → 5 chips → 4 preview → 6 → 7.
- _2026-11-08_ — **Step 1 (app shell) implementation.** `client/src/mtn/` (top bar, sidebar, styles,
  tests). Upstream touch points, all inert while `mtnLayout` is off: `configSchema`
  (`interface.mtnLayout`), the interface loader, `Root.tsx` (renders the top bar, passes the flag),
  `UnifiedSidebar.tsx` (MTN sidebar instead of the rail; upstream drawer id/behaviour kept),
  `AccountSettings.tsx` (optional `subtitle`), one `mtn-*` entry in the lint class allow-list,
  translation keys `com_mtn_*`. The chat list, search, panels and account menu are upstream's;
  every other rail panel stays reachable under "More tools".
- _2026-11-08_ — **Local dev finding:** the user-level npm config sets `legacy-peer-deps=true`, so
  host installs skip peer dependencies (`rc-input-number`, `@radix-ui/react-slot`, and likely the
  earlier `winston-daily-rotate-file` gap). Install with
  `npm ci --legacy-peer-deps=false` for local tests; Docker/CI builds are unaffected.
- _2026-11-08_ — **CORE DEVIATION #2 — Office preview route** (approved, Stage C):
  `GET /api/files/:id/preview`. Returns rendered pages (PNG; PDF where useful) for Word/PowerPoint
  files and a JSON table summary for Excel, produced by office-mcp next to each version. Conditions:
  - Owner-checked with the existing file access check; anyone else gets 404.
  - Preview data goes only to the browser: it is never added to message content, tool results or
    anything sent to a model.
  - Logic in `packages/api`; `/api` has wiring only; inert unless `interface.mtnLayout` is on.
  - Tests: owner 200, other user 404, and no preview data in the model request.
- _2026-11-08_ — **Stage A composer accents in `mtn-overrides.css`.** The yellow composer border
  and yellow send button have no dedicated theme token (the tokens they use are shared with many
  components), so they are scoped to upstream's `data-testid="composer-surface"` and
  `data-testid="send-button"`. Exception to "colours stay in `interface.theme`"; falls back to
  the theme if upstream renames the ids.
- _2026-11-08_ — **Local image built from source (replaces the overlay).** The api image is built
  from the repo with the upstream `Dockerfile`, then the branding layer on top. A new
  `Dockerfile.dockerignore` (BuildKit reads it instead of `.dockerignore` for `./Dockerfile`)
  keeps `mtn/` (incl. the licensed fonts), `uploads/`, `logs/` and `images/` out of the image.

## Security & secrets

- **Never** place credentials, API keys, or secrets in this file, docs, or committed config.
  Secrets live in `.env` (git-ignored) and the deployment secret store.
- **Do not use real MTN data with the Groq or NVIDIA-hosted endpoints** (chat or embeddings).
  Both are third-party dev/test providers, not MTN-approved. Use synthetic or public test data only. Real MTN data may only go to an
  MTN-approved provider once one is confirmed.
- **Never commit `.claude/helpers/` or `.claude/settings.local.json`.** They are per-machine
  Claude Code tooling (hook scripts, local permission allowlist), not project source.
- Key secret env vars (names only): `CREDS_KEY`, `CREDS_IV`, `JWT_SECRET`, `JWT_REFRESH_SECRET`,
  `MEILI_MASTER_KEY`, `LIBRECHAT_CODE_API_KEY`, provider API keys, OIDC/SAML client secrets,
  `ADMIN_PANEL_SESSION_SECRET`.
- Do not forward raw errors/stacks/provider payloads to clients (`AGENTS.md` → "Service failures and
  user-facing errors").
