# Upstream proposal: expose the custom classifier's verdict as routing evidence

**Project:** NVIDIA NeMo Switchyard (Apache-2.0) · **Applies to:** `v0.3.0` (`336196f6`) ·
**MTN status:** carried as a local build-time patch for the model router demo only
(`mtn/router/switchyard/patches/0001-custom-verdict-evidence.patch`).

## Problem

With `type = "llm_classifier"` and `mode = "custom"`, a route can choose between any number of
model groups, and the judge's response schema is defined by the operator. A host can see *which*
model served a turn (the `x-model-router-selected-model` header, the routing log, metrics), but not
*why*:

- Capability mode records evidence (`source`, `score`, `threshold`), but custom mode records none
  in `v0.3.0` (`main` records only `{"source": "llm-classifier"}`).
- The verdict is not logged, not in the routing log, and not in `/v1/stats`.
- The standalone server never returns outcome evidence to the caller.

For a demo or an audit ("why did this go to the expensive model?"), the operator-defined verdict,
for example a short `reason` field, is exactly the explanation needed, and it is already parsed
and schema-validated by Switchyard.

## Design (what the MTN patch does)

1. **libsy (`crates/libsy/src/algorithms/llm_class.rs`).** `build_custom` enables evidence for the
   custom judge with a new `custom_evidence` function. It records the validated verdict:
   `{"source": "llm-classifier", "verdict": <verdict>}`. A verdict larger than 1 KiB is replaced by
   `{"source": "llm-classifier", "verdict_omitted": "too_large"}`, so evidence stays bounded. Enabling
   evidence also turns on the existing fail-open evidence (`{"source": "fail_open", "reason_code": …}`)
   for custom judges, as capability mode already has.
2. **switchyard-server (`crates/switchyard-server/src/lib.rs`).** The per-request run observer also
   captures `RunObservation::Outcome(metadata).evidence`. After the existing
   `x-model-router-selected-model` header, the server adds `x-switchyard-route-evidence`: compact
   JSON with non-ASCII characters escaped (`\uXXXX`), so the value is header-safe and still valid
   JSON. Evidence longer than the existing 512-character routing-header limit is left out rather
   than truncated. No new dependency; `Cargo.lock` is unchanged.

The operator controls what the verdict contains through `response_schema`. MTN's route asks for
`{"decision": {"target": "fast|balanced|capable", "reason": "<= 12 words"}}`.

### Privacy note

The verdict is produced by the judge about the user's request, so it can paraphrase the request.
It never contains the request itself unless the operator's schema asks for it. Hosts that should
not reveal it can simply not request a `reason` field; a configuration switch to disable the
header (`expose_route_evidence = false`) would be a reasonable upstream addition.

## Tests (in the patch)

| Test | What it proves |
|---|---|
| `custom_evidence_tests::custom_evidence_records_the_validated_verdict` | The verdict is recorded with `source = llm-classifier`. |
| `custom_evidence_tests::custom_evidence_summarizes_oversized_verdicts_and_skips_missing_ones` | Verdicts over 1 KiB are summarized; no verdict means no custom evidence. |
| `route_evidence_header_tests::evidence_header_is_ascii_json_that_round_trips` | Non-ASCII reasons are escaped; the header parses back to the same JSON. |
| `route_evidence_header_tests::oversized_evidence_is_left_out` | Evidence beyond the header limit is omitted, never truncated. |

Run with `docker build --target test mtn/router/switchyard`. End to end (MTN demo stack): a greeting
returned `x-switchyard-route-evidence: {"source":"llm-classifier","verdict":{"decision":{"reason":"Short greeting","target":"fast"}}}`.

## Open questions for upstream

- Should evidence also be written to the routing log (`outcome` field, as `main` does for some
  algorithms) and exposed in `/v1/routing/session-stats`?
- Header vs. a response body extension (for example `switchyard.route` in the final chunk) for
  clients that cannot read headers.
- A route-level switch to disable exposing evidence.

## Related limitation (not part of this patch)

In `v0.3.0`, a routing-time judge call uses only the first `models.judge` entry, and a client error
or timeout stops the request instead of falling back. MTN works around it outside Switchyard:
router-lens retries the turn once on a second route whose judge is a different model. Ordered
judge fallback inside Switchyard would remove that workaround.
