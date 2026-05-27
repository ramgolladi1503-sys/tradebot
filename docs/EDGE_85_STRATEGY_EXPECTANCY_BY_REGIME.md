# EDGE-85 — Strategy Expectancy by Regime

## Purpose

EDGE-85 adds a read-only paper expectancy layer on top of EDGE-84 reduced paper outcomes.

The goal is to summarize closed paper outcomes by strategy and market regime so later PRs can reason about strategy quality with evidence instead of raw trade anecdotes.

## Scope

In scope:

- Consume EDGE-84 paper outcome reduction reports.
- Use only closed paper outcomes for expectancy statistics.
- Group statistics by `strategy_id` and regime.
- Derive closed count, win count, loss count, flat count, gross paper PnL totals, average gross paper PnL, win rate, loss rate, and expectancy per trade.
- Fail closed when the input report is invalid.
- Surface insufficient sample blockers without hiding the underlying bucket.
- Preserve read-only and non-action metadata.

Out of scope:

- Slippage and cost truth.
- Strategy promotion or suspension.
- Strategy kill/keep decisions.
- Dashboard display.
- Runtime wiring.
- Broker/adaptor interaction.
- Paper journal mutation.
- Paper event append behavior.

## Contract

Module:

- `core.paper_expectancy_by_regime`

Main function:

- `build_expectancy_by_regime(outcome_report, min_closed_outcomes=1)`

Primary report:

- `PaperExpectancyReport`

Bucket model:

- `PaperExpectancyBucket`

Status values:

- `PAPER_EXPECTANCY_REDUCED`
- `PAPER_EXPECTANCY_BLOCKED`

Block reasons:

- `invalid_outcome_reduction_report`
- `no_closed_paper_outcomes`
- `insufficient_closed_sample`

## Regime selection

The reducer checks each closed outcome for regime context in this order:

1. `metadata.regime`
2. `metadata.market_regime`
3. `metadata.regime_id`
4. top-level `regime`
5. top-level `market_regime`
6. top-level `regime_id`
7. fallback to `UNKNOWN`

## Safety behavior

EDGE-85 is read-only.

It does not:

- mutate the paper journal
- append events
- call adapters
- update broker state
- change runtime behavior
- rank candidates
- promote or suspend strategies
- compute slippage or costs

## Test proof

Focused tests cover:

- grouping closed outcomes by strategy and regime
- expectancy metrics for wins and losses
- ignoring non-closed outcomes
- unknown-regime fallback
- invalid outcome report blocking
- no-closed-outcome blocking
- insufficient sample blocker propagation
- JSON serialization
- read-only and non-action payload flags

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_85_paper_expectancy_by_regime.py
```

## Next

EDGE-86 should add slippage and cost truth before any strategy quality decision can be treated as financially realistic.
