# ML Strategy Discovery Repository Inventory

Date: 2026-07-21
Baseline: `main` at `a48176fc245375f15e316493364915ec37439e29`
Branch target: `research/ml-strategy-discovery-core`

## Executive finding

The existing TradeBot ML surface is not a strategy-discovery system.

- `scripts/train_ml_overlay.py` trains an XGBoost classifier on already-generated trades and labels a row profitable when `pl > 0`. Its seven features are RSI, ADX, VWAP slope, trend distance, ATR percentage, hour, and minute. This is a trade filter/overlay, not causal market-structure discovery.
- `ml/trade_predictor.py::TradePredictor` is a production inference/runtime component with model registry, live/shadow model loading, runtime degradation, and online-update concerns. It must not be reused as the research discovery owner because that would couple experimental training to production inference.
- `ml/meta_labeler.py::MetaLabeler` is explicitly a secondary veto model for heuristic strategy signals. It also contains fail-open fallbacks (`approve=True`, probability `1.0`) when the model or features are unavailable, making it unsuitable as an evidence-grade discovery or validation component.
- `core/option_backtest/engine.py::OptionBacktestEngine` plus `core/option_backtest/wfa.py::run_option_replay_wfa` are documented as the trusted strict option-replay validation path. The new discovery lab should emit frozen deterministic candidates that can later be adapted into this strict path when real option replay data is available.

## Reuse decisions

| Existing component | Decision | Reason |
|---|---|---|
| `scripts/train_ml_overlay.py` | Do not reuse directly | Labels existing trades by `pl > 0`; no path-dependent barrier contract; feature set is too narrow and indicator-heavy. |
| `ml/trade_predictor.py` | Do not modify | Production runtime owner; isolation is required. |
| `ml/meta_labeler.py` | Do not reuse for evidence | It is a veto layer and fails open when unavailable. |
| `core/option_backtest/engine.py` | Future integration target | Strict option replay and executable-side fills are the correct final validator once option paths exist. |
| `core/option_backtest/wfa.py` | Future certification target | Existing audit identifies it as the only certifying WFA path. |
| `core/backtest_engine.py` and legacy WFA paths | Prohibited for edge claims | Existing audit classifies them as deprecated/proxy/non-certifying. |

## New isolated owner

The new package is intentionally isolated under:

`research/ml_strategy_discovery/`

It owns only research construction, discovery, deterministic candidate extraction, validation controls, and evidence manifests. It does not import production execution, broker, risk, ranking, dashboard, or live-inference modules.

## Data support boundary

The first implementation supports completed underlying OHLCV bars and an optional quote-presence check for option data.

It does not fabricate:

- historical bid/ask paths
- implied volatility
- open interest
- option liquidity
- strike selection
- executable option P&L

When these are unavailable, the dataset records `option_data_availability=UNAVAILABLE` and a reason. Underlying barrier returns are never represented as option profitability.

## Validation boundary

The first implementation provides:

- chronological whole-session development/validation/locked-holdout partitions
- development-only fitting
- validation-only default evaluation
- an explicit holdout acknowledgement gate
- contiguous whole-session validation folds for a frozen rule
- label permutation
- timestamp-shift control
- condition ablations
- threshold perturbation
- transaction-cost stress in R units
- independent rule-mask oracle
- future-mutation causality oracle
- same-session label horizon enforcement
- separate LONG and SHORT discovery directions
- semantic dataset hashes

It does not claim strict option-replay certification. That remains blocked until a frozen candidate is adapted to real option replay data and passes the existing strict engine and WFA contracts.
