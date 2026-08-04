# Candidate ML V2 Architecture

## Purpose

Candidate ML V2 is an offline, fail-closed evidence system for one narrow question:

> After a frozen strategy emits a candidate, do causal market, constituent, option, liquidity, expiry, and strategy-context features improve candidate selection over the unfiltered rule stream after costs?

It does not generate orders, change strategies, allocate capital, or claim that ML creates an edge.

## Safety Boundary

Every generated contract preserves:

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
allowed_for_paper_execution=false
append=false
```

No module in this package imports broker, order, execution, risk, orchestration, ranking, or live-launcher code.

## Evidence Lanes

### Candidate event/outcome lane

This is the strongest intended lane. It joins immutable candidate events with resolved executable outcomes by event ID or trade key. It requires causal decision timestamps, feature cutoffs no later than the decision, and resolution timestamps no earlier than the decision.

Target labels are target-before-stop outcomes with executable-feasibility truth. Future MFE, MAE, net R, stop, target, P&L, and outcome fields remain evaluation-only.

### Historical replay-ledger proxy lane

This lane adapts the existing `MEAN_REVERSION_EXTENSION` historical replay ledger into candidate rows. It preserves candidate IDs, decision lineage, signal/entry/exit timestamps, setup type, HTF regime, rejection quality, cost margin, stop/target resolution, and proxy realised R.

Its authority is deliberately limited:

```text
model_authority=STRATEGY_PROXY_SELECTOR_ONLY
execution_grade=false
option_truth=MOCKED_CONTRACT_PROXY_PNL
candidate_edge_certification_allowed=false
```

It may test whether the available strategy-context features distinguish historical winners and losers. It cannot certify option profitability or execution quality.

### Raw market-response pretraining lane

This lane materializes selected Git LFS Upstox parquet shards, rejects pointer stubs and incompatible schemas, normalizes timestamps and instruments, derives one-minute market/option state rows, and creates future market-response labels.

Its authority is:

```text
model_authority=PRETRAINING_ONLY
candidate_lineage_available=false
candidate_edge_certification_allowed=false
```

Raw market rows cannot reconstruct which TradeBot candidates were generated, rejected, ranked, approved, or resolved.

## Causal Features

The feature layer supports:

- underlying returns over 1, 3, and 5 completed rows;
- recent volatility and relative volume;
- ATR-normalized VWAP distance;
- weighted constituent breadth up/down and mean return;
- breadth dispersion and acceleration;
- leadership concentration and constituent count;
- index-versus-breadth divergence;
- option returns over 1, 3, and 5 completed rows;
- option acceleration, relative volume, and OI change;
- bid/ask spread and quote age;
- mirror-wing response and response gap;
- time to expiry;
- strategy-context features from replay lineage;
- exact decision, cutoff, and maximum source timestamps.

Future source rows fail closed instead of being trimmed.

## Models

The mandatory simple baseline is class-balanced logistic regression with standardized features. The nonlinear comparison is regularized histogram gradient boosting.

Tree probabilities use validation-only Platt calibration. A final probability is emitted only when the models agree within the configured threshold. Explicit inference states replace fallback probabilities:

```text
PREDICTION_VALID
MODEL_UNAVAILABLE
FEATURES_INCOMPLETE
PREDICTION_OUT_OF_DISTRIBUTION
INSUFFICIENT_SUPPORT
MODEL_DISAGREEMENT
BELOW_VALUE_THRESHOLD
```

## Chronological Validation

Training and validation operate on whole chronological sessions. The system never randomly shuffles time-series rows.

The walk-forward certification engine resolves the earliest chronological prefix that satisfies the existing model support gates. It advances the first fold when a sparse candidate ledger has enough sessions but not enough rows. It never lowers `min_train_rows` or `min_validation_rows`.

Certification includes:

- lift over the accept-all candidate stream;
- selected support per fold;
- positive-expectancy fold fraction;
- expected calibration error;
- Brier score and ROC AUC where defined;
- top-five winner concentration;
- best-session concentration;
- deterministic label permutation;
- one-row delayed-feature control;
- feature-removal ablations.

Possible verdicts are:

```text
INSUFFICIENT_EVIDENCE
NO_OUT_OF_SAMPLE_ML_LIFT
ML_EVIDENCE_QUARANTINED
READY_FOR_LOCKED_HOLDOUT
```

No verdict grants PAPER or LIVE authority.

## Locked Holdout

The latest chronological session block is physically separated before research certification. The parquet and sidecar carry physical and semantic SHA-256 hashes, row/session counts, and date boundaries.

Opening the holdout requires an exact acknowledgement token. Research reports always state whether holdout metrics were consumed.

## Drift and Counterfactuals

PSI-based drift states are:

```text
STABLE
DEGRADED
QUARANTINE_REQUIRED
```

Counterfactual reporting keeps actual decisions and hypothetical ML decisions separate. Unresolved outcomes remain unresolved. There is no automatic retraining or promotion.

## Real-Corpus Result Recorded on PR #767

### Raw Upstox lane

```text
8,705,498 normalized rows
7,891,149 option rows
1,105 instruments
5 raw sessions
4 causally labelled response sessions
1,768 derived rows
verdict: REAL_CORPUS_FOUND_MODEL_NOT_BUILT
reason: insufficient independent sessions
```

### Historical replay-ledger lane

```text
145 candidate rows
95 sessions containing resolved candidates
38 positive rows
30-row / 19-session locked holdout
115-row / 76-session research partition
model trained: true
```

The adaptive walk-forward start preserved the 70-row train and 20-row validation gates, using 71 initial sessions, 80 nested training rows, and 24 nested validation rows.

Research-only outcome:

```text
verdict: NO_OUT_OF_SAMPLE_ML_LIFT
mean lift R: -0.1741984958
mean selected future net R: -1.0921557872
positive fold fraction: 0.0
selected rows across folds: 1
max ECE: 0.5361179136
```

The locked holdout was not opened. The model remains quarantined and may not be wired into production ranking or execution.

## Promotion Requirements

A future model can move beyond research only after a separate immutable, execution-grade candidate/outcome corpus demonstrates:

- adequate independent-session and candidate support;
- stable positive post-cost WFA lift;
- acceptable calibration;
- survival of permutation, delayed-feature, and ablation controls;
- acceptable winner/session concentration;
- no holdout leakage;
- exact source, code, dataset, and model provenance;
- drift-safe abstention;
- real option contract, quote, spread, slippage, and fill evidence.

Production shadow wiring, PAPER authority, and LIVE authority each require a separate narrowly scoped PR and explicit human approval.
