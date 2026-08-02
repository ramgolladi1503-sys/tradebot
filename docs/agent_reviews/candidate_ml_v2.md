# Candidate ML Evidence V2 Agent Review

mode: CANDIDATE_ML_V2_OFFLINE_CERTIFICATION
candidate_id: CANDIDATE_ML_V2
decision: IMPLEMENTATION_COMPLETE_CORPUS_FOUND_ML_LIFT_REJECTED
reason: replay_proxy_selector_failed_out_of_sample_and_raw_market_lane_has_insufficient_independent_sessions
timestamp: 2026-08-02T08:10:00+05:30
is_order_action: false
broker_api_called: false
source: PR_767_BRANCH_AGENT_CANDIDATE_ML_EVIDENCE_V2

## Agent Work Contract

```text
source_agent: ChatGPT GPT-5.6 Thinking
action: GENERATE_PATCH
title: Add candidate-level temporal ML evidence, real-corpus adapters, and certification
scope: Offline temporal features, immutable provenance, candidate datasets, locked holdout, model validation, certification, abstention, drift, counterfactual reporting, raw-market corpus audit, historical replay-ledger training, tests, documentation, and focused CI only.
requested_paths: core/analytics/candidate_ml_v2/**; scripts/run_candidate_ml_v2.py; scripts/run_candidate_ml_market_corpus.py; scripts/run_candidate_ml_replay_ledger.py; tests/test_candidate_ml_v2*.py; docs/architecture/candidate_ml_v2.md; docs/agent_reviews/candidate_ml_v2.md; .github/workflows/candidate-ml-v2.yml
allowed_paths: same as requested_paths
forbidden_paths: main.py; run_live.sh; config/; credentials; broker; order; execution; risk; feed; strategies; ranking; dashboard; runtime/live; production ML inference; secrets
expected_tests: focused Candidate ML V2 tests; Python compilation; real-corpus GitHub Actions lanes; repository Code Excellence and safety gates; repository CI
acceptance_proof: listed below
```

## What Changed

- Added causal feature construction from completed underlying, constituent, option, and mirror-wing histories.
- Added candidate-level event/outcome dataset construction with strict timestamp and future-field rejection.
- Added immutable JSON/JSONL input manifests with SHA-256, byte count, record count, code SHA, path-root enforcement, and source mutation detection.
- Added a physically separated, hash-sealed latest-session holdout requiring an exact acknowledgement token before opening.
- Added chronological whole-session splitting and purged walk-forward folds.
- Added a class-balanced logistic-regression baseline and regularised histogram-gradient-boosting model.
- Added validation-only Platt calibration and model-disagreement abstention.
- Added explicit missing, OOD, unsupported, unavailable, disagreement, and below-post-cost-value states.
- Added nested WFA certification with lift over the rule-only candidate stream, calibration, support, concentration, permutation, one-row-delay, and ablation controls.
- Added a data-aware walk-forward start resolver that advances the first fold until the unchanged minimum train and validation row gates are satisfied. It never lowers those gates.
- Added cost-aware thresholding and expected-value calculation.
- Added logistic contribution diagnostics, PSI drift quarantine, and actual-versus-counterfactual shadow reporting.
- Added deterministic semantic hashes and fail-closed model, source, and holdout artifact validation.
- Added a raw Upstox tick-parquet audit and market-response pretraining lane.
- Added a historical replay-ledger adapter and strategy proxy-selector training lane.

## Real Corpus Discovery

Two different corpora were found and kept separate because they support different claims.

### Raw market tick lane

The GitHub LFS corpus contains real Upstox tick data across NIFTY, BANKNIFTY, SENSEX, and option instruments.

Final audit evidence:

```text
raw normalized rows: 8,705,498
option rows: 7,891,149
index rows: 407,405
instruments: 1,105
raw sessions: 5
causally labelled market-response sessions: 4
derived training rows: 1,768
positive rate: 0.2200226244
verdict: REAL_CORPUS_FOUND_MODEL_NOT_BUILT
reason: INSUFFICIENT_INDEPENDENT_SESSIONS_FOR_MODEL_FIT
```

This lane has real market response data but no historical TradeBot candidate lineage and no option contract metadata sufficient for candidate-edge certification.

### Historical replay-ledger lane

The repository contains:

```text
runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger.jsonl
```

Final corpus evidence:

```text
input records: 145
accepted rows: 145
rejected rows: 0
sessions containing resolved candidates: 95
symbols: NIFTY, BANKNIFTY
positive rows: 38
positive rate: 0.2620689655
candidate lineage: available
option truth: MOCKED_CONTRACT_PROXY_PNL
execution grade: false
```

The ledger preserves candidate IDs, decision lineage, signal/entry/exit timestamps, setup type, HTF regime, rejection quality, cost margin, stop/target resolution, and proxy realised outcome. It is suitable only for testing whether the available strategy-context features can select better historical candidates. It cannot certify real option profitability or broker execution.

## Replay-Ledger Training Result

A proxy selector was successfully trained from the research partition after physically sealing the latest 20% session block.

```text
full rows: 145
research rows: 115
research sessions: 76
locked holdout rows: 30
locked holdout sessions: 19
locked holdout range: 2025-12-16 through 2026-06-29
holdout opened: false
model trained: true
model authority: STRATEGY_PROXY_SELECTOR_ONLY
```

The walk-forward resolver preserved the configured support gates:

```text
requested minimum train sessions: 20
effective minimum train sessions: 71
prefix rows: 105
nested train rows: 80
nested validation rows: 24
configured minimum train rows: 70
configured minimum validation rows: 20
support gates lowered: false
remaining test sessions: 5
```

## Out-of-Sample Verdict

The model failed the research-only walk-forward evaluation.

```text
verdict: NO_OUT_OF_SAMPLE_ML_LIFT
completed folds: 3
errors: 0
mean lift R: -0.1741984958
mean selected future net R: -1.0921557872
positive-expectancy fold fraction: 0.0
selected rows across folds: 1
minimum selected rows per fold: 0
maximum calibration error: 0.5361179136
```

Gate result:

```text
all_folds_completed: true
mean_lift: false
selected_support: false
positive_fold_fraction: false
calibration: false
top_five_concentration: false
best_session_concentration: false
permutation_control: true
delayed_feature_control: false
```

This is not a near miss. On the available proxy ledger, the features did not provide a usable out-of-sample selector. The single selected candidate lost approximately `-1.092 R`, and most test candidates were rejected by the value threshold or model-disagreement abstention.

The locked holdout remains sealed because the research evidence failed before holdout eligibility.

## Why This Moves Readiness Forward

The production predictor can load and score a model, but that does not prove causality, calibration, or trading value. This patch creates a separate evidence owner that constructs time-aligned inputs, seals source and holdout boundaries, compares a simple baseline with a non-linear model, and refuses to emit a trustworthy probability when evidence is incomplete or unsupported.

The negative result is operationally valuable. A model artifact was produced, but the certification correctly quarantined it instead of promoting it into ranking or execution.

## Risks

- The raw tick corpus has only four independent sessions with complete derived labels; millions of rows do not compensate for inadequate independent-session support.
- The replay ledger has only 145 resolved candidates and a 26.2% positive rate.
- The replay ledger uses mocked option contracts and proxy option P&L, so even a positive selector result would not certify real option profitability.
- The adaptive walk-forward boundary leaves only five research sessions after model support becomes sufficient; this limits test support and is recorded rather than hidden.
- Historical option outcome quality remains bounded by quote/fill realism and executable-feasibility evidence.
- WFA and controls reduce overfitting risk but cannot prove future profitability.
- PSI indicates distribution shift; it does not identify whether the shift is beneficial or harmful.
- Linear contribution diagnostics are not causal explanations.

## Scope Guard

The comparison against `main` contains 23 additive files only:

```text
.github/workflows/candidate-ml-v2.yml
core/analytics/candidate_ml_v2/__init__.py
core/analytics/candidate_ml_v2/certification.py
core/analytics/candidate_ml_v2/contracts.py
core/analytics/candidate_ml_v2/corpus_loader.py
core/analytics/candidate_ml_v2/dataset.py
core/analytics/candidate_ml_v2/evaluation.py
core/analytics/candidate_ml_v2/features.py
core/analytics/candidate_ml_v2/holdout.py
core/analytics/candidate_ml_v2/market_corpus.py
core/analytics/candidate_ml_v2/model.py
core/analytics/candidate_ml_v2/provenance.py
core/analytics/candidate_ml_v2/replay_ledger.py
docs/agent_reviews/candidate_ml_v2.md
docs/architecture/candidate_ml_v2.md
scripts/run_candidate_ml_market_corpus.py
scripts/run_candidate_ml_replay_ledger.py
scripts/run_candidate_ml_v2.py
tests/test_candidate_ml_v2.py
tests/test_candidate_ml_v2_corpus_loader.py
tests/test_candidate_ml_v2_market_corpus.py
tests/test_candidate_ml_v2_provenance.py
tests/test_candidate_ml_v2_replay_ledger.py
```

No strategy, threshold, TradeBuilder, Orchestrator, production model, ranking, capital selection, feed, broker, order, execution, risk, dashboard, credential, or live-launcher file is changed.

## Grill Me Review

The initial investigation incorrectly stopped at “authoritative candidate corpus missing.” That conclusion was challenged rather than preserved. A deeper repository and LFS inventory found both the raw Upstox corpus and the 525-day replay history containing 145 resolved candidate rows. The two sources were not merged into one claim: raw ticks support only market-response pretraining, while the replay ledger supports only a mocked-contract proxy selector.

The implementation also exposed two methodological defects during review. The first replay test used fewer validation rows than the contract allowed; the fixture was expanded instead of lowering the 20-row minimum. The first WFA layout began before the sparse ledger could satisfy the 70-row training and 20-row validation requirements; the fold start was made data-aware instead of weakening either threshold.

Finally, the presence of a serialized model was not treated as success. Its negative lift, weak calibration, and near-zero selected support produced `NO_OUT_OF_SAMPLE_ML_LIFT`, and the holdout remained sealed. No parameter search was performed against the failed result.

## Hermes Review

The architecture maintains independent evidence lanes:

1. immutable candidate-event and executable-outcome joins;
2. historical replay-ledger proxy selection;
3. raw-market response pretraining;
4. model fitting and calibrated abstention;
5. nested chronological certification;
6. locked-holdout custody;
7. drift and counterfactual evaluation.

Each lane has explicit authority metadata. The raw lane cannot claim candidate lineage. The replay lane cannot claim real option execution or profitability. The candidate event/outcome lane remains the only path capable of supporting future execution-grade certification.

Production inference, ranking, strategy selection, sizing, broker integration, and execution remain outside the dependency graph. The package cannot promote its own artifacts or route an order.

## GSD Review

The patch is additive and limited to the declared ML evidence paths. Future timestamps, future-semantic feature names, outcome-before-decision rows, incompatible parquet schemas, Git LFS pointer stubs, mutated sources, unsafe artifacts, symlinks, path escapes, and holdout mutations fail closed.

Training is chronological. The mandatory linear baseline remains alongside the nonlinear model. The adaptive WFA resolver records the requested and effective fold boundaries and proves `support_gates_lowered=false`. Failed calibration, insufficient selected support, negative lift, delayed-feature failure, and concentration failures remain visible in the final verdict.

No production strategy, threshold, TradeBuilder, Orchestrator, ranking, feed, risk, broker, order, dashboard, or live configuration was modified.

## QA / Safety Review

The focused behavioral suite covers:

- future/outcome feature rejection;
- causal decision, feature-cutoff, source, and outcome timestamps;
- target-before-stop and executable-feasibility labels;
- chronological purged folds;
- model training, calibration, serialization, and artifact safety;
- incomplete-feature, OOD, unsupported, disagreement, and value abstention paths;
- cross-market feature construction and future-row rejection;
- drift quarantine and counterfactual separation;
- locked-holdout hashing, acknowledgement, and content verification;
- nested WFA, adaptive support-boundary resolution, permutation, delayed-feature, and ablation report generation without holdout consumption;
- input source hashing, mutation detection, path escape, and symlink rejection;
- raw parquet normalization and incompatible-shard quarantine;
- replay-ledger causal conversion and noncausal-row rejection.

Every generated contract preserves:

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
allowed_for_paper_execution=false
append=false
```

## Acceptance Proof

Evidence-producing Candidate ML workflow before the final documentation-only commits:

```text
GitHub Actions run: 30729058806
head: 2b075b7733f71340091018cb632f3151e1da0bb2
focused tests: 15 passed in 15.38s
replay-ledger job: success
raw-market-corpus job: success
```

Replay-ledger artifact:

```text
artifact id: 8827358160
artifact name: candidate-ml-replay-ledger-proxy-selector
artifact digest: sha256:30f50029e105e33aae0f1256bc5069f5601cd6a0e8e65ad98593c6351dfd5f53
```

Raw-market artifact:

```text
artifact id: 8827364591
artifact name: candidate-ml-real-market-corpus-pilot
artifact digest: sha256:7515ff77b5d355f6d1a4c0a8f30664223df69af721f5305fd466d4fe8a9b3550
```

The final documentation head must pass all repository workflows before merge consideration.

## Runtime Proof Required After Merge

None for this PR. It adds no production runtime wiring and must remain draft and unmerged because the tested model failed the research gates.

A future, separate shadow-runtime PR would require an immutable execution-grade candidate/outcome corpus with real option contract identity, causal bid/ask quotes, quote age, spread, slippage, fill feasibility, target/stop path, costs, and unresolved-outcome handling. Before any runtime wiring, that corpus must demonstrate adequate independent support, positive and stable post-cost WFA lift, acceptable calibration, control survival, low winner/session concentration, sealed-holdout eligibility, and drift-safe abstention.

## What This PR Does Not Prove

This PR does not prove:

- structural market edge;
- option profitability;
- improvement over the existing strategy stream;
- calibrated performance on real executable TradeBot option candidates;
- broker fill quality;
- paper or live readiness;
- ranking, sizing, capital-allocation, or execution authority;
- that any market model can be near-perfect.

## Human Approval

No human approval is required to run offline tests or generate read-only evidence. Explicit human approval and a separate narrowly scoped PR are required before any production shadow wiring. PAPER and LIVE authority are prohibited in this PR.

## Final Status

```text
IMPLEMENTATION_COMPLETE
REAL_RAW_MARKET_CORPUS_FOUND
REAL_REPLAY_CANDIDATE_LINEAGE_FOUND
RAW_MARKET_MODEL_BLOCKED_INSUFFICIENT_SESSIONS
REPLAY_PROXY_MODEL_TRAINED
NO_OUT_OF_SAMPLE_ML_LIFT
CALIBRATION_FAILED
SELECTED_SUPPORT_FAILED
LOCKED_HOLDOUT_UNOPENED
MODEL_QUARANTINED
SHADOW_ONLY
DO_NOT_MERGE
```
