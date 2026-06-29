# Candidate Lineage Rejection Ledger

This ledger exists to answer a basic question with evidence instead of inference: where do candidates die?

The trading system already has strong safety gates. What it lacked was a single, cycle-level lineage record that links generation, TradeBuilder, Phase 2, ranking, display, execution eligibility, and top-opportunity selection.

## Stage meanings

1. `generated`: a strategy or upstream component produced a candidate-shaped row.
2. `passed`: the row survived the current stage without being blocked.
3. `blocked`: the row failed a gate and cannot move forward on an executable path.
4. `downgraded`: the row is still visible for review, but it is not executable.
5. `ranked`: the row reached ranking.
6. `selected`: the row reached top-opportunity selection.

## Visibility classes

- `displayable`: safe to show in a UI or diagnostics surface.
- `rankable`: safe to enter the ranking funnel.
- `executable`: safe to be treated as an executable opportunity.
- `TOP_OPPORTUNITY`: the final selected opportunity bucket.

These are not the same thing.

A row can be displayable but not executable.
A row can be rankable but not top opportunity.
A row can be visible for review while still being correctly blocked from execution.

## Field semantics

- `block_reason`: populated only when `stage_status="blocked"`.
- `downgrade_reasons`: normalized reasons attached to blocked or downgraded rows; useful for summaries.
- `selection_reason`: populated only when `stage_status="selected"`.
- `ranking_bucket`: pre-selection eligibility bucket from ranking.
- `top_opportunity`: final selector flag.
- `selection_bucket`: final selection bucket. When present, `TOP_OPPORTUNITY` means the row was selected after ranking.
- `entry_path`: explicit lineage path such as `strategy_to_tradebuilder`, `phase2_direct`, `ranking_existing_candidate`, `soft_reject_augmented`, or `synthetic_or_debug`.

`ranking_bucket` and `top_opportunity` are intentionally different.

`ranking_bucket` says where the row sits in the ranking funnel.
`top_opportunity` says the row survived final selection.

The row can remain `ranking_bucket="EXECUTABLE_CANDIDATE"` and still be `top_opportunity=true`.

## Why fallback, stale, advisory, and degraded rows stay non-executable

The system is designed to fail closed.

If a row depends on fallback, recovered fallback, stale quote truth, advisory-only truth, or degraded truth, it can be useful for debugging or review, but it must not become executable.

That rule protects the system from confusing visibility with tradeability.

## Why selected rows are not blocked

Selected rows must not be counted as blocked.

If a row was selected, then `stage_status` should be `selected`, `block_reason` should be empty, and the row should carry `selection_reason="top_opportunity_selected"` instead.

That keeps the blocked funnel honest and prevents the ledger from double-counting final selections as failures.

## How to read the funnel

For each cycle, inspect:

1. `generated_total`
2. `tradebuilder_input_total`
3. `tradebuilder_passed_total`
4. `phase2_input_total`
5. `phase2_passed_total`
6. `displayable_total`
7. `rankable_total`
8. `executable_total`
9. `top_opportunity_total`

Then inspect the block counters to see where the losses came from:

- feed truth
- entropy
- spread
- liquidity
- stale quote
- fallback
- recovered fallback
- missing outcome contract
- score threshold
- bucket mapping
- no-trade logic

## How this supports replay and calibration

The ledger is observability-only. It does not change gates, thresholds, broker behavior, or order behavior.

Its purpose is to make later replay analysis honest:

- it shows which strategies survive,
- it shows which gates are killing them,
- it shows whether a row was only advisory or truly executable,
- it shows whether ranking is selecting real opportunities or just surviving survivors.

That makes it possible to calibrate edge later without pretending the current system already has it.
