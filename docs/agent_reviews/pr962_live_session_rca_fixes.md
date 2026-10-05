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

The failing session is SHA-bound by `presession_manifest.json` and `process_identity.json` to producer `ff2504830cb7c68eab5d3dfcae77daa5809469a3`. Its preserved `logs/tick_store_errors.jsonl` contains 82 records: two schema confirmations and 80 `TICK_STORAGE_BOUND_REJECTED` records. All 80 rejection records name `SQLITE_WAL_CHECKPOINT_BUSY`; their batches total 78,297 rows. The shutdown counters report 491,932 rows dequeued and 413,635 enqueued, also a delta of 78,297. This reconciles the complete set of failed batches with retry dequeues. The durable tick insert happened before the checkpoint; the prior path treated the subsequent busy checkpoint as an unsuccessful insert, so retrying wrote those rows through again. The PR changes post-commit checkpoint failure to degraded-but-committed accounting, preventing that duplicate-write path while keeping checkpoint trouble visible. The aggregate counters and current preserved database were insufficient to prove the exact number of duplicate rows, so this review does not claim that number.

The preserved depth rejection log contains 183,085 records; all are `QUEUE_REJECTED` at queue depth 65,536. The first is at 09:33:49 IST and the last at 15:30:02 IST. Captured shutdown accounting reports zero depth DB failures and zero lock skips, while 47,245 rows were persisted and 65,536 remained queued. This confirms sustained producer/service-rate imbalance and queue saturation. It does not identify why the persistence worker's service rate was insufficient; do not attribute this to SQLite lock contention from the available evidence.

The 4,334-row tick residual is confirmed, while the old `in_flight_rows` value counts retries and overstates unique work. The 18.98-million-ms runtime writer lag used an enqueue timestamp retained through coalescing and is not evidence of a continuous five-hour stall. The PR improves future evidence and corrects these counters; it does not claim the observed feed was healthy.

### Adjacent Readiness Findings (Not Fixed by This PR)

The same session has no verified prior-run interval. Its process start is 09:19 IST, after the 09:15 primitive's two-second admissibility window; the persisted primitive is terminally `BLOCKED`/`EXPIRED_NO_CURRENT_CAPTURE`. The 10:00 primitive is also `BLOCKED`, but its source timestamp and rejected-field reason were not preserved, so its specific cause remains unknown. All 8,348 strategy observations are `UNKNOWN` with `CAS_PRIMITIVE_0915_INVALID`; the candidate and executable pools are empty. This is fail-closed behavior and does not imply an edge. Repair requires a separately scoped pre-session readiness and diagnostic change; this PR does not alter the CAS or strategy contract.

The recorded MEG traversal rejection reasons include `SNAPSHOT_STALE` (181), `INDEX_INTERVAL_MISALIGNED` (54), `SNAPSHOT_SOURCE_TICK_STALE` (20), `BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION` (13), and `MISSING_POST_REQUEST_TICK` (7). These point to stale or misaligned inputs and incomplete live-consumer coverage, but the preserved events do not establish a single common cause. The zero-length candidate and executable pool artifacts confirm no candidate output was produced.

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
- Exact-head hosted CI: not yet green. The PR818 frozen-live-flow policy rejects the protected production changes and reports base drift from its pinned baseline. The PR782 focused-contracts gate also rejects changed files outside its designated scope. This evidence is from the live check logs; neither gate is waived or bypassed.

## Acceptance Proof

The local tests prove that a fresh receipt cannot mask stale, missing, future, or non-finite source time; checkpoint failure after commit does not enqueue duplicate rows; failure events contain only redacted categories/types; retry attempts do not inflate unique pending/in-flight accounting; status `PROGRESS` is not classified as recovered; and shutdown recomputes each worker budget from one monotonic deadline while requiring tick/depth/runtime accounting to reconcile. Hosted acceptance still requires every required exact-head check to pass under the repository's protected live-flow policy.

## Runtime Proof Required After Merge

A future read-only observation must verify that the new source/receipt fields agree with MEG's source-bar age, tick persistence reports the pre-commit failure category if one recurs, runtime oldest-pending age is distinct from service wait, and shutdown drains all accepted work. A fresh session must independently demonstrate feed health. No live execution authorization is implied.

## What This PR Does Not Prove

It does not prove how many duplicate tick rows were committed during the observed session, identify the depth persistence throughput bottleneck, prove sustainable depth-write throughput, recover the 2026-10-05 session, certify MEG source-bar progress, establish a strategy edge, prove live readiness, or authorize paper/live orders. The PR818 protected-surface check remains an independent required policy gate.

## Human Approval

The user explicitly authorized offline fixes, opening a PR, and merging only after CI is green. This authorization does not permit disabling a CI gate, using admin/force merge, changing broker credentials, performing order actions, or restarting the observed live process. Any protected live-flow recertification must follow the repository's governed procedure and remain fail-closed.
