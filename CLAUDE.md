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
      into `/app/client/dist`, links `fonts/mtn-fonts.css` from `index.html`, and sets `<title>`.
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
   (`s3`/`azure_blob`) at MTN-managed services. Confirm Code Interpreter/RAG connectivity.
5. **Phase 4 — Office document generation.**
   - *Step 1 — Self-hosted Code Interpreter.* Run the `librechat-code` service, set
     `LIBRECHAT_CODE_BASEURL` and `LIBRECHAT_CODE_API_KEY`, and enable the `execute_code`
     capability for agents. Build the sandbox image with `python-docx`, `python-pptx`,
     `openpyxl`, `pandas` and `matplotlib` preinstalled.
   - *Step 2 — Template-driven MCP tools.* Add MCP tools backed by versioned MTN templates:
     `create_word_document`, `create_powerpoint_presentation`, `create_excel_workbook`,
     `revise_office_file`. Include output file validation, previews, revision in chat, and
     per-user file ownership.
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
  `client/public/assets/`, so there is no upstream file diff. Inline theme is a **partial** token set (unnamed tokens keep LibreChat's
  defaults). In dark mode, yellow is not used behind the send button, because that would force a
  dark `text-on-status` label, which also sits on the red/status fills.
- _2026-11-08_ — **Brand fonts via a branding image (option 1 of 3, chosen by the user):** there is
  no config lever for extra `@font-face` files, so `mtn/branding/Dockerfile` layers fonts, assets
  and an `index.html` stylesheet link onto the unchanged upstream image. Rejected: a new
  `configSchema` lever (core change) and relying on locally installed fonts. Font files and the
  official logo stay in gitignored `mtn/branding/private/`. **Open:** MTN must confirm that the
  Newlyn Works licence covers web embedding for this app.
- _2026-11-08_ — **Local dev:** `SCHEDULES_SINGLE_PROCESS=true` in `.env` (single API replica, no
  Redis) so the schedules engine arms. Not for multi-replica deployments.

## Security & secrets

- **Never** place credentials, API keys, or secrets in this file, docs, or committed config.
  Secrets live in `.env` (git-ignored) and the deployment secret store.
- **Do not use real MTN data with the Groq endpoint.** Groq is a third-party dev/test provider,
  not MTN-approved. Use synthetic or public test data only. Real MTN data may only go to an
  MTN-approved provider once one is confirmed.
- **Never commit `.claude/helpers/` or `.claude/settings.local.json`.** They are per-machine
  Claude Code tooling (hook scripts, local permission allowlist), not project source.
- Key secret env vars (names only): `CREDS_KEY`, `CREDS_IV`, `JWT_SECRET`, `JWT_REFRESH_SECRET`,
  `MEILI_MASTER_KEY`, `LIBRECHAT_CODE_API_KEY`, provider API keys, OIDC/SAML client secrets,
  `ADMIN_PANEL_SESSION_SECRET`.
- Do not forward raw errors/stacks/provider payloads to clients (`AGENTS.md` → "Service failures and
  user-facing errors").
