# EDGE-05 — Strategy-Regime Expectancy Aggregator

mode: REVIEW
candidate_id: EDGE-05-STRATEGY-REGIME-EXPECTANCY-AGGREGATOR
decision: add_strategy_regime_expectancy_aggregator
reason: Add a deterministic, read-only expectancy aggregator over candidate outcome truth without changing ranking, strategy, broker, order, websocket, or UI behavior.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge-05-strategy-regime-expectancy-aggregator.md

## Agent Work Contract

- source_agent: Codex
- action: implement_read_only_expectancy_aggregation
- scope: deterministic strategy/regime expectancy aggregation from candidate outcome records
- requested_paths:
  - core/expectancy/__init__.py
  - core/expectancy/strategy_regime_expectancy.py
  - tests/test_strategy_regime_expectancy.py
  - tests/test_candidate_outcome_tracker.py
  - tests/test_cost_slippage_model.py
  - docs/agent_reviews/edge-05-strategy-regime-expectancy-aggregator.md
- allowed_paths:
  - core/expectancy/__init__.py
  - core/expectancy/strategy_regime_expectancy.py
  - tests/test_strategy_regime_expectancy.py
  - tests/test_candidate_outcome_tracker.py
  - tests/test_cost_slippage_model.py
  - docs/agent_reviews/edge-05-strategy-regime-expectancy-aggregator.md
- forbidden_paths:
  - setup fingerprinting
  - kill/keep runtime gate
  - ranking changes
  - strategy changes
  - broker/order changes
  - dashboard/UI changes
- expected_tests:
  - PYTHONPATH=. pytest -q tests/test_strategy_regime_expectancy.py -vv
  - PYTHONPATH=. pytest -q tests/test_candidate_outcome_tracker.py tests/test_cost_slippage_model.py -vv
  - python scripts/validate_agent_review_evidence.py
  - git diff --check
- acceptance_proof:
  - groups are deterministic and sorted by normalized group key
  - fallback outcomes are excluded from executable expectancy
  - NOT_EXECUTABLE is counted separately from blocked rows
  - thresholds produce INSUFFICIENT_DATA, WATCH, KEEP, and KILL deterministically
  - markdown and JSON reports are generated without any runtime execution wiring

## Scope Guard

- This PR only aggregates outcome truth into strategy/regime expectancy metrics.
- It does not change strategy behavior, ranking behavior, or runtime execution decisions.
- It does not add a kill/keep gate or any setup fingerprinting.

## Grill Me Review

- The aggregator must not become a hidden promotion or kill policy.
- Grouping must stay purely informational and deterministic.
- Exclusion buckets must be explicit so blocked or fallback rows do not contaminate executable proof.

## Hermes Review

- `core/expectancy/strategy_regime_expectancy.py` is a pure reducer/writer over already-produced candidate outcomes.
- The report separates sample count, executable count, excluded counts, and expectancy summary.
- Sorting is deterministic by normalized group key and stable row order within each group.

## GSD Review

- Added deterministic tests for positive, negative, and insufficient-data groups.
- Added tests for fallback and blocked exclusions.
- Added tests for median cost-adjusted R, deterministic max drawdown, and JSON/Markdown report writing.

## QA / Safety Review

- read_only=true
- append=false for report objects
- is_order_action=false
- broker_api_called=false
- live_order_allowed=false
- live_order_action=false
- broker_order_action=false
- No broker APIs are called.
- No live orders are created.
- No runtime execution path is modified.

## Acceptance Proof

- `tests/test_strategy_regime_expectancy.py` proves the aggregator thresholds and exclusion rules.
- `tests/test_candidate_outcome_tracker.py` and `tests/test_cost_slippage_model.py` prove the upstream candidate outcome data remains deterministic and read-only.
- JSON and Markdown reports are generated under `.runtime/expectancy/` without runtime wiring.

## Runtime Proof Required After Merge

- Future runtime proof may consume these reports for review only.
- This PR itself does not require live wiring or live market validation.

## What This PR Does Not Prove

- It does not prove strategy edge.
- It does not prove live profitability.
- It does not prove ranking quality.
- It does not prove that a future kill/keep gate should be enabled.

## Human Approval

- This PR stays within the agreed read-only aggregation scope and does not require live order approval.


## High-Risk Path Review

N/A
