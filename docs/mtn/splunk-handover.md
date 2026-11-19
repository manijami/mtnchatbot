# Splunk integration handover — 2026-11-11

## Groq request-size mitigation

The operator observed HTTP 413: requested 8,091 tokens against an 8,000 TPM account limit. The Operations assistant now sets maxContextTokens=6000 and max_tokens=1024, retaining the approved model and tool attachments. Full configuration schema validation passed; only the isolated API was restarted. This is a mitigation, not a verified end-to-end fix: tool definitions/results and successive calls can still exhaust provider limits. A fresh-chat browser retry remains required. No paid tier was activated.

## Current decision checkpoint

**Overall: incomplete; full acceptance has not passed.** This checkpoint supersedes historical blocked-runtime statements below. The operator supplied the archive and accepted the vendor terms. The isolated Splunk and chatbot services are now running. Local demo administration was performed after authorization; no vendor account was used.

- Passed: verified-TLS official MCP discovery and a real read-only query. Exactly eight approved tools were discovered.
- Passed: the chatbot called `splunk_run_query_mcp_mtn-splunk`; the persisted tool output contains an actual result row with marker `MTN_CHATBOT_SPLUNK_PROOF`.
- Failed: the subsequent assistant text returned `MTN_CHATBOT_SPLITK_PROOF`, misspelling the evidence. The first response also ended in a rate-limit error. A completed tool call therefore does not establish a reliable final answer.
- Pending: demo ingestion, incident investigation, live security/workload negative tests, live incident-report Word download and representative peak memory measurement.
- Pending by design: MSISDN masking.
- Original application remains running at http://localhost:3080. Isolated integration UI: http://localhost:3081; Splunk Web: http://localhost:8001. Docker status checked after the proof.

Evidence is private and gitignored: `mtn/splunk/private/results/mcp-proof.json`, `chatbot-proof-messages.json`, and `chatbot-splunk-tool-completed-rate-limit.png`. The latter shows the interrupted first turn, not successful full acceptance.

Recent infrastructure fixes: use a primary UI bridge for loopback port publication; preserve internal management/ingestion connectivity; repair the Splunk leaf certificate to support both server and client authentication for KV Store while retaining the CA; explicitly disable inherited role capabilities. Runtime authorization remains an acceptance gate.

The next gate is a correct, evidence-grounded chatbot answer. Do not describe the integration as ready on the strength of container health or tool execution alone. No merge or push performed.

## Resume checkpoint — 2026-11-11

The operator supplied the official `splunk-mcp-server_210.tgz` archive (app 2.1.0), licence flags,
local admin password and dev provider/Office values. The original download is retained and a
fixed-name source copy is present. Vendor SHA-256:
`b86042f4fcccc8f743fb58a9062d2c2d350686cddf94876634b4e235a2e0a7bc`.
The current official Splunkbase listing explicitly supports 10.4 for app 2.1.0.

Fresh application encryption/session secrets were generated only for previously blank fields in
this worktree's private `.env`; existing populated values and the original MTN runtime were not changed.
TLS and the `mtn-demo.tgz` configuration bundle are prepared. Five preparation tests pass.

Archive inspection confirmed actual `mcp.conf.spec` fields for maximum and default rows, TLS CA
path, timeout and token lifetimes. `mtn/splunk/mcp.conf` sets max/default 100 rows, timeout 60,
30-day maximum/default minted-token life, CA verification, 12 calls/minute global and 6 query
calls/minute. The per-tool rate key is the installed ID `splunk_mcp_app_builtin:run_query`.
These are configured controls; runtime enforcement and actual issued-token expiry remain untested.

A derived `private/splunk-mcp-configured.tgz` adds only `Splunk_MCP_Server/local/mcp.conf`.
Vendor code/data files are preserved byte for byte; the original archive is unchanged. The overlay
mounts this derived install archive and the independent MTN demo app archive. A preparation test
verifies preservation and rejects an unexpected pre-existing vendor local/mcp.conf.

Container `mtn-splunk-codex-splunk-1` has been **created, not started by the agent**, using only
project-scoped networks and volumes. The original `mtn-employee-ai` project remains running.
First launch/trial initialization is reserved for the operator by their explicit earlier instruction.
The operator was given `docker start mtn-splunk-codex-splunk-1` and asked to confirm startup.

MCP and HEC tokens are still expected to be blank until the operator performs app/identity setup.
No live Splunk acceptance result is claimed. The historical results below describe the earlier
preparation run; archive/initial-secret absence is now resolved as described in this checkpoint.

## Worktree and prerequisites

Work remained in `/Users/subhangisilla/dev/mtn-employee-ai-codex`, branch
`codex/splunk-integration`, HEAD `19b59ceb231709fd3c933013cc5db5e228fc5709` (no new commit).
Prerequisites `65d5b30f4` and `81dc4f8c2` were already verified as ancestors. The existing
`.gitignore` change and this handover were preserved and extended. Claude's worktree and
`mtn/ui-brand` were not modified. No remote review/CI run was requested.

The gitignored official-app location is:

`/Users/subhangisilla/dev/mtn-employee-ai-codex/mtn/splunk/private/splunk-mcp-server.tgz`

Filename is fixed; manually rename the official download. Actual archive version/hash and installed
compatibility remain unknown. The app is Splunkbase **7931**, not a third-party MCP adapter.

The approved image manifest exists and is pinned in the overlay:

```text
splunk/splunk:10.4.5@sha256:bb4607d1bea70bec6d7f6ef0ff66f8e74180f1d2d7e3a1573909bd09660a0f59
linux/amd64
```

The shared daemon reports x86_64 and 8,346,099,712 bytes (7.773 GiB) total memory. Initial inspection
found the existing `mtn-employee-ai` project with ten containers. No stop/restart/removal commands were issued against it. A later inspection found all ten
existing containers exited (0/143, router-lens 137); the cause is unverified. They were not restarted.
The new project is `mtn-splunk-codex`; no fixed container names or shared volumes are used.
Ports 8001 (Splunk Web) and 3081 (independent LibreChat) were not listening when audited.

## Changed files

| Files | Purpose |
|---|---|
| `.env.mtn.example` | Points to the independent Splunk environment template without changing shared-stack defaults |
| `.gitignore` | Ignore licensed archives, private TLS and local evidence under `mtn/splunk/private/` |
| `mtn/deploy/compose.splunk.yml` | Digest-pinned 3 GiB Splunk, etc/var persistence, internal network/HEC and public-CA mounts |
| `mtn/deploy/compose.splunk-demo.yml` | Separate API/Mongo/Office stack without root Compose fixed-name conflicts |
| `mtn/config/librechat.yaml` | Operations Assistant on Groq 120B, Office/Splunk MCP, incident skill, narrow address allowlist |
| `mtn/skills/mtn-skills/incident-report-rca/SKILL.md` | Untrusted-log handling, evidence/search trace, six-section Word report |
| `mtn/splunk/.env.example` | Blank operator acceptance and secret values, isolated project defaults |
| `mtn/splunk/config/default/{app,authorize,indexes,props,savedsearches,server}.conf` | Demo role/index limits, JSON fields, replay alerts, management TLS |
| `mtn/splunk/config/metadata/default.meta` | Admin writes, readonly role reads; shared demo objects |
| `mtn/splunk/{prepare,preflight,memory,verify_mcp}.py` | Archive/TLS preparation, safe prerequisite status, VM sampling, real MCP SDK discovery/cases |
| `mtn/splunk/{test_prepare.py,validate.cjs}` | TLS/archive checks and full LibreChat schema/config assertions |
| `mtn/demo/splunk/{seed.py,test_seed.py,verify_word.py}` | Reproducible data and real Office MCP offline Word/download/owner checks |
| `docs/mtn/{splunk-integration,splunk-handover,feature-register}.md` | Setup, security targets, actual evidence and pending actions |

A gitignored root `.env` was created with mode 0600 from the template and blank operator values;
no other worktree's runtime configuration or secrets were copied. No root Compose override is
needed. The API receives only its selected variables, excluding the Splunk admin password and HEC
token. Private CA signing keys are not mounted into any service.

## Passed checks

| Check | Evidence |
|---|---|
| Registry image manifest and pull | Exact digest above, Linux amd64; full digest-pinned image download succeeds; image ID `fe986be9ed4e`; no version substitution |
| Image role specifications | Selected image packaged `authorize.conf.spec` confirms units/semantics of window, earliest event, runtime, concurrency and disk quotas; runtime enforcement still blocked |
| Image acceptance variables | Read-only shell with normal entrypoint bypassed confirms both required flags in `/sbin/entrypoint.sh`, with no defaults; Splunk not started |
| Compose parse | `docker compose ... config --quiet` passes using non-acceptance validation placeholders; no services started by validation |
| LibreChat YAML | Full `configSchema.parse` plus assistant model/tools/skill, HTTPS endpoint and address assertions pass in isolated local base-image container |
| Synthetic incident | `python3 -m unittest discover -s mtn/demo/splunk -p 'test_*.py' -v`: 1 behavior test passes; covers deterministic output, seven-day bounds, two affected hosts, rollback, four alert markers, two injection fixtures and synthetic identifiers |
| Archive/TLS | `python3 -m unittest discover -s mtn/splunk -p 'test_*.py' -v`: 4 tests pass; absent/traversal and pre-alert app releases rejected, metadata inspected, trusted hostname verifies, wrong hostname rejected, existing CA preserved; generated config app reproducible and contains no TLS keys |
| Python syntax | `python3 -m py_compile` for seed, preparation and preflight passes; `ast.parse` passes for all eight new Python files; MCP audit CLI imports against the real SDK |
| Source whitespace | `git diff --check` passes |
| Source image | `docker build -f Dockerfile -t mtn-splunk-librechat-src:local .` passes; image `sha256:13165b4ff54e4e98f09cb5b8b837f7866c27325298fc2d0f7dcaeb79652068a3` |
| Demo runtime images | Branding `mtn-splunk-librechat:local` (`c81432e7ef90`) and Office `mtn-splunk-office-mcp:local` (`46f5461e4614`) build successfully under separate tags; placeholder branding because licensed assets are absent |
| Office test image | Built this worktree's `mtn/services/office-mcp` test target under distinct tag `mtn-splunk-office-test:local` |
| Word MCP contract | Real in-process Streamable HTTP MCP call creates `incident_report v0.1`, validated OOXML, reopened, rendered by LibreOffice, 1 page, all six headings; owner REST download bytes match generated resource; other owner gets 404 |
| VM sample, offline only | 60 samples, one-second interval, peak 1,810,132,992 bytes / **1.686 GiB** while repeating the offline Word check; live Splunk was absent and this is not a full-stack baseline |

The initial YAML schema check used the existing local base-image ID `bd4391bbe495`.
It was repeated against this worktree's newly built `mtn-splunk-librechat-src:local` image in a
network-free test container. Both validate the full config and focused Operations assertions.
No TypeScript workspace source was changed; a workspace typecheck was not applicable.

Final deterministic seed measurement with `--now 2026-11-10T12:00:00+02:00`:

```text
events: 90731
bytes: 33454392
SHA-256: dc38db1c086d69c45dc4d7a070a73c8911a1be28498ec73e56d3773dbe63a54c
RNG seed: 7931
```

The full NDJSON fixture was generated in `/private/tmp/mtn-splunk-seed-final.ndjson`, not ingested.
The generator defaults to execution time for a fresh demo. Its four saved alert definitions replay
seeded incident markers; actual scheduler firings occur after ingestion, not retroactively overnight.

## Failed attempts and corrections

- The first image-spec inspection used a runtime path that is empty before bootstrap. Located
  the packaged spec under `/opt/splunk-etc` and verified the settings there; no Splunk startup occurred.
- Initial YAML validation rejected parentheses in the MCP display title. Corrected to
  `MTN Splunk Synthetic Demo`; the rerun **passed**.
- An initial Compose command used an option unsupported by installed Compose 2.17.2.
  Repeated with supported `config --quiet`; **passed**.
- Initial Python syntax check hit a sandbox restriction on macOS's Python cache. The approved
  rerun **passed**.
- Browser navigation to `http://127.0.0.1:3081` observed **ERR_CONNECTION_REFUSED**. Chrome did
  not produce a screenshot for that failed navigation. The supplied blocked screenshot is a
  local prerequisite report, explicitly labelled as such; it is not an application screenshot.

## Blocked checks — none count as passed

| Acceptance/check | Blocker / current result |
|---|---|
| Payment incident investigation | No running Splunk, app archive or model credentials |
| Errors by host in last hour | Same; seed fixture verified offline, no live aggregate comparison |
| Overnight fired alerts | No scheduler run; historical evidence and actual firing time must be distinguished |
| Explain this SPL in browser | Independent LibreChat not running; no Splunk AI Assistant required |
| Write incident report in browser | Offline Word passes; actual attachment, reload, download and second-LibreChat-user isolation untested |
| Injection resistance | Exactly two injection records exist; live model behavior not tested |
| Out-of-scope index denial | Role config supplied, but no service identity/runtime authorization test |
| REST unauthorized configuration denial | Must test actual app/Splunk permissions; tool hiding and prompt refusal are insufficient |
| Disabled tools | Candidate allowlist documented; actual installed discovery and direct-call denial unverified |
| Time/result/workload controls | Role settings supplied; app settings, hard 100-row cap, runtime/rate/concurrency/storage behavior unverified |
| Token issuance/30-day expiry | Operator has not issued service-identity encrypted MCP token; supported expiry fields unverified |
| App endpoint/TLS | Official endpoint documented; installed app endpoint, certificate and internal app CA trust untested |
| Trial activation/expiry | No instance initialized; actual activation and expiry **unknown**, expected duration 60 days only |
| Expiry consequences | Official restrictions documented; no runtime expiry experiment performed |
| Peak memory with Splunk/live browser tests | Only offline 1.686 GiB sample available; not representative of full demo |
| MSISDN masking | **Pending by design**; no masking or broader guardrails acceptance claimed |
| Lighthouse | Attempted `npm run lighthouse`; frontend prerequisite build stops at missing `rimraf` because `node_modules` is absent |
| Repository static checks | Attempted `npm run static-checks -- --against origin/dev`; local `origin/dev` reference is absent |
| CI/review at pushed head | Not run; no push requested or performed |

The source build also reported existing dependency warnings and an npm audit summary of five moderate
and one high vulnerability. No dependency versions were changed in this integration.

Image inspection found default user `ansible` (UID 999) and Ansible sudo escalation.
`no-new-privileges` was removed from the Splunk service to permit vendor bootstrap. The MTN config
app is generated as `private/mtn-demo.tgz` and installed alongside the official archive through
`SPLUNK_APPS_URL`, rather than bind-mounted read-only into the initialized application tree.
Compose validation and the preparation tests pass after this correction.

No failed runtime security test was observed because the runtime was unavailable. This does not
establish that the proposed security policy works. In particular, **100 default rows is not a hard
maximum**. A verified hard-row policy and REST denial are live release gates.

## Screenshots and Word artifact

All evidence below is local and gitignored. It contains only synthetic fixtures and safe status
metadata. Do not treat it as a successful live application acceptance record.

- [Rendered Word fixture](../../mtn/splunk/private/results/phoenix-offline-fixture.png) — visually inspected, six sections on one page; logo absent because licensed assets were not copied.
- [Blocked prerequisites in Chrome](../../mtn/splunk/private/results/acceptance-blocked.png) — screenshot of a local report, not the running app.
- [Word file](../../mtn/splunk/private/results/phoenix-offline-fixture.docx) and [PDF preview](../../mtn/splunk/private/results/phoenix-offline-fixture.pdf).
- [Word verification metadata](../../mtn/splunk/private/results/word-verification.json).
- [Preflight JSON](../../mtn/splunk/private/results/preflight.json) and [offline memory sample](../../mtn/splunk/private/results/memory-offline.json).

Final Word file: **39,452 bytes**, 1 page; downloaded resource and owner REST bytes match.
SHA-256 of the final recorded artifact:
`ac0e0d52a32b9d5b7c1746e9f975381d09d670d6c8bd82d7a7ef48d5c17f86fb`.
Word ZIP metadata/timestamps can change across regenerations; use `word-verification.json` for the
current artifact. Neither a browser download nor a live Splunk-sourced report has been verified.

## Operator handover and resume order

1. Download the compatible official app to the fixed private path and inspect its provenance;
   fill this worktree's `.env` with **new** values from [the setup guide](splunk-integration.md).
   Licence acceptance flags remain blank until you personally accept the applicable terms.
2. Run `prepare.py`; inspect recorded app version/hash and verify that release's 10.4 compatibility.
   Prepare CA trust for the app's own backend connection without disabling verification.
3. You start only this project's Splunk container to initialize any trial. Record actual licence
   activation/expiry in this handover. Do not switch to Splunk Free: its authentication/alerting
   restrictions break this demo's security contract.
4. In Splunk Web, verify the effective role, create `svc_mtn_assistant` with only that role, configure
   exact tool/command/rate settings and issue its encrypted token. Create the index-scoped HEC token.
   No agent script uses your Splunk admin credentials. Restart/reload only this project's Splunk if
   the app install requires it; do not change the existing project.
5. Build this branch under distinct demo image tags. Ingest once over internal HTTPS HEC; wait for
   indexing and replay alerts. Verify actual event counts and alert firing times.
6. Run real MCP discovery/negative and workload tests. Resolve the hard-row ceiling and REST
   authorization gates before starting the API. Do not expand permissions to make tests green.
7. Start the separate API/Mongo/Office stack, create synthetic LibreChat users, run every browser
   acceptance case, capture real application screenshots and verify attachment/reload/ownership.
8. Sample total VM memory during the full scenarios. If above about 6.5 GiB, recommend optional
   unrelated demo containers to the operator; do not stop them automatically. Re-run Lighthouse
   and scoped static checks after dependencies/base reference are available.

`splunk_run_saved_search` stays off. Phase 2 requires approval of a named allowlist and its
parameters, ACLs, indexes, workload and output limits. Production needs licensed deployment,
verified app/platform pairing, managed read-only identity and token/certificate rotation, narrow
network policy, enforced workload controls and approved data/model routing. No merge or push is
part of this handover.

## NVIDIA connectivity check

Added NVIDIA_API_KEY to the isolated API explicit environment and recreated only that service. The key remains private. NVIDIA models discovery returned HTTP 200 and listed nvidia/nemotron-3-ultra-550b-a55b. Completion requests returned HTTP 200, but the small output budget first ended in length; with thinking disabled a subsequent exact-answer test returned unrelated text. A forced synthetic function-call request ended without a structured tool call. These are failed model behavior checks, not a successful chatbot integration. Operations remains on Groq; no replacement model was silently selected. Original application containers were not recreated.

## NVIDIA replacement model checkpoint

Following operator direction to use NVIDIA, tested alternatives. Nemotron 3 Super and Llama 3.1 Nemotron 70B returned HTTP 404 despite discovery listings. NVIDIA nemotron-3.5-lightning-30b-a3b returned the exact synthetic answer, produced a structured check_connection call with the correct argument, and returned NVIDIA_TOOL_OK after the synthetic tool response (HTTP 200 for both round-trip requests). Operations now selects this NVIDIA model; schema validation passed and only isolated API restarted. Groq remains configured as an available provider. This is provider-level tool compatibility proof, not yet a real Splunk browser acceptance pass. Start a NEW Operations conversation to load the changed preset.

## NVIDIA context budget correction

Operator UI evidence showed attached tool definitions consume 6,428 tokens and total instructions 6,773, exceeding the inherited 6,000 Groq mitigation. That limit was inappropriate after switching to NVIDIA. Operations now sets maxContextTokens=24000 and max_tokens=2048; the full schema validation checks both exact settings. With the observed instruction count this provides approximately 17,227 tokens before response reservation and any additional skill overhead. Only the isolated API was restarted. Existing conversations may retain the old preset; create a new conversation and reselect Operations. This corrects local context admission but does not prove NVIDIA quota availability or full Splunk acceptance.

## Missing-tool diagnosis and recovery

Operator reported no final answer and model text claiming only Office tools were available. Direct tools/list from the live API confirmed HTTP 401: running MTN_SPLUNK_MCP_TOKEN was empty. Restored the previously issued token from private/provision-secrets.json into the blank local .env entry, with no Splunk token rotation. Verified TLS tools/list then returned HTTP 200 and exactly the eight approved Splunk tools. Compose now rejects a missing/empty MCP token. Prompt explicitly prohibits simulated execution and invented results/search IDs/timestamps when tools are unavailable.

The local .env also lacked CREDS_KEY, CREDS_IV, JWT_SECRET and JWT_REFRESH_SECRET; all four were empty in the recreated API. The stopped predecessor was no longer available to recover prior values. Initialized missing values only for this isolated synthetic demo; existing isolated sessions require login again, and any credentials encrypted with previous isolated keys may require re-entry. Original application settings/secrets/data were not changed. Docker recreation initially failed to observe container exit; stopping only the isolated API and retrying recovered it. Full browser query remains unverified at this checkpoint.

## Real NVIDIA chatbot connectivity PASS

A fresh browser login and new Operations conversation 56fb196c-886e-56b9-b785-bd47b4c872fd selected nvidia/nemotron-3.5-lightning-30b-a3b. Persisted assistant content includes a completed splunk_run_query_mcp_mtn-splunk call whose actual output contains Splunk connection works, followed by a final text answer with that result and the executed SPL under Searches used. One row, not truncated. Browser screenshot: private/results/nvidia-splunk-connectivity-passed.png. This verifies the narrow browser-to-model-to-official-MCP connectivity path after token recovery. The response inaccurately labels makeresults as index all/default; the command reads no index. Absolute time bounds were also omitted. Incident, security, workload and Word-report acceptance remain pending.

## Demo ingestion and discovery scope correction

Operator observed zero counts in the three demo indexes and 19 names from get_indexes. This was a genuine discovery metadata scope failure; disabled splunk_get_indexes using the official app policy. Expected catalog is now seven tools; admin.py and verify_mcp.py enforce it. Searchable-index role grants remain unchanged. Prompt now forbids recommending searches older than seven days or against other indexes, invented absolute dates, and describing makeresults as reading all indexes.

Enabled internal HTTPS HEC using the supported local REST configuration/enable endpoints, a private index-scoped token and the existing trusted certificate. The vendor bootstrap overrides app-local HTTP defaults on restart, so reapply HEC configuration after bootstrap before any future ingestion. No ingestion port was published. One seed execution was acknowledged: 90,731 events, 33,454,407 bytes, ending 2026-11-11T20:55:07.061223+00:00, fixed seed 7931, SHA256 092939707636fa179d069dc974399529d1bd3ca6916cdc208dfb66ca04c0caad. Do not blindly rerun and duplicate this dataset. Search-visible counts and authorization negatives are assessed separately.

### Post-ingestion read-only verification

Real MCP SDK evidence: private/results/post-ingest-mcp.json. Seven-tool catalog exact match passed. Search-visible rolling seven-day counts were phoenix_app=30245, phoenix_net=30240, phoenix_auth=30240 (90,725 total). Six oldest events had fallen outside the rolling window since generation; seed acknowledgment remains 90,731. Unauthorized index=_internal stats count returned count=0 and no event fields, not an explicit authorization error; this alone is not a complete proof of authorization denial. The rest /services/configs/conf-server attempt returned isError=true with a forbidden signal. No configuration payload was exposed by that test. Original ten application services remain running. Broader security, browser incident investigation, alerts and Word report acceptance remain pending.

## Native HTML artifacts — verified 2026-11-12

Operations was missing artifacts mode. Enabled artifacts: default and self-contained HTML/SVG/diagram guidance; max_tokens increased to 4096, maxContextTokens remains 24000. Existing document assistant modes, source renderer, iframe sandbox, Office file validation and TLS were preserved. Full configuration validation passes in the actual isolated image; only the isolated API restarted (completed during recovery). Docker subsequently reported all configured health checks healthy.

Real synthetic browser test on localhost:3081, conversation 63439946-c459-59bf-a08d-085aa02dbce1: the model produced a native text/html artifact titled MTN HTML Check; clicking the HTML card opened a rendered Sandpack preview; heading and Synthetic demo label visible; clicking Increment changed counter 0 to 1. Download Artifact produced MTN HTML Check.html (1112 bytes), including inline CSS/JS. Artifact card restored after full conversation reload. Screenshot was visually inspected. No Splunk or Office call was required for this visual-only request.

Evidence (gitignored): private/results/html-artifact-interactive.png, mtn-html-check.html and html-artifact-verification.json. These establish HTML rendering, interaction, download and conversation restoration for this case, not comprehensive React/SVG/Mermaid acceptance or live Splunk dashboard correctness. Generation was slow with model reasoning enabled. Sandpack preview still requires external CodeSandbox/Sandpack infrastructure; no offline preview claim. Lighthouse attempted, blocked by absent local dependencies/rimraf. No TypeScript source changed; no merge or push performed.

To use: refresh localhost:3081, start a new MTN Operations Assistant chat, and request a self-contained interactive HTML artifact. Click the HTML card to open Preview; Code allows inspection/editing and Download Artifact exports HTML. For a simple test ask for a counter with an Increment button, using illustrative data. Do not treat the native interactive page as a trusted Office HTML attachment or relax the Office active-content restrictions.
