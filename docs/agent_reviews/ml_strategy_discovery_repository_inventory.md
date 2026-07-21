# ML Strategy Discovery Repository Inventory

- mode: ML_STRATEGY_DISCOVERY_REPOSITORY_INVENTORY_V2
- candidate_id: ML_DISCOVERY_REPOSITORY_SURFACE
- decision: RESEARCH_OWNER_AND_SOURCE_AUTHORITY_IDENTIFIED
- reason: Existing production ML is not a strategy-discovery owner; the certified Upstox source manifest is the first authoritative underlying-data selection contract.
- timestamp: 2026-07-21T16:45:00+05:30
- source: ml_strategy_discovery_repository_inventory.md
- read_only: true
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- allowed_for_live_execution: false
- append: false

Baseline: `main` at `a48176fc245375f15e316493364915ec37439e29`
Branch target: `research/ml-strategy-discovery-core`

## Executive finding

The existing TradeBot ML surface is not a strategy-discovery system.

- `scripts/train_ml_overlay.py` trains an XGBoost classifier on already-generated trades and labels a row profitable when `pl > 0`. Its seven features are RSI, ADX, VWAP slope, trend distance, ATR percentage, hour, and minute. This is a trade filter/overlay, not causal market-structure discovery.
- `ml/trade_predictor.py::TradePredictor` is a production inference/runtime component with model registry, live/shadow model loading, runtime degradation, and online-update concerns. It must not be reused as the research discovery owner because that would couple experimental training to production inference.
- `ml/meta_labeler.py::MetaLabeler` is a secondary veto model for heuristic signals and has fail-open behavior when model evidence is unavailable. It is unsuitable as an evidence-grade discovery or validation owner.
- `core/option_backtest/engine.py::OptionBacktestEngine` and `core/option_backtest/wfa.py::run_option_replay_wfa` remain the strict option-replay validation authority after a candidate is frozen and real option paths are available.

## Reuse decisions

| Existing component | Decision | Reason |
|---|---|---|
| `scripts/train_ml_overlay.py` | Do not reuse directly | Labels existing trades by `pl > 0`; no path-dependent barrier contract; feature set is too narrow and indicator-heavy. |
| `ml/trade_predictor.py` | Do not modify | Production runtime owner; isolation is mandatory. |
| `ml/meta_labeler.py` | Do not reuse for evidence | It is a veto layer and can fail open when evidence is unavailable. |
| `core/option_backtest/engine.py` | Future integration target | Strict option replay and executable-side fills are the correct final validator once option paths exist. |
| `core/option_backtest/wfa.py` | Future certification target | Existing audit identifies it as the certifying WFA path. |
| `core/backtest_engine.py` and legacy WFA paths | Prohibited for edge claims | Existing audit classifies them as deprecated, proxy, or non-certifying. |

## Research owner

The isolated research owner is:

`research/ml_strategy_discovery/`

It owns causal dataset construction, interpretable discovery, deterministic candidate extraction, validation controls, and research evidence. It does not import or modify execution, broker, risk, ranking, dashboard, production strategy, or live-inference modules.

## Authoritative underlying-data source

The initial authoritative source is not an arbitrary directory scan. It is the certified ORB source manifest:

`docs/agent_reviews/opening_range_retest_causal_replay_source_manifest_v2.json`

The manifest selects file-backed sessions under:

`runtime/upstox_candidate_replay`

The existing independent source oracle established the expected contract for selected files:

- contained beneath the allowed source root
- regular non-symlink parquet files
- SHA-256 and byte-size agreement
- required timestamp, symbol, OHLC, and volume columns
- exactly 375 start-labelled one-minute rows per complete session
- Asia/Kolkata session timestamps from 09:15 through 15:29
- deterministic symbol and session identity

The ML discovery adapter reopens and independently verifies those facts. It does not trust manifest metadata without reopening the selected files.

## Timestamp authority

The certified source timestamps are start-labelled. Therefore:

```text
bar_start_timestamp = source timestamp
bar_end_timestamp = source timestamp + 1 minute
decision_timestamp = bar_end_timestamp
feature_cutoff_timestamp = bar_end_timestamp
source_data_max_timestamp = bar_end_timestamp
```

Treating the 09:15 row as available at 09:15 would leak that candle's high, low, close, and volume. The discovery contract now makes START versus END timestamp semantics explicit and fails closed when explicit-file input omits this declaration.

## Data support boundary

The current implementation supports completed underlying OHLCV bars and only audits option quote presence when optional quote data is supplied.

It does not fabricate:

- historical bid/ask paths
- implied volatility
- open interest
- option liquidity
- strike selection
- executable option P&L

When option evidence is unavailable, the dataset records `option_data_availability=UNAVAILABLE` with a reason. Underlying barrier-label metrics are explicitly named as label metrics and are never represented as option profitability.

## Validation boundary

The implementation provides:

- chronological whole-session development, validation, and locked-holdout partitions
- development-only imputer and model fitting
- validation-only default evaluation
- frozen tree-rule extraction with exact leaf ID and development imputation values
- rule-to-source-leaf reproduction proof
- label permutation and timestamp-shift controls
- condition ablations and threshold perturbations
- abstract label-cost stress in R units
- independent rule-mask and future-mutation oracles
- same-session label horizon enforcement
- separate LONG and SHORT discovery directions
- semantic dataset and candidate hashes

Contiguous validation-session slices are descriptive stability slices for a frozen rule. They are not labelled as certifying WFA. Strict option-replay certification remains blocked until a candidate is adapted to real option quote paths and passes the existing option replay engine and WFA contracts.

## Claim boundary

This inventory and implementation do not prove structural edge, profitability, Profit Factor on executable options, fill realism, WFA success, locked-holdout success, paper readiness, or live readiness.
