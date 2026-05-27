# EDGE-87 — Strategy Family Kill/Keep Report

## Purpose

EDGE-87 adds a read-only strategy-family evidence report on top of EDGE-86 net slippage/cost truth.

The goal is to classify strategy families as `KEEP`, `WATCH`, or `KILL` using net paper evidence instead of gross paper PnL or isolated anecdotes.

This is reporting only. It does not change any strategy lifecycle state.

## Scope

In scope:

- Consume valid EDGE-86 slippage/cost truth reports.
- Use net-cost buckets only.
- Group strategy versions into strategy families.
- Support explicit family metadata when present.
- Derive family-level totals:
  - closed count
  - net win/loss/flat counts
  - gross PnL
  - total cost
  - net PnL
  - net expectancy per trade
  - win/loss rates
  - cost drag per trade
- Classify family evidence as `KEEP`, `WATCH`, or `KILL`.
- Preserve read-only and non-action metadata.

Out of scope:

- Strategy lifecycle state mutation.
- Strategy promotion.
- Strategy suspension.
- Dashboard display.
- Runtime wiring.
- Broker/adaptor interaction.
- Paper journal mutation.
- Paper event append behavior.

## Contract

Module:

- `core.strategy_family_kill_keep_report`

Main function:

- `build_strategy_family_report(...)`

Primary report:

- `StrategyFamilyReport`

Recommendation model:

- `StrategyFamilyRecommendation`

Policy model:

- `StrategyFamilyPolicy`

Status values:

- `STRATEGY_FAMILY_REPORT_REDUCED`
- `STRATEGY_FAMILY_REPORT_BLOCKED`

Recommendation values:

- `KEEP`
- `WATCH`
- `KILL`

Block/reason values:

- `invalid_slippage_cost_truth_report`
- `no_net_cost_buckets`
- `insufficient_family_sample`
- `negative_net_expectancy`
- `positive_net_expectancy`
- `weak_net_win_rate`
- `mixed_or_borderline_evidence`

## Classification rules

A family is classified as `WATCH` when the closed sample is below policy minimum.

A family is classified as `KILL` when net expectancy is at or below the kill threshold or total net PnL is negative.

A family is classified as `KEEP` when net expectancy meets the keep threshold and net win rate meets the keep threshold.

Otherwise, it is classified as `WATCH`.

## Family selection

Family name is resolved in this order:

1. `metadata.strategy_family`
2. `metadata.family`
3. `metadata.family_id`
4. top-level `strategy_family`
5. top-level `family`
6. top-level `family_id`
7. `strategy_id` with a trailing version suffix removed, for example `breakout_v1` becomes `breakout`
8. `UNKNOWN_FAMILY`

## Safety behavior

EDGE-87 is read-only.

It does not:

- mutate strategy state
- promote strategies
- suspend strategies
- append paper events
- call adapters
- update broker state
- change runtime behavior
- create dashboard behavior

## Test proof

Focused tests cover:

- KEEP classification
- KILL classification
- WATCH classification for insufficient sample
- WATCH classification for weak win rate
- grouping multiple strategy versions into one family
- explicit family metadata
- invalid cost truth report blocking
- empty bucket blocking
- JSON serialization
- read-only and non-action payload flags

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_87_strategy_family_kill_keep_report.py
```

## Next

After EDGE-87 merges green, continue with the LIVE-TRUTH stabilization block before EDGE-88 lifecycle governance.
