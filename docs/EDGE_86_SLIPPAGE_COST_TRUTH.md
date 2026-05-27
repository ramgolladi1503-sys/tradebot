# EDGE-86 — Slippage and Cost Truth

## Purpose

EDGE-86 adds a read-only slippage and transaction-cost truth layer on top of EDGE-84 reduced paper outcomes.

The goal is to stop treating gross paper PnL as real strategy quality. A strategy is not financially meaningful until its gross outcomes survive realistic cost drag.

## Scope

In scope:

- Consume valid EDGE-84 paper outcome reduction reports.
- Use only closed paper outcomes.
- Convert gross paper PnL into net paper PnL.
- Apply explicit cost model inputs:
  - entry slippage per unit
  - exit slippage per unit
  - per-order fee
  - turnover fee rate
  - fixed cost per trade
  - tax rate
- Surface per-candidate turnover, slippage cost, fee cost, tax cost, fixed cost, total cost, net PnL, and cost-to-gross ratio.
- Aggregate net truth by `strategy_id` and regime.
- Block invalid cost models.
- Surface malformed closed outcomes without hiding the candidate.
- Preserve read-only and non-action metadata.

Out of scope:

- Broker/adaptor interaction.
- Runtime wiring.
- Dashboard display.
- Strategy promotion or suspension.
- Strategy kill/keep decisions.
- Paper journal mutation.
- Paper event append behavior.
- Live order behavior.

## Contract

Module:

- `core.paper_slippage_cost_truth`

Main function:

- `build_slippage_cost_truth(...)`

Primary report:

- `PaperSlippageCostReport`

Candidate model:

- `PaperSlippageCostCandidate`

Bucket model:

- `PaperSlippageCostBucket`

Cost model:

- `PaperSlippageCostModel`

Status values:

- `PAPER_SLIPPAGE_COST_REDUCED`
- `PAPER_SLIPPAGE_COST_BLOCKED`

Block reasons:

- `invalid_outcome_reduction_report`
- `invalid_cost_model`
- `no_closed_paper_outcomes`
- `missing_price_or_quantity`
- `missing_gross_pnl`

## Cost formula

For each valid closed paper outcome:

```text
turnover = quantity * (abs(entry_price) + abs(exit_price))
entry_slippage_cost = quantity * entry_slippage_per_unit
exit_slippage_cost = quantity * exit_slippage_per_unit
fee_cost = (2 * fee_per_order) + (turnover * fee_rate)
tax_cost = turnover * tax_rate
fixed_cost = fixed_cost_per_trade
total_cost = entry_slippage_cost + exit_slippage_cost + fee_cost + tax_cost + fixed_cost
net_pnl = gross_pnl - total_cost
```

## Safety behavior

EDGE-86 is read-only.

It does not:

- mutate the paper journal
- append events
- call adapters
- update broker state
- change runtime behavior
- rank candidates
- promote or suspend strategies
- create dashboard behavior

Invalid cost model values fail closed before outcome reduction. Malformed closed outcomes are included in the candidate list with blockers but are excluded from net buckets.

## Test proof

Focused tests cover:

- gross-to-net candidate cost conversion
- strategy/regime net bucket aggregation
- unknown-regime fallback
- non-closed outcome exclusion
- invalid outcome report blocking
- no-closed-outcome blocking
- invalid cost model blocking
- malformed closed outcome blockers
- JSON serialization
- read-only and non-action payload flags

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_86_paper_slippage_cost_truth.py
```

## Next

EDGE-87 should use net cost truth before any strategy family kill/keep report is trusted.
