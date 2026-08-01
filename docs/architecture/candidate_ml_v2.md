# Candidate ML Evidence V2

## Status

Candidate ML V2 is an offline, read-only evidence and certification system. It has no production inference, ranking, sizing, broker, risk, order, or execution authority.

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
allowed_for_paper_execution=false
append=false
```

## Objective

Evaluate whether causal context available when a frozen TradeBot strategy emits a candidate improves target-before-stop selection and post-cost expectancy over the rule-only candidate stream.

This is deliberately narrower than predicting the next price. It does not claim that ML creates an edge, that a probability is executable, or that complexity can compensate for weak data.

## Causal feature construction

`build_temporal_candidate_features()` derives features only from rows at or before the decision timestamp. A supplied future row is rejected rather than silently trimmed.

It constructs:

- underlying returns over 1, 3, and 5 rows;
- recent underlying volatility and relative volume;
- ATR-normalised distance from VWAP;
- weighted constituent breadth up/down and weighted mean return;
- breadth dispersion and acceleration;
- leadership concentration and constituent count;
- index-versus-breadth divergence;
- option return over 1, 3, and 5 rows;
- option acceleration and relative volume;
- option OI change, bid/ask spread, and quote age;
- mirror-wing response and response gap;
- minutes to expiry;
- exact decision, feature-cutoff, and maximum source timestamps.

These are deterministic measurements, not hand-written confidence scores.

## Candidate-level dataset

`build_candidate_dataset()` joins recorded candidate events to later outcome-replay records by event ID or trade key. Each training row contains candidate identity, strategy and instrument context, causal features, decision and resolution timestamps, executable-feasibility truth, and evaluation-only outcomes.

Primary label:

```text
1 = outcome is hit_target and exec_feasible=true
0 = otherwise
```

Future MFE, MAE, net R, stop status, resolution timestamp, target, P&L, and outcome fields are excluded from model features. Feature keys containing future or outcome semantics fail closed.

## Immutable source provenance

Before reading the data, `build_input_manifest()` records for both events and outcomes:

- resolved path;
- SHA-256;
- byte size;
- record count;
- file format;
- code SHA supplied to the campaign;
- a semantic source-contract hash.

Source mutation, unsupported format, symlink input, and path escape fail closed. `verify_input_manifest()` reopens and rehashes the physical files.

## Locked holdout

`seal_locked_holdout()` separates the latest chronological session block before model certification. It writes a dedicated parquet file plus a sidecar containing physical and semantic hashes, row count, session count, and date boundaries.

The holdout cannot be opened without the exact acknowledgement token:

```text
OPEN_CANDIDATE_ML_V2_LOCKED_HOLDOUT
```

Research certification reports `holdout_metrics_consumed=false`. Opening the holdout is a separate explicit act after research gates pass; the ordinary training and certification path does not consume it.

## Models and calibration

Every model unit compares:

- standardised class-balanced logistic regression;
- regularised histogram gradient boosting.

The tree probability is calibrated using a validation-only Platt calibrator. An ensemble probability is emitted only when the two models agree within the configured bound. Per-strategy models require independent support; otherwise the global model or an abstention state is used.

Metrics include Brier score, log loss, ROC AUC where defined, expected calibration error during certification, selected support, post-cost expectancy, and lift over the accept-all rule-only stream.

## Abstention

The model never substitutes a neutral-looking probability for missing or unreliable evidence. It returns one of:

- `PREDICTION_VALID`;
- `MODEL_UNAVAILABLE`;
- `FEATURES_INCOMPLETE`;
- `PREDICTION_OUT_OF_DISTRIBUTION`;
- `INSUFFICIENT_SUPPORT`;
- `MODEL_DISAGREEMENT`;
- `BELOW_VALUE_THRESHOLD`.

Even `PREDICTION_VALID` remains offline shadow evidence.

## Cost-aware decision value

```text
expected_value_R = P(win) * average_win_R
                 - (1 - P(win)) * average_loss_R
                 - cost_R
```

The probability threshold is selected on a separate validation slice and penalises unstable selected-return dispersion. Accuracy alone is not an acceptance metric.

## Certification

`certify_candidate_ml()` runs nested, purged, chronological walk-forward folds. For every fold, the inner period trains and calibrates the model and the later period remains out of sample.

Certification includes:

- lift over the unfiltered rule-only candidate stream;
- selected support per fold;
- positive-expectancy fold fraction;
- expected calibration error;
- Brier score and ROC AUC where defined;
- top-five winner concentration;
- best-session concentration;
- deterministic label-permutation control;
- one-row delayed-feature control;
- feature-removal ablations.

Possible verdicts:

```text
INSUFFICIENT_EVIDENCE
NO_OUT_OF_SAMPLE_ML_LIFT
ML_EVIDENCE_QUARANTINED
READY_FOR_LOCKED_HOLDOUT
```

None of these verdicts grants PAPER or LIVE authority.

## Drift and counterfactuals

`drift_report()` computes feature PSI:

- below 0.10: `STABLE`;
- 0.10 to below 0.25: `DEGRADED`;
- 0.25 or above: `QUARANTINE_REQUIRED`.

`counterfactual_shadow_report()` keeps actual and hypothetical decisions separate:

- actual accept / ML accept;
- actual accept / ML reject;
- actual reject / ML accept;
- actual reject / ML reject;
- unresolved.

No counterfactual result rewrites actual execution history.

## Explanations

The logistic baseline records the largest positive and negative standardised feature contributions for candidate diagnostics. These are not presented as causal explanations.

## CLI

```bash
PYTHONPATH=. python scripts/run_candidate_ml_v2.py \
  --events path/to/trade_intent_events.jsonl \
  --outcomes path/to/outcome_replay.json \
  --allowed-input-root path/to/frozen_inputs \
  --code-sha <immutable_sha> \
  --output-root research/candidate_ml_v2/run_001
```

Outputs:

- `candidate_ml_input_manifest.json`;
- `candidate_ml_full_join.parquet`;
- `candidate_ml_research_dataset.parquet`;
- `candidate_ml_holdout_LOCKED.parquet` and hash sidecar;
- `candidate_ml_certification.json`;
- `candidate_ml_bundle.joblib`;
- `candidate_ml_manifest.json`.

The CLI uses recorded files only and performs no provider, broker, or order call.

## Deliberately excluded

- production or live model wiring;
- ranking and capital-allocation authority;
- strategy threshold changes;
- automatic online retraining;
- LSTM, Transformer, or reinforcement learning;
- synthetic profitability evidence;
- paper/live promotion.

## Promotion boundary

A separate shadow-runtime PR is allowed only after an immutable real TradeBot candidate/outcome corpus demonstrates stable, positive out-of-sample post-cost lift, acceptable calibration, adequate support, control survival, low concentration, feature availability, and drift-safe behaviour. A failed gate means quarantine, not tuning against the same holdout.
