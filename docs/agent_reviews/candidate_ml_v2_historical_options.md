# Candidate ML V2 Historical Options Agent Review

mode: CANDIDATE_ML_V2_HISTORICAL_OPTION_RECONSTRUCTION
candidate_id: CANDIDATE_ML_V2_HISTORICAL_OPTIONS
decision: IMPLEMENT_EXACT_ATM_RECONSTRUCTION_AND_KEEP_RUNTIME_AUTHORITY_DISABLED
reason: use_audited_kite_strategy_intents_and_real_expired_option_candle_outcomes_without_mixing_nearest_strike_proxy_rows
timestamp: 2026-08-02T08:55:00+05:30
is_order_action: false
broker_api_called: false
source: PR_767_HISTORICAL_OPTION_RECONSTRUCTION

## Agent Work Contract

```text
source_agent: ChatGPT GPT-5.6 Thinking
action: GENERATE_PATCH
title: Add Kite-underlying plus expired-option Candidate ML reconstruction
scope: Read-only conversion of audited canonical intent and real option replay ledgers into exact-ATM and nearest-strike datasets, exact-only model training, locked holdout custody, certification, tests, architecture notes and focused CI.
requested_paths: core/analytics/candidate_ml_v2/historical_option_reconstruction.py; core/analytics/candidate_ml_v2/__init__.py; scripts/run_candidate_ml_historical_options.py; tests/test_candidate_ml_v2_historical_options.py; docs/architecture/candidate_ml_v2_historical_options.md; docs/agent_reviews/candidate_ml_v2_historical_options.md; .github/workflows/candidate-ml-v2.yml
allowed_paths: same as requested_paths
forbidden_paths: strategies; thresholds; TradeBuilder; Orchestrator; ranking; feed; broker; order; execution; risk; dashboard; credentials; live launchers; local source archives; locked holdout outcomes
expected_tests: focused conversion, causality, reconciliation and evidence-separation tests; Python compilation; repository gates
acceptance_proof: final-head workflow results and a later immutable local-corpus report
```

## What Changed

- Added strict loaders for canonical option intents, real option trade outcomes and replay blockers.
- Added SHA-256 and byte/row manifests for every supplied ledger.
- Added exact identity, strategy, underlying, option type and signal-time reconciliation.
- Added causal entry and exit validation.
- Added post-cost option outcome labels and option-risk-normalized future R.
- Added signal-time candidate score, time, expiry and contract-distance features.
- Added physically separate exact-ATM and nearest-strike proxy datasets.
- Prohibited proxy rows from model fitting and certification.
- Reused Candidate ML V2 chronological splitting, calibration, walk-forward controls and locked holdout custody.
- Added focused negative tests for duplicate identities and noncausal entry timestamps.

## Scope Guard

All additions remain inside the declared offline analytics, script, test and documentation paths. Production strategy generation, candidate ranking, sizing, capital allocation, feeds, broker clients, orders, execution, risk and dashboard behavior remain unchanged.

The local Kite and expired-option archives are read only by an explicit offline campaign. This patch does not upload, rewrite or delete those corpora.

## Grill Me Review

A large option-candle row count does not guarantee signal-time ATM coverage. The original archive was centred around a narrow expiry-cycle strike wing, and part of it was materially mis-centred. The patch therefore refuses to infer exact coverage from aggregate row counts.

Nearest-strike matches are not treated as equivalent to exact ATM. They are written to a distinct artifact and excluded from model support. Empty exact support blocks model fitting rather than allowing proxy substitution.

A serialized model is not a successful result. Promotion still requires positive post-cost walk-forward lift, adequate selected support, acceptable calibration, control survival, low concentration and locked-holdout eligibility.

## Hermes Review

The dependency boundary is one-way:

```text
PR #718 audited replay artifacts
        -> historical option reconstruction
        -> exact-ATM research dataset
        -> Candidate ML V2 certification
```

The ML package does not import strategy, broker, order or execution modules. The source replay remains the authority for expiry resolution, contract selection, entry timing and conservative option outcome resolution.

The nearest-strike proxy artifact, exact-ATM artifact and locked holdout are independently named and cannot be merged by the runner.

## GSD Review

The implementation fails closed on absent files, malformed schemas, empty or duplicate identities, signal mismatches, strategy/underlying/option-type disagreement, noncausal entry, invalid exit order, nonpositive entry premium, expired contracts and reconciliation imbalance.

The focused tests prove exact/proxy separation, post-cost R construction, future-field exclusion, duplicate rejection and causal timing rejection. The workflow compiles the new CLI and executes the full Candidate ML V2 focused test pattern.

## Risks

- Historical minute candles do not contain bid/ask, depth, actual slippage, partial-fill or quote-age evidence.
- One-minute bars cannot always establish whether target or stop occurred first inside a bar; source replay policy remains authoritative.
- The available archive is strike-thin and may produce limited exact-ATM support.
- The first-candidate-per-session policy in the older broad campaign may reduce candidate diversity unless the audited source replay is rerun with the intended frozen policy.
- Positive research results would not grant PAPER or LIVE authority.

## Acceptance Proof

At this checkpoint, implementation proof is limited to repository tests because the connected environment does not contain materialized copies of the full local archives. A real-data report must record source hashes, intent/trade/blocker counts, exact/proxy counts, independent sessions, class support, holdout seal and certification verdict.

## What This PR Does Not Prove

This patch does not prove ML lift, strategy profitability, executable broker fills, complete dynamic ATM coverage, PAPER readiness or LIVE readiness.

## Human Approval

No approval is needed for offline conversion and tests. Explicit approval and a separate narrowly scoped PR are required for any shadow-runtime integration. PAPER and LIVE authority remain prohibited.

## Final Status

```text
HISTORICAL_OPTION_RECONSTRUCTION_IMPLEMENTED
EXACT_ATM_AND_NEAREST_PROXY_SEPARATED
REAL_DATA_CAMPAIGN_NOT_RUN_IN_CONNECTED_ENVIRONMENT
LOCKED_HOLDOUT_UNOPENED
NO_RUNTIME_AUTHORITY
DO_NOT_MERGE_PENDING_REAL_CORPUS_EVIDENCE
```
