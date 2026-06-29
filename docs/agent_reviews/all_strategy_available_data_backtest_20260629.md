# All-Strategy Available-Data Backtest 20260629

mode: PAPER_RESEARCH
candidate_id: all_strategy_available_data_backtest_20260629
decision: offline_directional_proxy_evidence_only
reason: Local parquet data contains index OHLC only, so the PR produces conservative offline evidence without option PnL or executable trading claims.
timestamp: 2026-06-29T20:30:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/all_strategy_available_data_backtest_20260629.md

## Agent Work Contract

Goal: add an offline evidence tool that runs strategy signal/proxy analysis only on `data/tick_data_20260629.parquet`.

Scope:

- `scripts/backtest_all_strategies_available_data.py`
- `tests/test_backtest_all_strategies_available_data.py`
- `runtime/backtests/all_strategy_20260629/`
- `docs/agent_reviews/all_strategy_available_data_backtest_20260629.md`

Safety contract:

- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- no broker API calls
- no Kite/live calls
- no order placement
- no gate, threshold, strategy, broker, feed, or order behavior changes

## Scope Guard

In scope:

- inspect the local parquet schema and data quality
- classify strategy input support against available index OHLC data
- run directional underlying-index proxy calculations where allowed
- skip executable option PnL when option truth is missing
- emit CSV, JSON, and Markdown artifacts
- add tests for offline safety and false-positive prevention

Out of scope:

- live trading
- paper order mutation
- broker integration
- Kite API calls
- strategy logic changes
- threshold changes
- risk gate changes
- feed freshness changes
- option PnL claims

## Grill Me Review

Risk: the report could be misread as executable option backtest proof.

Mitigation: the final verdict is `DIRECTIONAL_PROXY_ONLY, NOT_EXECUTABLE_OPTION_BACKTEST`; proxy trade rows have `executable=false`; the report states that it does not prove option PnL, option executability, fill quality, spread cost, depth, OI, Greeks, or IV edge.

Risk: opening-range strategies could accidentally see future range data.

Mitigation: ORB levels are unavailable until the first 15-minute range is complete, and a regression test covers this.

Risk: zero-volume data could create false VWAP confidence.

Mitigation: volume quality is reported as `ZERO_VOLUME`; VWAP and volume-dependent strategies are classified as partial or invalid volume proxy.

## Hermes Review

The tool is an offline analyzer. It reads a local parquet file, builds local feature proxies, classifies strategy capability, and writes evidence artifacts.

The design intentionally separates:

- supported directional proxy analysis
- partial proxy analysis with invalid volume assumptions
- signal-only summaries
- unsupported executable option strategies
- per-strategy errors

No runtime execution path consumes this report.

## GSD Review

Implementation completed:

- added the offline all-strategy backtest harness
- added strategy capability classification
- added unsupported option-data blocking for PnL rows
- added per-strategy error isolation
- added signal-spam flags
- generated artifacts under `runtime/backtests/all_strategy_20260629/`
- added focused tests

## QA / Safety Review

Tests added:

- schema inspection marks zero-volume VWAP paths as partial or invalid
- broker sentinel is not called by the harness
- unsupported option strategies do not produce proxy PnL claims
- fallback/advisory signals are not executable
- strategy errors do not stop the full run
- ORB levels do not use future opening-range data before completion
- proxy trades use current close and remain non-executable

Safety proof:

- proxy trades contain `executable=false`
- unsupported option strategies are absent from proxy trades
- generated report has `broker_api_called=false`
- generated report has `is_order_action=false`
- generated report has `allowed_for_live_execution=false`

## Acceptance Proof

Commands run locally:

```bash
python -m pytest -q tests/test_backtest_all_strategies_available_data.py
python -m py_compile scripts/backtest_all_strategies_available_data.py tests/test_backtest_all_strategies_available_data.py
python scripts/backtest_all_strategies_available_data.py --data data/tick_data_20260629.parquet --out runtime/backtests/all_strategy_20260629 --date 2026-06-29
```

Results:

- targeted tests: `7 passed`
- compile check: passed
- backtest command: completed with `error_count=0`
- final verdict: `DIRECTIONAL_PROXY_ONLY, NOT_EXECUTABLE_OPTION_BACKTEST`

## Runtime Proof Required After Merge

No live runtime proof is required because this PR is offline evidence generation only.

If reused for another day, rerun the script against the target parquet file and attach:

- `strategy_data_capability_matrix.csv`
- `all_strategy_proxy_summary.csv`
- `all_strategy_report_YYYYMMDD.md`
- `all_strategy_report_YYYYMMDD.json`

## What This PR Does Not Prove

This PR does not prove:

- strategy edge
- option PnL
- executable fills
- quote freshness
- option bid/ask/depth quality
- option OI, Greeks, or IV correctness
- slippage-adjusted profitability
- live or paper trading readiness
- ranking calibration

## Human Approval

Human approval is required before merge.

This PR is acceptable only if CI is green and the scope remains limited to offline evidence generation.
