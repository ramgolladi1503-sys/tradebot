# ML Strategy Discovery V2 — Prototype Revocation and Certified Repair

mode: ML_STRATEGY_DISCOVERY_V2_CERTIFIED_REPAIR
candidate_id: 2256874b-1408-4e25-8b76-e9d2347703f2 (revoked)
decision: V2_IMPLEMENTATION_REPAIRED_REAL_CORPUS_RERUN_REQUIRED
reason: PR #688 prototype evidence was revoked because it used placeholder provenance hashes, simulated multiple-testing and control calculations, non-deterministic candidate identity, incomplete feature leakage guards, and non-behavioral tests. The replacement implements a development-only, source-bound, nested stability-first screen. The external NIFTY corpus is not available in GitHub Actions, so no repaired LONG or SHORT candidate is asserted by this commit.
timestamp: 2026-07-22T00:00:00+00:00
source: PR #688 branch research/ml-strategy-discovery-v2-stability
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
append: false

## Claim Boundary

The current development verdict is `V2_DISCOVERY_INVALID` until the repaired code is run independently for explicit LONG and SHORT sides on the authoritative local corpus and generated artifacts are reviewed. The prior LONG candidate is not confirmation eligible.

The confirmation verdict is `NEED_NEW_FRESH_CONFIRMATION_DATA`; sessions from 2026-07-11 through 2026-07-21 remain permanently consumed and invalid.

`NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN`.

## Agent Work Contract

source_agent: ChatGPT GPT-5.6 Thinking
action: GENERATE_PATCH
title: Replace PR #688 prototype logic with a real stability-first V2 research pipeline
scope: `research/ml_strategy_discovery_v2/**`, V2 registry, V2 scripts, V2 tests, V2 research contract, and this evidence document. The unrelated V1 audit modification is reverted to `origin/main`.
requested_paths: `research/ml_strategy_discovery_v2/**`; `research/ml_strategy_discovery/v2_validation_registry.json`; `scripts/generate_ml_strategy_discovery_v2_manifest.py`; `scripts/inventory_ml_strategy_discovery_v2_source.py`; `scripts/run_ml_strategy_discovery_v2.py`; `tests/test_ml_strategy_discovery_v2.py`; `docs/research/ml_strategy_discovery_v2_contract.md`; `docs/agent_reviews/ml_strategy_discovery_v2.md`
allowed_paths: same as requested paths; the existing V2 source manifest and sidecar remain frozen inputs
forbidden_paths: production strategy, ML inference, broker, execution, order, risk, feed, ranking, dashboard, credentials, live configuration, source parquet bytes, V1 evidence semantics, and holdout outcomes
expected_tests: compile replacement modules and scripts; run behavioral V2 tests; run existing V1 ML discovery and audit suites in repository CI; run evidence, CE, CodeQL, deterministic, and health gates
acceptance_proof: 45 reconstructed behavioral tests passed before publication; GitHub CI must complete successfully on the committed repair head

## Scope Guard

No production strategy, execution, broker, order, risk, feed, ranking, dashboard, credential, live configuration, or source-data file is modified. `scripts/audit_ml_strategy_discovery_real_run.py` is restored to the `main` blob and is not part of the repaired V2 diff.

## Prototype Revocation

- revoked candidate ID: `2256874b-1408-4e25-8b76-e9d2347703f2`
- revoked reported bundle hash: `b6bfd5b4ce7d87e91b36928070cf0b34d3716633d9a6773f5bacaf6b78e1f704`
- revocation reason: `REVOKED_UNTRUSTED_PROTOTYPE_OUTPUT`
- confirmation use: prohibited
- option replay: prohibited
- production integration: prohibited

## Architecture Review

The repaired design separates registry enforcement, source certification, causal model extraction, anchored nested folds, statistical gates, controls, artifacts, and deterministic freezing. Parent manifest metadata is filtered before any source parquet is opened. Candidate generation uses explicit causal feature validation and development-fitted imputation. Readable rules must reproduce their exact source tree leaf.

## Statistical Review

The prior random-normal null was removed. The replacement permutes complete label vectors among equal-length sessions, calculates each real candidate statistic under every permutation, applies max-statistic FWER, and computes BH-FDR q-values. Structural recurrence and selected-row similarity are measured across nested folds.

The prior simulated controls were removed. The replacement calculates real row and whole-session permutations, shifted signal times, placebo decision times, delayed features, direction reversal proxy, each-condition ablation, strongest-condition removal, threshold neighborhoods, LOYO, LORO using deterministic regime fields, one/two-bar signal latency, and abstract cost stress. Control results participate in candidate rejection.

## Determinism Review

Candidate IDs derive from canonical candidate bundle hashes. Candidate bundles bind source manifest, development dataset, feature schema, fold manifest, search space, adjusted statistics, recurrence, concentration, bootstrap, imputation dependence, controls, and code commit. Semantic artifact comparison excludes only generated timestamps and output directories.

## Source and Partition Review

- current V2 source manifest sidecar declares SHA-256 `fd344cc79c95aacc6fbb1e02d8f4104be1623ff0355e3be4937a9e175ebd6fa3`
- `VALIDATION_V1_CONSUMED`: not available to selection
- `HOLDOUT_V1_LOCKED`: not loaded
- `FRESH_CONFIRMATION_V2_CONSUMED_INVALID`: 2026-07-11 through 2026-07-21; never relocked
- `FRESH_CONFIRMATION_V2_LOCKED`: metadata only; no outcomes evaluated in this PR
- Muhurat/non-standard sessions: excluded with exact rows, source identity, and reason; no padding or synthesis

## Local Reconstructed Acceptance Proof

- `python -m compileall -q research/ml_strategy_discovery_v2 scripts tests/test_ml_strategy_discovery_v2.py`: passed.
- `ruff check research/ml_strategy_discovery_v2 scripts tests/test_ml_strategy_discovery_v2.py`: passed.
- `PYTHONPATH=. pytest -q tests/test_ml_strategy_discovery_v2.py`: 45 passed.
- behavioral proof covers partition blocking, metadata-only access, persistent token binding/replay, forbidden feature families, anchored nested folds, development median imputation, exact rule reproduction, imputation dependence, metrics, concentration, deterministic bootstrap, real session permutations, BH-FDR, recurrence, real controls, deterministic candidate identity, empty freeze behavior, sidecars, unsafe paths, duplicate records, changed source bytes, symlinks, development-only manifest selection, deterministic manifest generation, and Muhurat exclusion.

## Repository CI Required

The repair is not complete until the PR head reports success for Agent Review Evidence Gate, Portfolio CI, Repo Forensics PR Gate, Code Excellence Gates, CodeQL Advanced, Verify Strategy Registry, tests, ci, gitleaks, and deterministic health checks where applicable.

## Required Real-Corpus Execution After Code Gates

Run LONG and SHORT separately under `/Users/madhuram/tradebot-ml-evidence/v2-certified-repair/`. Review input hashes, source selection, fold manifests, candidate funnels, adjusted p/q values, recurrence, concentration, controls, frozen registry, confirmation lock, and all-artifact semantic hashes. A truthful `NO_STABLE_CANDIDATE` is successful.

## What This PR Does Not Prove

This PR does not prove structural edge, option profitability, fill quality, transaction-cost survival, certifying WFA, paper readiness, live readiness, broker execution safety, or production integration.

## Human Approval

No confirmation token is issued. No new fresh outcomes are evaluated. A separate human-approved task is required only if a repaired candidate survives and genuinely new confirmation sessions exist.
