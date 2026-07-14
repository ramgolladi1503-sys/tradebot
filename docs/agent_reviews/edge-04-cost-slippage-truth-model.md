# PR-EDGE-04 — Cost and Slippage Truth Model

mode: REVIEW
candidate_id: PR-EDGE-04-COST-SLIPPAGE-TRUTH-MODEL
decision: add_cost_and_slippage_truth_model
reason: Add a deterministic, read-only cost and slippage model for runtime candidate outcome truth without changing ranking, strategy, broker, order, websocket, or dashboard behavior.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge-04-cost-slippage-truth-model.md

## Agent Work Contract
- source_agent: Codex
- action: implement_read_only_truth_model
- scope: deterministic cost/slippage model for candidate outcome truth
- requested_paths:
  - core/cost_slippage_model.py
  - core/candidate_outcome_tracker.py
  - tests/test_cost_slippage_model.py
  - tests/test_candidate_outcome_tracker.py
  - tests/test_candidate_outcome_truth.py
  - docs/agent_reviews/edge-04-cost-slippage-truth-model.md
- allowed_paths:
  - core/cost_slippage_model.py
  - core/candidate_outcome_tracker.py
  - tests/test_cost_slippage_model.py
  - tests/test_candidate_outcome_tracker.py
  - tests/test_candidate_outcome_truth.py
  - docs/agent_reviews/edge-04-cost-slippage-truth-model.md
- forbidden_paths:
  - broker/order code
  - live order behavior
  - strategy logic
  - ranking/scoring
  - Phase 2 behavior
  - websocket/feed lifecycle
  - dashboard/UI behavior
- expected_tests:
  - PYTHONPATH=. pytest -q tests/test_cost_slippage_model.py tests/test_candidate_outcome_tracker.py tests/test_candidate_outcome_truth.py -vv
  - PYTHONPATH=. pytest -q tests/test_candidate_journal.py -vv
  - python scripts/validate_agent_review_evidence.py
  - git diff --check
- acceptance_proof:
  - read-only model and tracker outputs are deterministic
  - missing bid/ask degrades safely instead of crashing
  - invalid risk per unit fails closed
  - cost-adjusted R uses gross R minus estimated cost R
  - no broker/order imports or runtime execution wiring were added

## Scope Guard
- This PR adds a pure cost/slippage model and enriches outcome-tracker evidence only.
- It does not change strategy selection, ranking, execution routing, or live trading behavior.
- It does not add expectancy aggregation or any kill/keep gate.

## Grill Me Review
- The model must never become a hidden execution-policy layer.
- The tracker must not start inferring trades or mutating runtime state.
- Missing quote data must remain visible as degraded/blocked evidence.

## Hermes Review
- `core/cost_slippage_model.py` is a pure deterministic helper with explicit blockers and warnings.
- `core/candidate_outcome_tracker.py` only enriches candidate outcome records when enough data exists.
- `core/candidate_outcome_truth.py` remains the source of outcome classification.

## GSD Review
- Added deterministic tests for tight spread, wide spread, degraded quote data, invalid risk, and safe import boundaries.
- Added tracker regression coverage for propagated cost-model fields.
- Added outcome-truth coverage showing high costs can make net R negative.

## QA / Safety Review
- read_only=true
- append=false for truth objects
- is_order_action=false
- broker_api_called=false
- live_order_allowed=false
- live_order_action=false
- broker_order_action=false
- No broker API calls are introduced.
- No live orders are introduced.
- No websocket changes are introduced.

## Cost Model Formula
- `spread_cost_abs = max(spread, ask - bid, spread_pct-derived spread) * position_units`
- `slippage_cost_abs = slippage_ticks * tick_size * position_units * 2`
- `fee_cost_abs = max(brokerage, 0) + max(taxes, 0)`
- `estimated_cost_abs = spread_cost_abs + slippage_cost_abs + fee_cost_abs`
- `estimated_cost_r = estimated_cost_abs / risk_per_unit` when `risk_per_unit > 0`
- `effective_entry` and `effective_exit` are adjusted conservatively by side/direction and slippage

## Acceptance Proof
- `tests/test_cost_slippage_model.py` proves:
  - tight spread cost stays small
  - wide spread increases cost
  - missing bid/ask degrades safely
  - invalid risk blocks safely
  - no broker/order imports exist
- `tests/test_candidate_outcome_tracker.py` proves:
  - tracker rows carry cost-model fields
  - candidate outcome truth remains read-only
  - write failure remains non-fatal
- `tests/test_candidate_outcome_truth.py` proves:
  - cost-adjusted R can fall below zero when cost is high enough

## Runtime Proof Required After Merge
- The tracker remains read-only and append-only evidence only.
- No live runtime wiring is required for this PR to be valid.
- Any future runtime consumer must continue to fail closed on missing data.

## What This PR Does Not Prove
- It does not prove live profitability.
- It does not prove execution quality.
- It does not prove strategy edge.
- It does not prove slippage assumptions are accurate in live markets.

## Human Approval
- This PR stays within the agreed read-only scope and does not require live order approval.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
