# Existing Strategy Exit-Policy Edge V1

## Status

`IMPLEMENTED_RESEARCH_HARNESS_DATA_EXECUTION_PENDING`

## Objective

Evaluate already-implemented TradeBot strategies as frozen causal signal generators while allowing the downstream option exit policy to use targets below 1R. The research asks whether any fixed entry signal has stable positive net expectancy after spread, slippage and charges.

## Frozen primary grid

Targets: `0.30R, 0.40R, 0.50R, 0.65R, 0.75R, 1.00R, 1.25R, 1.50R, 2.00R`

Stop: `1.00R`

Maximum holds: `5, 10, 15, 20, 30 minutes`

## Implemented

- Research-only contract with explicit claim and safety boundaries.
- Conservative long-option premium evaluator.
- Stop-first handling when target and stop touch within the same bar.
- Entry and exit slippage plus fixed round-trip cost support.
- Net-R summaries, profit factor and top-three-winner removal.
- CLI accepting normalized CSV or JSON option-bar ledgers.
- Focused tests for ambiguity, costs, time exits, robustness summaries and contract determinism.

## Required normalized input

Each input row must contain:

- `strategy_id`
- `signal_id`
- `timestamp`
- `open`, `high`, `low`, `close`
- `risk_points`

The first row for each signal may include `entry_price`; otherwise its option-bar open is used. Rows must represent the same option contract selected causally for that signal.

## Command

```bash
python scripts/evaluate_existing_strategy_exit_policies.py \
  --input .runtime/existing_strategy_exit_policy_edge_v1/normalized_option_paths.csv \
  --output .runtime/existing_strategy_exit_policy_edge_v1/policy_results.json \
  --entry-slippage-points 0.5 \
  --exit-slippage-points 0.5 \
  --fixed-round-trip-rupees 80 \
  --quantity 65
```

## Truthful limitation

No profitability result is claimed in this commit. The repository contains causal strategy replay evidence, but the full same-contract option paths referenced by the user's local data campaign are not available through GitHub alone. The harness must be executed against authoritative local option data before any edge verdict.

## Prohibited inference

This implementation is not production-ready, does not modify strategy formulas, does not alter live execution or risk, and does not establish that a 0.5R target is profitable.
