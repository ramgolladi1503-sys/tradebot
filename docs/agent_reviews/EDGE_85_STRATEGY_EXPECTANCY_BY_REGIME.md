# EDGE-85 Strategy Expectancy by Regime Agent Review

mode: REVIEW
candidate_id: edge_85_strategy_expectancy_by_regime
decision: review_ready
reason: paper_expectancy_by_regime_tests_docs
timestamp: 2026-05-27T06:20:00Z
source: edge85_strategy_expectancy_by_regime
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

EDGE-85 derives read-only paper expectancy statistics from EDGE-84 reduced paper outcomes.

The EDGE-84 outcome report remains the input contract. EDGE-85 does not mutate the paper journal, append events, or make strategy governance decisions.

## Scope

In scope:

- Consume valid EDGE-84 outcome reports.
- Use closed paper outcomes only.
- Group metrics by strategy and regime.
- Derive win, loss, flat, gross paper PnL total, average gross paper PnL, win rate, loss rate, and expectancy per trade.
- Surface insufficient sample blockers.
- Preserve read-only and non-action metadata.

Out of scope:

- Slippage/cost truth.
- Strategy governance state changes.
- Dashboard views.
- Runtime loop wiring.
- Adapter interaction.
- Paper journal mutation.
- Paper event append behavior.

## Scope Guard

- Outcome reducer remains the upstream source.
- Expectancy is derived from closed paper outcomes only.
- Invalid input blocks before aggregation.
- Insufficient samples remain blocked evidence.
- No dashboard behavior change.
- No runtime behavior change.
- No strategy governance decisioning.

## Grill Me Review

Question: Can this PR write to the paper journal?

Answer: No. It consumes outcome reports and returns a derived report only.

Question: Can this PR append events?

Answer: No. Output is read-only and append is false.

Question: Can this PR decide strategy governance state?

Answer: No. It only derives paper expectancy metrics. Governance decisions are later roadmap work.

Question: Does this PR account for slippage and costs?

Answer: No. EDGE-86 owns slippage and cost truth.

Question: Can invalid outcome evidence produce expectancy buckets?

Answer: No. Invalid input returns a blocked report with no buckets.

## Hermes Review

Boundary check:

- No runtime loop wiring added.
- No dashboard controls added.
- No adapter imports added.
- No ranking/final-quality behavior modified.
- Non-action metadata remains false.

Verdict: scoped and read-only analytics only.

## GSD Review

Files changed are narrow:

- `core/paper_expectancy_by_regime.py`
- `tests/test_edge_85_paper_expectancy_by_regime.py`
- `docs/EDGE_85_STRATEGY_EXPECTANCY_BY_REGIME.md`
- `docs/agent_reviews/EDGE_85_STRATEGY_EXPECTANCY_BY_REGIME.md`
- `docs/EDGE_TODO.md`

## QA / safety review

Tests cover:

- strategy/regime grouping
- win/loss/flat counts
- expectancy per trade
- non-closed outcome exclusion
- unknown-regime fallback
- invalid outcome report blocking
- no-closed-outcome blocking
- insufficient sample blocker propagation
- JSON serialization
- non-action metadata

## Runtime Proof Required After Merge

After merge, EDGE-85 proves only that expectancy can be derived from validated paper outcome evidence.

Any runtime report, dashboard display, or governance flow must be added in a separate scoped PR with tests and human review.

## Acceptance Proof

Command:

`PYTHONPATH=. python -m pytest tests/test_edge_85_paper_expectancy_by_regime.py`

Expected result:

- focused EDGE-85 tests pass
- invalid inputs fail closed
- valid closed outcomes derive deterministic bucket metrics
- non-action metadata remains false

## What This PR Does Not Prove

This PR does not prove:

- slippage/cost accuracy
- strategy governance readiness
- pilot readiness
- dashboard correctness
- runtime integration correctness

## Human Approval

Human review is required before any later PR wires expectancy into runtime reports, dashboards, or strategy-governance decisions.

## Next Action

After EDGE-85 merges green, continue to EDGE-86 — Slippage and Cost Truth.


## QA / Safety Review

N/A

## High-Risk Path Review

N/A
