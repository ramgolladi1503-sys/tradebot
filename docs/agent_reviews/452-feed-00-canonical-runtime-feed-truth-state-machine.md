# FEED-00 — Canonical Runtime Feed Truth State Machine

mode: LIVE
candidate_id: FEED-00-canonical-runtime-feed-truth-state-machine
decision: add_canonical_feed_truth_execution_contract
reason: Add strict feed truth artifacts and one fail-closed feed execution boolean so executable candidate paths can consume canonical LIVE-only feed truth.
timestamp: 2026-05-29T17:18:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/452-feed-00-canonical-runtime-feed-truth-state-machine.md

## Agent Work Contract
Implement Issue #452 only: FEED-00 — Canonical Runtime Feed Truth State Machine. Keep the change read-only and feed-truth scoped.

## Scope Guard
In scope:
- Add a pure helper that treats only canonical `LIVE` feed truth as allowing executable candidate selection.
- Publish canonical feed truth and strict execution booleans to both `logs/feed_runtime_latest.json` and `.runtime/feed_runtime_latest.json` through the runtime feed snapshot store.
- Add deterministic tests proving fail-closed behavior and required artifact fields.

Out of scope:
- Ranking weights.
- Strategy logic.
- Dashboard/UI.
- Broker calls.
- Live order behavior.
- TB-EDGE-01 and later stories.

## Grill Me Review
Risk checked: ticker object, websocket object, or process-alive evidence must not imply LIVE. The helper returns true only for canonical `LIVE`; all other states are false.

## Hermes Review
Runtime artifact evidence remains machine-readable JSON. The new fields are explicit:
- `feed_truth_allows_live_selection`
- `feed_truth_allows_executable_candidates`
- `feed_execution_truth_schema_version`
- read-only safety fields

## GSD Review
The patch is intentionally small. It reuses the existing `core.feed_truth_state.classify_feed_truth_state` classifier instead of creating a parallel feed-health system.

## QA / Safety Review
Tests prove:
- only LIVE allows executable selection;
- required runtime artifacts are written;
- no-tick feed evidence fails closed;
- artifacts are read-only and non-order-action.

## Acceptance Proof
Planned commands:

```bash
python -m py_compile core/feed_execution_truth.py core/feed/runtime_store.py core/kite_depth_ws.py core/runtime_health.py core/readiness_gate.py
PYTHONPATH=. python -m pytest -q tests/test_feed_00_canonical_feed_truth.py
PYTHONPATH=. python -m pytest -q tests/test_feed_runtime_states.py
PYTHONPATH=. python -m pytest -q tests/test_feed_debug.py
PYTHONPATH=. python -m pytest -q tests/test_readiness_gate.py
```

## Runtime Proof Required After Merge
During the next live run, inspect:

```bash
cat logs/feed_runtime_latest.json | jq '{feed_truth_state, feed_truth_allows_executable_candidates, feed_truth_reason_code, feed_truth_reasons}'
cat .runtime/feed_runtime_latest.json | jq '{feed_truth_state, feed_truth_allows_executable_candidates, feed_truth_reason_code, feed_truth_reasons}'
```

Expected: only `feed_truth_state == "LIVE"` can show `feed_truth_allows_executable_candidates == true`.

## What This PR Does Not Prove
It does not prove ranking has edge, Phase2 data is strict, fallback execution is killed in LIVE, or strategy expectancy is positive. Those remain later TB-EDGE stories.

## Human Approval
Human approval is required before merge. Do not start TB-EDGE-01 until FEED-00 is merged.
