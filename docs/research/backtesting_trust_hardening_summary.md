# Backtesting trust hardening summary

## What changed

TradeBot's trustworthy backtesting path is now the hardened option-replay stack under `core/option_backtest/`.

Phase 1 through Phase 5 added:

- strict option replay data contract and fail-closed loader validation
- causal timing enforcement and elapsed-time hold enforcement
- executable-side option exit fills and explicit cost accounting
- immutable journal evidence and summary reconciliation
- an option-replay-only WFA certification path with:
  - chronological train / validation / holdout partitions
  - purge / embargo buffers
  - frozen config hashing
  - repeated-holdout blocking
  - explicit fail-closed gates

## Old paths now treated as proxy-only or retired

- `core/backtest_engine.py`: proxy research only
- `core/backtest_elite.py`: proxy research only
- legacy WFA built on vectorized / proxy engines: not valid for certification
- fake candidate WFA pass logic: not valid for certification

## What validation is now trustworthy

The codebase now has a machine-checkable framework for:

- strict single-contract option replay
- conservative executable-side fills
- explicit after-cost P&L accounting
- auditable trade and decision evidence
- option-replay WFA certification reporting

The strongest valid verdict produced by this path is:

- `PASSED_OPTION_REPLAY_CERTIFICATION`

That verdict means the strategy passed the option-replay certification framework for research validation only.

## What is still not proven

- live trading readiness
- broker execution quality
- production profitability durability
- latency-sensitive microstructure realism beyond the implemented conservative replay
- any strategy edge that has not actually passed the configured WFA gates on real data

## Exact tests run for the hardened option backtest path

- `pytest -q tests/option_backtest/test_loader.py tests/option_backtest/test_engine.py`
- `pytest -q tests/option_backtest/test_exporter.py tests/option_backtest/test_review_queue_eval.py`
- `pytest -q tests/option_backtest/test_wfa.py`

## Remaining limits

- certification quality still depends on the truthfulness of the replay dataset and partition definitions
- repeated-holdout protection is local to the configured output artifact path
- the framework blocks or fails closed when required metrics, metadata, or holdout tracking are missing
- this framework does not authorize live deployment or strategy approval on its own
