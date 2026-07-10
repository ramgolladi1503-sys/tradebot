# Feed Integrity and Health Duration

mode: CHECK
candidate_id: FEED-INTEGRITY-AND-HEALTH-DURATION
decision: APPROVE
reason: feed integrity and health duration evidence package
timestamp: 2026-07-10T21:37:39+05:30
is_order_action: false
broker_api_called: false
source: Codex

## Agent Work Contract
- source_agent: Codex
- action: generate_patch
- title: Add transport heartbeat, cycle-truth checksum, and health-duration monitoring
- scope: Feed runtime artifacts, runtime health, snapshot production, and read-only evidence checks only
- requested_paths:
  - core/feed/ws_lifecycle_shell.py
  - core/feed/runtime_snapshot_builder.py
  - core/feed/runtime_store.py
  - core/feed_debug.py
  - core/runtime_feed_truth_snapshot.py
  - core/runtime_health.py
  - core/runtime_snapshot_producer.py
  - core/runtime_snapshot_stages.py
  - core/runtime_truth_integrity.py
  - core/jsonl_tail_cache.py
  - core/feed_health_duration.py
  - scripts/monitor_feed_health_duration.py
  - tests/core/test_runtime_snapshot_producer.py
  - tests/test_feed_health_duration.py
  - tests/test_feed_runtime_states.py
  - tests/test_pr_feed_11_runtime_snapshot_builder.py
  - tests/test_runtime_health.py
- allowed_paths:
  - core/feed/*
  - core/runtime_*.py
  - core/jsonl_tail_cache.py
  - scripts/monitor_feed_health_duration.py
  - tests/*
- forbidden_paths:
  - core/broker/*
  - core/order/*
  - core/risk/*
  - credentials.py
  - .env
  - runtime/live*
- expected_tests:
  - python -m py_compile core/runtime_truth_integrity.py core/feed/runtime_snapshot_builder.py core/feed/runtime_store.py core/runtime_feed_truth_snapshot.py core/runtime_snapshot_stages.py core/feed_debug.py core/runtime_health.py core/feed/ws_lifecycle_shell.py core/runtime_snapshot_producer.py core/jsonl_tail_cache.py core/feed_health_duration.py scripts/monitor_feed_health_duration.py
  - pytest -q tests/test_runtime_health.py tests/test_pr_feed_11_runtime_snapshot_builder.py tests/test_feed_runtime_states.py
  - pytest -q tests/core/test_runtime_snapshot_producer.py tests/test_feed_health_duration.py
- acceptance_proof: The feed stack emits a transport heartbeat, a canonical snapshot hash, and explicit alerts when transport state, feed truth state, or snapshot hash disagree.

## Scope Guard
- Feed-only change.
- No broker, order, risk-threshold, or execution logic was modified.
- The new monitoring paths are read-only and fail closed.

## Grill Me Review
- PASS: No live trading behavior was changed.
- PASS: The checksum is derived from canonical JSON, not ad hoc string concatenation.
- PASS: Alerts surface mismatches instead of masking them.

## Hermes Review
- PASS: Transport health is represented explicitly.
- PASS: Canonical cycle truth is shared through one immutable payload.
- PASS: Hot-path JSONL reads use a bounded tail cache.

## GSD Review
- PASS: Tests cover snapshot propagation, runtime health alerting, and health-duration monitoring.
- PASS: New helper modules are isolated and import-safe.
- PASS: Validation commands were run before publish.

## QA / Safety Review
- PASS: No order placement or broker API usage.
- PASS: No feed freshness gate weakening.
- PASS: No silent fallback to fake success.
- PASS: Any checksum or transport mismatch is reported as an alert.

## Acceptance Proof
- `python -m py_compile ...`
- `pytest -q tests/test_runtime_health.py tests/test_pr_feed_11_runtime_snapshot_builder.py tests/test_feed_runtime_states.py`
- `pytest -q tests/core/test_runtime_snapshot_producer.py tests/test_feed_health_duration.py`

## Runtime Proof Required After Merge
- Confirm `feed_runtime_latest.json` includes `transport_state`, `transport_heartbeat`, `snapshot_hash`, and `truth_integrity_alerts`.
- Confirm `feed_health_duration_latest.json` advances the healthy-duration counter only while the runtime snapshot remains healthy.
- Confirm `runtime_truth_integrity_alert` is emitted when snapshot hash or state mismatches are detected.

## What This PR Does Not Prove
- It does not prove market edge, profitability, or strategy alpha.
- It does not prove live broker execution.
- It does not prove the feed will remain healthy for one hour in production without observing live runtime evidence.

## Human Approval
- Approved for feed-only publication review.
