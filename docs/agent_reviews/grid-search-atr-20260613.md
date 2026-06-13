# ATR Grid Search Optimization — Agent Review Evidence

mode: PAPER
candidate_id: pr-grid-search-atr
decision: implement-atr-grid-search
reason: Allow dynamic ATR multi-variate grid search over historical datasets to isolate profitable risk-reward thresholds.
timestamp: 2026-06-13T12:33:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/grid-search-atr-20260613.md

## Agent Work Contract

This PR modifies the backtest framework to parameterize Risk-Reward ratios (ATR multipliers) and allows the Grid Search module to iteratively sweep them.
1. `core/backtest_elite.py` - Updated `EliteBacktestConfig` with `target_atr_mult` and `stop_atr_mult`.
2. `core/vectorized_signals.py` - Rewrote logic to fetch target/stop configurations from the config model rather than hardcoded 1.5x/1.0x values.
3. `scripts/run_walk_forward_elite.py` - Implemented CLI `--csv` argument and added target/stop ATR lists to the multiprocessing `param_grid`.

## Scope Guard

In scope:
- Offline offline signal configuration injection logic.

Out of scope:
- Live `TradeBuilder` modifications (untouched to protect live execution parity).

## QA / Safety Review

Safety findings:
- `is_order_action: false`
- `broker_api_called: false`

## Acceptance Proof

Executed `scripts/run_walk_forward_elite.py` against 5 years of `NIFTY` 5-minute data (92,541 rows).
**Time to evaluate 36 permutations (1.3M trade lifecycles):** 41.48 seconds.
**Optimal Finding:** Horizon=10, Slippage=1.5 bps, Target ATR=4.0x, Stop ATR=1.0x (Improved Sortino Ratio to 1.04).

## Human Approval

Human approval required before merge.
