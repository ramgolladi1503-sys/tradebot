# Agent Review Evidence — EDGE-51 Latest Artifact Freshness Runtime Wiring

mode: PAPER
candidate_id: EDGE-51-LATEST-ARTIFACT-FRESHNESS-RUNTIME-WIRING
decision: ADD_READ_ONLY_RUNTIME_SNAPSHOT_FRESHNESS_READER
reason: Runtime snapshot readers need freshness evidence before treating latest artifact envelopes as current runtime truth.
timestamp: 2026-05-24T10:41:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/EDGE_51_LATEST_ARTIFACT_FRESHNESS_RUNTIME_WIRING.md and tests/test_edge51_runtime_snapshot_freshness_wiring.py

## Contract

This PR adds an opt-in read helper only: `read_snapshot_with_freshness(...)`.

It keeps `read_snapshot(...)` unchanged.

## Scope Guard

- in_scope_list: runtime snapshot read helper, timestamp parsing, tests, docs, agent evidence
- out_of_scope_list: dashboard migration, runtime decision gating, artifact writer changes, strategy tuning, live behavior
- files_changed_list: core/runtime_snapshot_store.py, tests/test_edge51_runtime_snapshot_freshness_wiring.py, docs/EDGE_51_LATEST_ARTIFACT_FRESHNESS_RUNTIME_WIRING.md, docs/agent_reviews/edge_51_latest_artifact_freshness_runtime_wiring.md
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- dashboard_changed: false
- strategy_changed: false
- thresholds_changed: false

## Review Notes

Risk: changing the existing snapshot reader could break callers.
Decision: add a new helper and preserve the old function.

Risk: stale or invalid latest files can create false confidence.
Decision: the helper returns freshness status, blockers, and the original snapshot when readable.

Risk: this could become too broad.
Decision: this PR does not migrate dashboard readers or runtime gates.

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge51_runtime_snapshot_freshness_wiring.py
```

Expected: all EDGE-51 runtime snapshot freshness tests pass.
