# Candidate ML Evidence V2 Agent Review

## Agent Work Contract

```text
source_agent: ChatGPT GPT-5.6 Thinking
action: GENERATE_PATCH
title: Add candidate-level temporal ML evidence system
scope: Offline temporal features, candidate dataset, model validation, abstention, drift, counterfactual reporting, tests, documentation, and focused CI only.
requested_paths: core/analytics/candidate_ml_v2/**; scripts/run_candidate_ml_v2.py; tests/test_candidate_ml_v2.py; docs/architecture/candidate_ml_v2.md; docs/agent_reviews/candidate_ml_v2.md; .github/workflows/candidate-ml-v2.yml
allowed_paths: same as requested_paths
forbidden_paths: main.py; run_live.sh; config/; credentials; broker; order; execution; risk; feed; strategies; ranking; dashboard; runtime/live; secrets
expected_tests: focused Candidate ML V2 tests; Python compilation; repository CI
acceptance_proof: listed below
```

## What Changed

- Added causal feature construction from completed underlying, constituent, option, and mirror-wing rows.
- Added underlying returns, volatility, relative volume and VWAP distance; weighted breadth, dispersion, acceleration and concentration; option returns, spread, quote age, OI, volume and mirror-response features.
- Added a candidate-level temporal dataset builder over recorded intent events and outcome-replay records.
- Added strict future-row, future-field, timestamp, chronology, support, and feature-completeness gates.
- Added chronological validation and purged walk-forward split contracts.
- Added logistic-regression and gradient-boosting comparison, validation-only calibration, model-disagreement abstention, and post-cost threshold selection.
- Added explicit missing-feature, OOD, insufficient-support, unavailable-model, disagreement, and non-positive-value states.
- Added candidate-level linear contribution diagnostics.
- Added population-stability drift reporting with fail-closed quarantine status.
- Added actual-versus-ML counterfactual shadow reporting with unresolved separation.
- Added artifact safety validation and deterministic semantic dataset hashing.

## Why This Moves Readiness Forward

The existing production predictor can load and score models, but model existence is not evidence of predictive value. This patch creates an isolated research owner that can construct causal cross-market features and prove or falsify candidate-level ML lift without modifying production inference or execution. It also removes the unsafe ambiguity where unavailable evidence can look like a neutral probability.

## Risks

- Historical artifacts may not contain all inputs needed for every temporal feature.
- Outcome quality is limited by recorded option series and executable-feasibility evidence.
- A model can still overfit despite chronological splits; walk-forward, concentration, ablation, delay, and sealed-holdout evidence remain mandatory before promotion.
- PSI detects distribution shift but does not prove whether that shift is harmful.
- Logistic feature contributions are diagnostics, not causal explanations.

## Scope Guard

The changed-path scope is limited to:

```text
core/analytics/candidate_ml_v2/**
scripts/run_candidate_ml_v2.py
tests/test_candidate_ml_v2.py
docs/architecture/candidate_ml_v2.md
docs/agent_reviews/candidate_ml_v2.md
.github/workflows/candidate-ml-v2.yml
```

No strategy, threshold, TradeBuilder, Orchestrator, ranking, capital selection, feed, broker, order, execution, risk, dashboard, credential, live launcher, or live configuration file is modified. No broker API or order action is present.

## Grill Me Review

The implementation was reviewed for fake progress and overclaiming. The first version exposed required feature names but did not derive the cross-market temporal values. That gap was treated as incomplete implementation and repaired by adding a causal feature constructor over underlying, constituent, option, and mirror-wing histories. Remaining criticism is explicit: this code has not yet demonstrated real out-of-sample lift on an immutable candidate/outcome corpus, so it must remain shadow-only and unmerged.

## Hermes Review

The architecture separates four responsibilities:

1. deterministic feature construction from completed historical rows;
2. candidate/outcome dataset assembly;
3. chronological model training, calibration, and abstaining inference;
4. offline drift and counterfactual evaluation.

Production inference, ranking, risk and execution are deliberately outside the dependency graph. The public contracts carry exact timestamps, schema version, semantic dataset hash, and the no-live-authority safety fields.

## GSD Review

The patch is additive and path-scoped. Future-data keys and future timestamps fail closed. Training does not randomly shuffle rows. Logistic regression provides a simple baseline, while the tree model must agree within a configured bound before an ensemble probability is emitted. Missing, unsupported, out-of-distribution, unavailable, and negative-post-cost cases return named states rather than a fabricated probability.

## QA / Safety Review

Behavioral tests cover:

- future/outcome feature-name rejection;
- outcome-before-decision and feature-timestamp ordering;
- chronological purged folds;
- model training, calibration, serialization, and artifact safety;
- incomplete-feature and OOD abstention;
- drift quarantine;
- actual-versus-counterfactual separation;
- causal cross-market feature calculations;
- supplied future option-row rejection.

The focused CI also scans the new runtime-independent paths for broker and order capability. Every generated contract preserves:

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
append=false
```

## Acceptance Proof

Local focused validation performed before publication:

```text
python -m py_compile core/analytics/candidate_ml_v2/*.py scripts/run_candidate_ml_v2.py tests/test_candidate_ml_v2.py
pytest -q tests/test_candidate_ml_v2.py
5 passed
```

The final-head dedicated `Candidate ML V2` GitHub Actions workflow passed after the causal feature layer was added. Repository-wide final-head workflows remain authoritative for merge readiness.

## Runtime Proof Required After Merge

None is required for this PR because it introduces no production runtime wiring. Before any separate shadow-runtime integration is proposed, an immutable recorded corpus must prove feature availability, chronological WFA lift over the rule-only baseline, calibration stability, concentration controls, delayed-entry controls, ablations, drift handling, and exact artifact provenance.

## What This PR Does Not Prove

This PR does not prove:

- structural market edge;
- option profitability;
- calibrated performance on real TradeBot candidates;
- improvement over existing rule-only strategies;
- broker fill quality;
- paper readiness;
- live readiness;
- execution, ranking, sizing, or capital-allocation authority;
- that ML can predict every market regime.

## Human Approval

No human approval is required to execute the offline unit tests or build read-only evidence artifacts. Explicit human approval and a separate narrowly scoped PR are required before any production shadow wiring. PAPER or LIVE execution authority is outside this PR and remains prohibited.

## Remaining Gate

This PR must remain draft and unmerged until all final-head repository workflows pass and a real immutable candidate/outcome corpus is run. It does not claim ML edge, profitability, paper readiness, or live readiness.
