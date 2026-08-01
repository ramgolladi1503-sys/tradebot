# Candidate ML Evidence V2

## Status

This component is an offline, read-only evidence system. It is not an execution authority and it does not modify TradeBuilder, Orchestrator, ranking, strategy thresholds, broker, feed, risk, order, or live configuration.

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
append=false
```

## Objective

Train and evaluate machine-learning models on one row per emitted TradeBot candidate, using only information available at the candidate decision timestamp and outcomes resolved later by the existing analytics outcome-replay boundary.

The component answers a narrow question:

> Given that a frozen strategy emitted a candidate, does the historical candidate context improve the probability and post-cost value estimate of target-before-stop outcomes?

It does not claim that raw candles alone predict the market, that ML discovers an edge, or that a probability is executable.

## Implemented contracts

### Causal temporal feature construction

`build_temporal_candidate_features()` derives deterministic features from completed historical rows at or before the decision timestamp. It rejects any supplied future row instead of silently trimming it.

The feature set includes:

- underlying returns over 1, 3, and 5 rows;
- recent underlying volatility, relative volume, and ATR-normalised VWAP distance;
- weighted constituent breadth up/down, weighted mean return, dispersion, acceleration, leadership concentration, and constituent count;
- index-versus-breadth divergence;
- option returns, acceleration, relative volume, OI change, bid/ask spread, and quote age;
- mirror-wing response and same-strike response gap;
- minutes to expiry and exact source timestamp provenance.

These are deterministic measurements, not trading rules or confidence heuristics.

### Candidate-level temporal dataset

`build_candidate_dataset()` joins TradeBot intent events to replayed outcomes by event ID or trade key. Every row records the decision timestamp, feature cutoff, later outcome resolution, strategy and instrument identity, causal numeric event metrics, target-before-stop label, executable-feasibility truth, MFE, MAE, and post-friction R.

The dataset fails closed when the outcome predates the decision, the feature cutoff exceeds the decision, rows are not chronological, or any feature key contains future/outcome/target/P&L/exit/label semantics.

### Outcome labels

Primary target:

```text
1 = replay outcome hit_target and exec_feasible=true
0 = otherwise
```

Stop-hit, future MFE, future MAE, and future net R are retained only for evaluation and are excluded from model features.

### Chronological validation

- whole-session chronological train/validation split;
- configurable row purge before validation;
- expanding purged walk-forward split helper;
- minimum training, validation, positive-class, and per-strategy support gates;
- no random row shuffle.

### Model comparison and calibration

Each model unit contains:

- standardised, class-balanced logistic regression baseline;
- regularised histogram gradient boosting classifier;
- validation-only Platt calibration for tree probability;
- ensemble probability only when the models agree;
- cost-aware probability threshold selected on a separate validation slice;
- Brier score, log loss, and ROC AUC where defined.

A global model is always attempted. Strategy-specific models are trained only with sufficient independent support.

### Abstention

Prediction returns an explicit state instead of substituting a neutral-looking probability:

- `PREDICTION_VALID`;
- `MODEL_UNAVAILABLE`;
- `FEATURES_INCOMPLETE`;
- `PREDICTION_OUT_OF_DISTRIBUTION`;
- `INSUFFICIENT_SUPPORT`;
- `MODEL_DISAGREEMENT`;
- `BELOW_VALUE_THRESHOLD`.

Even `PREDICTION_VALID` remains shadow evidence and has no execution authority.

### Cost-aware value

```text
P(win) * average_win_R - (1 - P(win)) * average_loss_R - cost_R
```

Threshold selection penalises unstable selected-return dispersion and requires minimum selected support.

### Explanations

The logistic baseline records the largest positive and negative standardised feature contributions. These are diagnostics, not causal explanations.

### Drift quarantine

`drift_report()` calculates population stability index per feature:

- `STABLE` below 0.10 maximum PSI;
- `DEGRADED` from 0.10 to below 0.25;
- `QUARANTINE_REQUIRED` at or above 0.25.

No automatic retraining or promotion exists.

### Counterfactual shadow analysis

`counterfactual_shadow_report()` keeps actual and hypothetical decisions separate:

- actual accept / ML accept;
- actual accept / ML reject;
- actual reject / ML accept;
- actual reject / ML reject;
- unresolved.

It reports counts and future net-R summaries without rewriting actual history.

## CLI

```bash
PYTHONPATH=. python scripts/run_candidate_ml_v2.py \
  --events path/to/trade_intent_events.jsonl \
  --outcomes path/to/outcome_replay.json \
  --output-root research/candidate_ml_v2/run_001
```

Outputs:

- `candidate_ml_dataset.parquet`;
- `candidate_ml_bundle.joblib`;
- `candidate_ml_manifest.json`.

The CLI consumes recorded evidence only. It does not call a broker or market-data provider.

## Deliberately excluded

- runtime/live scoring integration;
- candidate ranking authority;
- capital allocation;
- strategy threshold changes;
- automatic online retraining;
- LSTM, Transformer, or reinforcement learning;
- profitability or structural-edge claims;
- paper/live promotion.

## Promotion gate

A separate future PR may add shadow runtime scoring only after immutable real evidence proves:

1. no future-data leakage;
2. sufficient support across sessions and strategies;
3. positive walk-forward lift over the rule-only baseline after costs;
4. probability calibration stability;
5. no winner or session concentration failure;
6. delayed-entry and feature-ablation controls;
7. drift and missing-feature abstention;
8. exact same-SHA artifact and code provenance;
9. no execution authority.
