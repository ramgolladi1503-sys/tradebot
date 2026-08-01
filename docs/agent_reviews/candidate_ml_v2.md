# Candidate ML Evidence V2 Agent Review

## Agent Work Contract

```text
source_agent: ChatGPT GPT-5.6 Thinking
action: GENERATE_PATCH
title: Add candidate-level temporal ML evidence and certification
scope: Offline temporal features, source provenance, candidate dataset, locked holdout, model validation, certification, abstention, drift, counterfactual reporting, tests, documentation, and focused CI only.
requested_paths: core/analytics/candidate_ml_v2/**; scripts/run_candidate_ml_v2.py; tests/test_candidate_ml_v2*.py; docs/architecture/candidate_ml_v2.md; docs/agent_reviews/candidate_ml_v2.md; .github/workflows/candidate-ml-v2.yml
allowed_paths: same as requested_paths
forbidden_paths: main.py; run_live.sh; config/; credentials; broker; order; execution; risk; feed; strategies; ranking; dashboard; runtime/live; production ML inference; secrets
expected_tests: focused Candidate ML V2 tests; Python compilation; broker/order capability scan; repository CI
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
- Added cost-aware thresholding and expected-value calculation.
- Added logistic contribution diagnostics, PSI drift quarantine, and actual-versus-counterfactual shadow reporting.
- Added deterministic semantic hashes and fail-closed model, source, and holdout artifact validation.

## Why This Moves Readiness Forward

The production predictor can load and score a model, but that does not prove causality, calibration, or trading value. This patch creates a separate evidence owner that constructs time-aligned cross-market inputs, seals source and holdout boundaries, compares a simple baseline with a non-linear model, and refuses to emit a trustworthy probability when evidence is incomplete or unsupported.

It also makes a negative result operationally useful: failure produces `NO_OUT_OF_SAMPLE_ML_LIFT`, `ML_EVIDENCE_QUARANTINED`, or `INSUFFICIENT_EVIDENCE` rather than another tuned model being promoted.

## Risks

- The repository and connected Drive currently do not contain a recorded real candidate-lineage/event/trade-outcome corpus adequate for this certification campaign.
- Raw market ticks and candles cannot reconstruct which candidates were actually generated, rejected, ranked, approved, or resolved without manufacturing history.
- Historical option outcome quality remains bounded by recorded quote/fill realism and `exec_feasible` evidence.
- WFA and controls reduce overfitting risk but cannot prove future profitability.
- PSI indicates distribution shift; it does not identify whether the shift is beneficial or harmful.
- Linear contribution diagnostics are not causal explanations.

## Scope Guard

The final changed-path scope is limited to:

```text
.github/workflows/candidate-ml-v2.yml
core/analytics/candidate_ml_v2/**
docs/agent_reviews/candidate_ml_v2.md
docs/architecture/candidate_ml_v2.md
scripts/run_candidate_ml_v2.py
tests/test_candidate_ml_v2.py
tests/test_candidate_ml_v2_provenance.py
```

The comparison against `main` contains 15 new files and no modification to production runtime paths. No strategy, threshold, TradeBuilder, Orchestrator, production model, ranking, capital selection, feed, broker, order, execution, risk, dashboard, credential, or live-launcher file is changed.

## Grill Me Review

The first implementation exposed required feature names but did not actually derive the temporal cross-market values. That was incomplete, so the branch was extended with completed-row feature construction and future-row rejection.

The next incomplete boundary was validation quality. A simple train/validation split was not sufficient, so the same PR was extended with nested purged walk-forward testing, calibration error, accept-all baseline lift, label permutation, one-row delay, feature ablations, concentration controls, and a physically sealed holdout.

The final unresolved issue is data, not code: no authoritative real candidate-lineage/outcome corpus was found. Using raw ticks or synthetic candidates to claim success would invalidate the entire exercise. The PR therefore remains draft, offline, and unmerged.

## Hermes Review

The architecture has independent layers for:

1. immutable source provenance;
2. causal feature construction;
3. candidate/outcome dataset assembly;
4. chronological train/calibration and abstaining inference;
5. research-only nested WFA certification;
6. locked-holdout custody;
7. drift and counterfactual evaluation.

Production model loading, orchestration, ranking, sizing, risk, and execution are outside the dependency graph. Every evidence object carries schema and safety truth; the locked holdout and source inputs carry physical hashes.

## GSD Review

The patch is additive and path-scoped. Future feature names, future history rows, outcome-before-decision rows, unsafe model artifacts, source mutation, symlinks, path escapes, and holdout mutation fail closed.

Training is chronological and does not shuffle rows. Logistic regression is the mandatory simple baseline. The tree model is accepted only with independent support and probability agreement. Certification can return only an evidence verdict; it has no method to route an order, allocate capital, alter a strategy, or promote itself.

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
- nested WFA, permutation, delayed-feature, and ablation report generation without holdout consumption;
- input source hashing, mutation detection, path escape, and symlink rejection.

The dedicated workflow compiles the package, runs all `tests/test_candidate_ml_v2*.py`, and scans the new code for broker/order capabilities.

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

Final focused GitHub Actions proof on the completed implementation:

```text
python -m py_compile \
  core/analytics/candidate_ml_v2/*.py \
  scripts/run_candidate_ml_v2.py \
  tests/test_candidate_ml_v2*.py

pytest -q tests/test_candidate_ml_v2*.py
9 passed in 12.52s

broker/order capability scan: PASS
```

The dedicated `Candidate ML V2` workflow completed successfully. Agent Review Evidence Gate, Portfolio CI, and Repo Forensics had also passed on the prior final-scope head; all workflows must be re-evaluated on the current documentation head before merge consideration.

## Runtime Proof Required After Merge

None for this PR because it introduces no production runtime wiring. Before a separate shadow-runtime integration is proposed, a real immutable candidate/outcome corpus must produce:

- sufficient feature and session support;
- stable positive post-cost WFA lift over the rule-only stream;
- acceptable calibration;
- control survival;
- acceptable winner and session concentration;
- no locked-holdout leakage;
- exact source, code, dataset, and model provenance;
- drift-safe abstention.

## What This PR Does Not Prove

This PR does not prove:

- structural market edge;
- option profitability;
- calibrated performance on real TradeBot candidates;
- improvement over existing strategies;
- broker fill quality;
- paper or live readiness;
- ranking, sizing, capital-allocation, or execution authority;
- that any market model can be near-perfect.

## Human Approval

No human approval is required to run offline tests or generate read-only evidence. Explicit human approval and a separate narrowly scoped PR are required before production shadow wiring. PAPER and LIVE authority are prohibited in this PR.

## Remaining Gate

The implementation and control framework are complete. Evidence completion is blocked because no authoritative recorded candidate-lineage/event/trade-outcome corpus is currently available in the repository or connected Drive. Until such a corpus exists and passes certification, this PR must remain draft and unmerged with status:

```text
IMPLEMENTATION_COMPLETE
REAL_CORPUS_MISSING
ML_LIFT_UNPROVEN
HOLDOUT_UNOPENED
SHADOW_ONLY
DO_NOT_MERGE
```
