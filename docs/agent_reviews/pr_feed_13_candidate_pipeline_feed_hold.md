# Agent Review Evidence — PR-FEED-13 Candidate Pipeline Feed Hold

## Agent Work Contract

### Goal

Wire canonical feed-health truth into the ranked opportunity pipeline using the existing feed-hold gate.

### Files changed

- `core/ranking_orchestrator.py`
- `tests/test_ranking_orchestrator.py`
- `docs/PR_FEED_13_CANDIDATE_PIPELINE_FEED_HOLD.md`
- `docs/agent_reviews/pr_feed_13_candidate_pipeline_feed_hold.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: PR_FEED_13_CANDIDATE_PIPELINE_FEED_HOLD
decision: READ_ONLY_PIPELINE_FEED_HOLD_INTEGRATION
reason: Ranked opportunity reports can now consume canonical feed-health truth before candidate ranking output is trusted.
timestamp: 2026-05-25T07:26:40Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr_feed_13_candidate_pipeline_feed_hold.md

### Non-goals

- No feed lifecycle changes.
- No reconnect logic.
- No resubscribe logic.
- No token-selection changes.
- No strategy changes.
- No dashboard UI changes.
- No threshold tuning.

## Grill Me Review

### Pushback

A standalone feed-hold contract is not enough if the ranking orchestrator never consumes it. The pipeline must make feed truth visible at the point where ranked candidates are produced.

### Required proof

- Legacy behavior remains unchanged when feed truth is not provided.
- Healthy feed truth preserves ranked output.
- Unhealthy feed truth holds ranking output.
- Pipeline metadata exposes feed-hold status.

## Hermes Review

### Contract clarity

The new `feed_health` argument is optional and backward-compatible. Existing callers that do not provide feed truth keep the same path.

### Serialization

The report remains JSON serializable through existing report `to_dict()` and `to_json()` methods.

## GSD Review

### Minimality

This PR changes the orchestrator seam only. It reuses `apply_feed_hold_to_ranking(...)` instead of creating another feed policy.

### Determinism

Tests use fixed candidate, regime, and feed-health payloads.

## QA / Safety Review

Tests assert:

- `feed_health_input_present=false` for legacy path.
- unhealthy feed truth produces zero ranked count.
- unhealthy feed truth produces zero executable count.
- healthy feed truth preserves top-ranked candidate.
- feed-hold metadata appears when active.

## Scope Guard

Confirmed not touched:

- Feed lifecycle.
- Reconnect/resubscribe behavior.
- Token selection.
- Strategy code.
- Dashboard UI.
- Threshold tuning.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_ranking_orchestrator.py tests/test_pr_feed_03_feed_hold_gate.py
```

Expected:

- ranking orchestrator tests pass.
- feed-hold gate tests pass.

## Runtime Proof Required After Merge

After merge, capture a paper-mode runtime candidate-cycle sample proving:

- `feed_health_input_present=true` when feed truth is supplied.
- `feed_hold_active=true` when feed truth is unsafe.
- unsafe feed truth produces zero ranked output.
- healthy feed truth preserves normal ranking behavior.
- no feed lifecycle or strategy behavior changed.

## What This PR Does Not Prove

- It does not prove websocket recovery.
- It does not prove token resolver correctness.
- It does not prove strategy edge.
- It does not prove dashboard rendering.

## Human Approval

Proceed only if CI is green and the PR remains limited to ranked pipeline feed-hold integration.
