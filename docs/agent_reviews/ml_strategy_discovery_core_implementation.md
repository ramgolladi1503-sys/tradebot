# ML Strategy Discovery Core — Implementation Report

Date: 2026-07-21
Status: `RESEARCH_CORE_IMPLEMENTED`
Production status: `NOT_CONNECTED`
Edge verdict: `NOT_EVALUATED_WITH_USER_DATA`

## Implemented

### Point-in-time dataset contract

- strict OHLCV and timestamp validation
- duplicate timestamps fail closed
- deterministic UTC normalization and stable sorting
- explicit session dates and interval-gap flags
- immutable schema versions
- explicit decision, feature-cutoff, and source-max timestamps
- enforced invariant: `source_data_max_timestamp <= decision_timestamp`
- deterministic semantic hashing

### Causal market features

The implementation computes completed-bar features across distinct structure families:

- multi-horizon returns
- true range and ATR
- ATR percentile
- normalized candle/range expansion
- directional efficiency
- ATR-normalized trend slope
- compression ratio
- relative volume and volume acceleration
- volume percentile
- wick ratios and close-location value
- causal session VWAP distance
- completed opening-range location and width
- prior-day range position and distances
- opening gap
- session time and weekday
- optional expiry context
- causal breakout, retest, and failed-breakout states

Opening-range values are masked until the opening range is complete.

### Path-dependent labels

- target-first, stop-first, neither, and same-bar ambiguity
- separate LONG and SHORT directional labeling
- full horizon must remain inside the same trading session
- incomplete end-of-session labels are excluded from model-ready rows
- configurable target, stop, and horizon in ATR units
- bars to event
- maximum favorable and adverse excursion
- horizon close return in ATR units
- conservative same-bar treatment as a stop in research return

### Deterministic regimes

- trend direction/range regime
- volatility regime
- gap regime
- session-time regime

### Discovery models

- shallow decision tree for readable rule paths
- XGBoost for nonlinear discovery comparison
- development-only fitting
- validation-only model metrics
- locked holdout not passed into fitting or validation scoring
- no trading session can appear in more than one partition
- ranked tree and XGBoost feature importance
- extraction of frozen `StrategyCandidate` rule contracts

### Independent evaluation and controls

- deterministic rule evaluator
- profit factor, expectancy, win rate, total R, sessions, and drawdown
- contiguous whole-session frozen-rule validation folds
- label-permutation control
- timestamp-shift control
- individual-condition ablations
- ±5% and ±10% threshold perturbations
- configurable cost stress
- explicit holdout acknowledgement guard
- independent numpy rule oracle
- future-data mutation causality oracle

### Evidence output

The CLI writes:

- `discovery_dataset.parquet`
- `feature_importance.json`
- `candidates.json`
- `evidence_manifest.json`

The manifest always states research-only status and preserves the option-data limitation.

## Deliberately not implemented

The following are not truthfully supportable without additional data or dependencies:

- real option net-outcome labels without historical bid/ask paths and strike-selection provenance
- IV/OI/depth features when those fields are absent
- SHAP interaction analysis because SHAP is not an existing repository dependency
- symbolic regression and clustering in the first core release
- strict option-replay certification directly inside the discovery package
- live execution or production inference integration
- a structural-edge or profitability claim

## Focused validation

Executed locally against the isolated implementation:

- `python -m compileall -q research scripts tests`
- `PYTHONPATH=/tmp/ml_impl pytest -q`

Result:

`9 passed`

Covered behaviors:

1. deterministic dataset hashes and explicit missing-option status
2. duplicate timestamps fail closed
3. future mutation changes labels but not features
4. chronological whole-session split and holdout ordering
5. holdout mutations do not change trained models, candidates, or validation metrics
6. rule evaluation, negative controls, stability tests, oracle agreement, and holdout guard
7. same-bar target/stop ambiguity is explicit and conservatively valued
8. barrier labels never cross a trading-session boundary
9. short-side barrier labels are directionally correct

## Truthful final verdict

This branch implements a credible research discovery core, not a finished profitable strategy.

The next evidence step is to run the CLI on the user's actual historical underlying data. Any extracted candidate that survives development and validation must then be frozen and ported to the existing strict option replay engine using real option quote paths before any executable-edge claim is allowed.
