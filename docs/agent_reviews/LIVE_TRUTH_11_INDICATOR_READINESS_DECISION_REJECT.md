# Agent Review — LIVE-TRUTH-11 Indicator Readiness Decision Reject Evidence

mode: PAPER
candidate_id: LIVE-TRUTH-11-INDICATOR-READINESS-DECISION-REJECT
source: agent_review_live_truth_11_indicator_readiness_decision_reject
reason: production decision reject evidence is written when blocker is INDICATORS_MISSING
timestamp: 2026-05-29T05:20:00Z
decision: APPROVED
is_order_action: false
broker_api_called: false

## Verdict

PASS — narrow production-path evidence wiring.

## Scope Reviewed

This PR wires existing indicator-readiness evidence into the post-decision side-effect hook used by production orchestrator flow.

Reviewed files:

- `core/decision_side_effects.py`
- `tests/test_live_truth_11_indicator_readiness_decision_side_effect.py`
- `docs/LIVE_TRUTH_11_INDICATOR_READINESS_DECISION_REJECT.md`

## Problem Confirmed

Live evidence showed repeated `INDICATORS_MISSING` decisions while `.runtime/live_indicator_readiness_latest.json` was absent.

The helper existed in `core/live_indicator_readiness.py`, but it was not connected to the production decision reject path.

## Design Review

The implementation keeps the pure Decision DAG side-effect free and adds the runtime evidence write inside `handle_post_decision_side_effects(...)`, which is already called by orchestrator immediately after production decision evaluation.

The side-effect uses only already-computed facts from:

- `DecisionReport.blockers`
- `DecisionReport.explain`
- `MarketSnapshot`
- `MarketSnapshot.raw_data`

## Safety Review

Confirmed boundaries:

- Decision DAG logic unchanged.
- Strategy logic unchanged.
- Candidate generation unchanged.
- Ranking unchanged.
- Thresholds unchanged.
- Dashboard unchanged.
- Reconnect behavior unchanged.

The evidence writer is best-effort. Writer failure does not alter the already-computed decision path.

## Test Evidence

Focused test command:

```bash
PYTHONPATH=. python -m pytest -q tests/test_live_truth_11_indicator_readiness_decision_side_effect.py
```

Tests prove:

1. Indicator-missing decision writes `.runtime/live_indicator_readiness_latest.json`.
2. Non-indicator reject does not write the artifact.
3. Writer failure is side-effect safe.
4. Allowed decision does not write the artifact.

## Regression Risk

Low.

The change is isolated to post-decision evidence and does not change gate decisions, candidate flow, or execution behavior.

## Final Review Decision

Approved.
