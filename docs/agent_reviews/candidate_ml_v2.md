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
- Added underlying returns/volatility/relative volume/VWAP distance; weighted breadth, dispersion, acceleration and concentration; option returns, spread, quote age, OI/volume and mirror-response features.
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

## What Was Not Touched

No strategy, threshold, TradeBuilder, Orchestrator, ranking, capital selection, feed, broker, order, execution, risk, dashboard, credential, live launcher, or live configuration file is modified. No broker API or order action is present.

## Acceptance Proof

Local focused validation performed before publication:

```text
python -m py_compile core/analytics/candidate_ml_v2/*.py scripts/run_candidate_ml_v2.py tests/test_candidate_ml_v2.py
pytest -q tests/test_candidate_ml_v2.py
5 passed
```

The focused tests prove:

1. future/outcome feature names fail closed;
2. target/stop outcome construction preserves temporal order and safety fields;
3. purged walk-forward folds are chronological;
4. the ensemble trains and serialises without live authority;
5. incomplete features cause abstention;
6. extreme OOD input causes abstention;
7. drift can require quarantine;
8. counterfactual outcomes remain separated from unresolved rows;
9. cross-market temporal features are computed only from rows at or before the decision timestamp;
10. a supplied future option row fails closed.

Repository GitHub Actions remains the authoritative final-head validation.

## Safety Contract

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
append=false
```

## Remaining Gate

This PR must remain draft and unmerged until final-head CI passes and a real immutable candidate/outcome corpus is run. It does not claim ML edge, profitability, paper readiness, or live readiness.
