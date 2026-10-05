# Agent Review: PR #962 Live Session RCA Fixes

## Agent Work Contract

- `source_agent`: grill_me -> hermes -> gsd
- `action`: `CRITIQUE_SCOPE`, `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `PLAN_PR`, `GENERATE_TESTS`, `GENERATE_PATCH`, `FIX_TEST_FAILURE`
- `title`: Preserve feed truth and persistence drain accounting
- `scope`: Correct source-vs-receipt freshness evidence, per-symbol option diagnostics, recovery classification, tick post-commit accounting, persistence failure telemetry, and shared-deadline drain reporting.
- `requested_paths`: `core/feed/runtime_store.py`, `core/feed_forensics.py`, `core/kite_depth_ws.py`, `core/kite_read_only_observation_runtime.py`, `core/tick_store.py`, and focused tests.
- `allowed_paths`: Those production modules, focused tests, and this review record.
- `forbidden_paths`: Broker/order/execution actions, credentials, live configuration, risk/freshness gate weakening, strategy thresholds, dashboard work, runtime restarts, and unrelated files.
- `expected_tests`: Focused feed, forensic, tick-store, runtime-store, and lifecycle tests; hosted exact-head CI.
- `acceptance_proof`: Explicit tests for fresh source and receipt timestamps, no duplicate retry after durable commit, unique-row accounting, redacted failure categories, latest recovery outcome, and a single monotonic shutdown deadline. Execution readiness remains fail-closed.

## Scope Guard

This PR repairs evidence and persistence lifecycle correctness from the 2026-10-05 observation. It keeps global recovery and execution readiness gates authoritative. Per-symbol measurements no longer get rewritten to hide what was observed. A durable insert is not retried because a later WAL checkpoint failed. Shutdown is incomplete when its shared deadline expires or accepted rows do not reconcile. No broker/order authority is introduced.

## Grill Me Review

The live capture does not contain `tick_store_errors.jsonl`; the 80 tick worker failures therefore have no proven underlying SQLite or storage cause. The 4,334-row residual is confirmed, while the old `in_flight_rows` value counts retries and overstates unique work. The 18.98-million-ms runtime writer lag used an enqueue timestamp retained through coalescing and is not evidence of a continuous five-hour stall. This PR improves future evidence and corrects these counters; it does not invent the missing cause or claim the observed feed was healthy.

## Hermes Review

Contracts: raw source time and callback receipt time are distinct authorities; both must be finite, non-future, fresh, and identity-matched for underlying health. A successful recovery classification requires the latest recovery outcome to explicitly be `RECOVERED`. Durable tick rows are accounted exactly once even if checkpoint maintenance degrades. Persistence drain completion requires reconciled accepted/committed/queued/in-flight counts within one shared monotonic deadline. Unknown, incomplete, or stale evidence remains blocked.

## GSD Review

Implementation is limited to the five listed runtime modules, six focused test files, and this review artifact. No configuration key or default is added. Storage exceptions are classified by safe category/type and omit exception messages, tick values, tokens, credentials, and row payloads. The tick checkpoint degradation remains visible and does not relax readiness.

## QA / Safety Review

### High-Risk Path Review

`core/kite_depth_ws.py` and `core/feed/runtime_store.py` are feed paths. The changes preserve fail-closed global execution readiness and do not change broker adapters, order behavior, strategy thresholds, freshness thresholds, kill switches, or live-mode configuration. `core/kite_read_only_observation_runtime.py` only tightens shutdown budget accounting. `core/tick_store.py` prevents replay after a durable commit and reports failures without payload data. No live process was restarted or modified; no broker or order API was called.

- Focused feed/persistence/lifecycle tests: 160 passed.
- Feed health/recovery/readiness and persistence-bound tests: 86 passed.
- `git diff --check`: passed.
- Exact-head hosted CI: not yet green; PR818 frozen-live-flow policy currently rejects changes under its protected production surface, and review evidence was initially missing. The review-evidence requirement is addressed by this file. The freeze policy is not waived or bypassed here.

## Acceptance Proof

The local tests prove that a fresh receipt cannot mask stale, missing, future, or non-finite source time; checkpoint failure after commit does not enqueue duplicate rows; failure events contain only redacted categories/types; retry attempts do not inflate unique pending/in-flight accounting; status `PROGRESS` is not classified as recovered; and shutdown recomputes each worker budget from one monotonic deadline while requiring tick/depth/runtime accounting to reconcile. Hosted acceptance still requires every required exact-head check to pass under the repository's protected live-flow policy.

## Runtime Proof Required After Merge

A future read-only observation must verify that the new source/receipt fields agree with MEG's source-bar age, tick persistence reports the pre-commit failure category if one recurs, runtime oldest-pending age is distinct from service wait, and shutdown drains all accepted work. A fresh session must independently demonstrate feed health. No live execution authorization is implied.

## What This PR Does Not Prove

It does not identify the missing 80 tick-store failure causes, prove sustainable depth-write throughput, recover the 2026-10-05 session, certify MEG source-bar progress, establish a strategy edge, prove live readiness, or authorize paper/live orders. The PR818 protected-surface check remains an independent required policy gate.

## Human Approval

The user explicitly authorized offline fixes, opening a PR, and merging only after CI is green. This authorization does not permit disabling a CI gate, using admin/force merge, changing broker credentials, performing order actions, or restarting the observed live process. Any protected live-flow recertification must follow the repository's governed procedure and remain fail-closed.
