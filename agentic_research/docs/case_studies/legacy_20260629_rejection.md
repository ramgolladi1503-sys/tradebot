# Case study: June 29 legacy evidence rejection

## Source

`runtime/backtests/all_strategy_20260629/all_strategy_report_20260629.json`

## Research question

Can the existing June 29 report certify `trend_pullback_v1` for production or option replay?

## Deterministic findings

- The report labels itself `DIRECTIONAL_PROXY_ONLY, NOT_EXECUTABLE_OPTION_BACKTEST`.
- Entry uses the current candle close, which is an optimistic same-bar directional proxy.
- The inspected dataset has `ZERO_VOLUME`.
- `movement.trend_pullback_v1` is explicitly listed under invalid volume or VWAP assumptions.

## Verdict

`REJECTED_DATA_INELIGIBLE`

## Why this is a strong agentic demonstration

The system does not accept a prior backtest because it exists, and it does not respond by tuning the strategy. It audits provenance and assumptions, obtains human approval, asks an independent critic to challenge the evidence, delegates the verdict to deterministic code and records that no strategy hypothesis is legitimate until the data problem is solved.
