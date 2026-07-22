# ML Strategy Discovery V2 — Clean-Room Repair Evidence

mode: ML_STRATEGY_DISCOVERY_V2_CLEAN_ROOM_REPAIR
candidate_id: NONE
candidate_bundle_hash: NONE
decision: REAL_CORPUS_CERTIFICATION_PENDING
reason: The earlier V2 LONG result was produced by prototype code containing pass-only tests, invalid registry code, malformed fold logic, placeholder provenance, and simulated or non-gating analysis. That result is revoked. The live branch now contains a clean-room, development-only replacement with executable behavioral tests and an immutable private-corpus certification workflow. No repaired candidate is recognized until generated workflow artifacts are independently reviewed.
source: PR #688 branch `research/ml-strategy-discovery-v2-stability`
code_commit_sha: `98f011bb6ee9c3b84b2b861e98cbebd330022be9`
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
append: false

## Claim Boundary

- Prototype candidate `2256874b-1408-4e25-8b76-e9d2347703f2` and bundle `b6bfd5b4ce7d87e91b36928070cf0b34d3716633d9a6773f5bacaf6b78e1f704` remain revoked.
- `VALIDATION_V1_CONSUMED` remains forbidden for V2 selection or tuning.
- `HOLDOUT_V1_LOCKED` remains unopened.
- Sessions from July 11 through July 21, 2026 remain consumed and invalid for confirmation.
- `FRESH_CONFIRMATION_V2_LOCKED` remains outcome-locked.
- No confirmation token has been issued.
- No option replay or production integration has been performed.

`NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN`.

## Agent Work Contract

source_agent: ChatGPT GPT-5.6 Thinking
action: GENERATE_PATCH_AND_VERIFY
title: Replace PR #688 V2 prototype with a source-bound stability-first research pipeline
scope: V2 research package, V2 runner, V2 behavioral tests, immutable-corpus workflow, partition registry, research documentation, and this evidence file
requested_paths: `research/ml_strategy_discovery_v2/**`; `research/ml_strategy_discovery/v2_validation_registry.json`; `scripts/run_ml_strategy_discovery_v2.py`; `tests/test_ml_strategy_discovery_v2*.py`; `.github/workflows/ml_strategy_discovery_v2_corpus.yml`; V2 research and review documentation
allowed_paths: the requested research, test, workflow, and evidence paths only
forbidden_paths: production strategies, production ML inference, broker, order, execution, risk, feed, ranking, dashboard, credentials, live configuration, source parquet bytes, and locked outcome data
expected_tests: compile the replacement; execute all V2 behavioral tests; verify private corpus identities; run LONG and SHORT twice; prove semantic determinism; pass repository evidence, Code Excellence, CodeQL, registry, test, and CI gates
acceptance_proof: local clean-room fixture compiled and all 52 behavioral tests passed; GitHub and real-corpus results must be evaluated on the committed branch head

## Scope Guard

No production strategy, broker, execution, order, risk, feed, ranking, dashboard, credential, or live configuration path is changed. Source parquet files are downloaded read-only from the private release and verified against the immutable manifest. The workflow writes evidence only to the Actions runner and workflow artifacts.

## Grill Me Review

The replacement was challenged against the defects that invalidated the prototype. The review confirmed that registry boundaries are exact and fail closed; development records are selected before feature and outcome generation; readable rules must reproduce their source tree leaf; imputation is fitted only on training data; candidate survival depends on adjusted statistics, recurrence, concentration, bootstrap, support, and negative controls; and the no-candidate path completes without inventing a freeze. Remaining uncertainty is empirical rather than architectural: the authoritative corpus run has not yet produced reviewed artifacts on this exact head.

## Hermes Review

The architecture separates source certification, partition authority, causal feature enforcement, model extraction, nested chronological folds, statistical tests, controls, gates, deterministic freezing, and artifact generation. The immutable-corpus workflow verifies archive SHA-256 identities and each parquet byte before any research run. LONG and SHORT are executed independently twice with the same frozen inputs and seeds.

## GSD Review

The implementation removes the undefined registry variable, malformed fold annotation, pass-only test suite, random candidate identity, permissive bootstrap lower bound, and non-aggregate semantic determinism check. The split suite contains 52 executable tests covering registry and authorization, source and folds, model and statistics, controls and gates, pipeline verdict changes, deterministic identity, artifacts, and runner argument binding.

## QA / Safety Review

Safety fields remain read-only and non-executable. Tests cover forbidden feature families, consumed and locked partition rejection, metadata-only fresh access, candidate-bound one-time authorization primitives, manifest/sidecar mismatch, duplicate sessions, path escape, symlink rejection, source-byte mutation, exact tree-rule reproduction, session permutation, BH-FDR, max-statistic FWER, recurrence, selected-row Jaccard, imputation dependence, negative controls, deterministic freeze identity, and the absence of prototype markers. No test authorizes confirmation or broker activity.

## Acceptance Proof

- Clean-room compile: passed for `research/ml_strategy_discovery_v2`, the V2 runner, and split V2 tests.
- Behavioral suite: `52 passed` in the isolated fixture.
- Remote repaired head: `98f011bb6ee9c3b84b2b861e98cbebd330022be9`.
- Corpus archive SHA-256: `8c5fd5cded6475347c94f073b3411d6636c34dcc256243270e23ec8daf6b35f7`.
- Minimal V1 evidence archive SHA-256: `c0e2d6d872ac292d3453bf835688b096a2817176e8dd000180b09f0b46054d58`.
- GitHub repository gates and the private-corpus workflow are required to complete successfully before the PR may leave draft status.

## Runtime Proof Required After Merge

None for production runtime. This PR must not enable a strategy, place an order, call a broker, change risk limits, or consume locked confirmation outcomes. The private-corpus development screen is pre-merge research evidence. Any future confirmation, option replay, paper test, or production integration requires a separate candidate-bound and human-approved change after evidence review.

## What This PR Does Not Prove

This PR does not prove structural edge, option profitability, transaction-cost survival, fill quality, WFA certification, paper readiness, live readiness, production arbitration, or broker execution safety. A successful implementation and deterministic corpus run may still truthfully return `NO_STABLE_CANDIDATE`.

## Human Approval

Human approval remains mandatory before any confirmation-data access, option replay, paper execution, live configuration change, or production strategy integration. PR #688 remains draft and must not be merged until the committed evidence and workflow results are independently reviewed.
