# GSD Plan — Issue 11 persisted feed-truth ranking boundary

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Fail closed on stale persisted feed truth at ranking
**scope:** Execute only `docs/agent_reviews/issues_7_11_hermes_issue11_persisted_feed_truth_contract.md`.

## Files

- `core/feed_health_truth.py`: recognize the versioned runtime snapshot by stable signature; missing/invalid freshness or age is unknown and stale freshness blocks ranking. Preserve explicit legacy global/symbol contracts, including explicit-SLA-bound legacy LTP evidence.
- `config/feed_runtime_reliability.py`: add configurable snapshot maximum age (3.0 seconds by default).
- `tests/test_feed_runtime_reliability_config.py`: verify the default and environment override.
- `tests/test_feed_truth_snapshot_ranking_contract.py`: compose the real snapshot producer/file loader with the real ranking gate and exercise healthy, stale, malformed, contradictory, source-label, and timestamp states.
- `tests/test_runtime_status_overlay.py` and `tests/test_runtime_truth_integrity_live_path.py`: preserve explicit legacy health decision and runtime integrity behavior.
- `artifacts/issues_7_11/defect_graph_issue11_replay_addendum.json`: add producer-contract mismatch and repair/attack edges without promoting candidate-level isolation.
- `artifacts/issues_7_11/attack_ledger.jsonl` and `repair_ledger.jsonl`: record targeted attacks and verification evidence.
- `artifacts/issues_7_11/FINAL_VERDICT.json`: keep campaign and live verification open; update only the Issue 11 status and proof after current-source verification.

## Execution sequence

1. RED: add tests using `build_feed_truth_snapshot` output passed through `apply_feed_hold_to_ranking`.
2. Repair the classifier with a source-specific, fail-closed freshness check.
3. Run focused tests for the new integration test and existing feed-health/ranking regressions.
4. Attack: omit freshness/components, replace them with null/string, set stale while transport is connected, use unsupported/arbitrary/missing source labels, strip the freshness marker, contradict aggregate freshness with component fields, test empty/transport-only payloads, retain websocket/global blockers, and mutate out source recognition to confirm tests fail.
5. Verify authority flags, unchanged ranking policy, and no broker/order/runtime wiring changes.
6. Update evidence artifacts with exact commands and result; preserve unresolved candidate-level isolation as UNKNOWN.

## Forbidden changes

No feed producer edits, candidate filtering, strategy logic, token-universe changes, risk/freshness threshold changes, recovery/auth relaxation, broker/order calls, or paper/live authority changes.

## Acceptance

The actual persisted artifact cannot be interpreted as healthy when stale or when its freshness verdict is absent/invalid. Healthy artifacts still pass only when all existing safety checks pass. Candidate-level isolation remains UNKNOWN until exact fresh dependency identity reaches each candidate.

## Timestamp-age continuation (Hermes addendum)

The aggregate freshness flag describes producer-time state only. Also require legacy LTP/depth/option age values to be exact finite nonnegative JSON numbers; booleans, strings, negatives, NaN, and infinity fail closed. Add `FEED_TRUTH_SNAPSHOT_MAX_AGE_SEC` (default 3.0, aligned with the existing recovery-gap limit) to `config/feed_runtime_reliability.py`, verify the env override, and require a finite non-boolean `generated_epoch` within that age at classification time. Reject future, absent, malformed, or over-age snapshots. Do not change LTP/option thresholds. Test each boundary with controlled time and retain the full existing ranking/global safety regression.


## Rollout notes

No runtime restart or live rollout is authorized by this offline repair. The new `FEED_TRUTH_SNAPSHOT_MAX_AGE_SEC` defaults to 3.0 seconds. A future controlled rollout must confirm the configured writer/consumer cadence is within this bound; operators may override the environment value only from measured runtime cadence and must keep stale/missing/future snapshot handling fail-closed.
