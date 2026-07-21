# ML Strategy Discovery V2 — Repair and Publication Evidence

mode: RESEARCH_ONLY
candidate_id: NONE
decision: V2_DISCOVERY_IMPLEMENTATION_REPAIRED_REAL_CORPUS_RERUN_REQUIRED
reason: The prior LONG candidate was produced by prototype logic containing simulated statistics, placeholder hashes, incomplete controls, non-deterministic identity, and weak tests. It is revoked. The repaired implementation has behavioral proof but has not been executed against the user's local certified TradeBot corpus in this publication environment.
timestamp: 2026-07-21T19:30:00Z
source: PR_688_REPAIR
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
append: false

## Authority

- Base main SHA: `0b086be1ad0e9bf6410fb3ea30ff26645bd5529f`
- Revocation commit: `e7b271670e04ac546fc9f531dac38a4bce922f43`
- Repaired implementation commit: `692d4888738fcecb1ac59e165a474ec52e3fbf42`
- Behavioral-proof commit: `3a1602ddd867584192796a6821e0c0bac5157f81`
- Draft PR: `#688`
- Prototype candidate ID: `2256874b-1408-4e25-8b76-e9d2347703f2`
- Prototype bundle hash: `b6bfd5b4ce7d87e91b36928070cf0b34d3716633d9a6773f5bacaf6b78e1f704`
- Prototype candidate status: `REVOKED_UNTRUSTED_PROTOTYPE_OUTPUT`

## Data boundaries

- `DEVELOPMENT_V1`: selection and labels permitted.
- `VALIDATION_V1_CONSUMED`: prohibited from V2 selection.
- `HOLDOUT_V1_LOCKED`: prohibited.
- `FRESH_CONFIRMATION_V2_CONSUMED_INVALID`: July 11–21, 2026; permanently unavailable for confirmation.
- `FRESH_CONFIRMATION_V2_LOCKED`: metadata-only until a separately approved future candidate-bound evaluation.
- Confirmation status: `NEED_NEW_FRESH_CONFIRMATION_DATA`.
- This PR does not issue or consume a confirmation token.

## Repaired implementation

- Strict source-manifest and SHA-256 sidecar verification.
- Path containment, symlink, source-byte, duplicate-session, and special-session controls.
- Development-only source selection before feature and label generation.
- Explicit causal model-feature allowlist.
- Development-fitted median imputation and exact source-leaf/rule reproduction.
- Deterministic anchored nested whole-session folds with purge/embargo.
- Development support, fold, concentration, bootstrap, and imputation gates.
- Whole-session label permutations, max-statistic family-wise correction, and Benjamini–Hochberg FDR.
- Rule recurrence, threshold similarity, and selected-row Jaccard evidence.
- Negative controls that gate candidate survival.
- Deterministic candidate IDs and canonical candidate-bundle hashes.
- Semantic artifact hashing and no confirmation token in a development-only run.

## Test evidence

```text
python3 -m compileall -q research/ml_strategy_discovery_v2 scripts tests
ruff check research/ml_strategy_discovery_v2 scripts tests
PYTHONPATH=. pytest -q tests/test_ml_strategy_discovery_v2_*.py
45 passed
```

The old `assert True` prototype suite was removed. The replacement cases exercise registry isolation, source manifests, path/symlink/source-byte failures, nested folds, causal features, fitted imputation, exact rule reproduction, multiple testing, recurrence, controls, deterministic freeze identity, semantic projection, and prototype-marker scans.

## Current research verdict

`V2_DISCOVERY_IMPLEMENTATION_REPAIRED_REAL_CORPUS_RERUN_REQUIRED`

No repaired LONG or SHORT candidate is asserted. Real-corpus runs must be executed separately for `--side LONG` and `--side SHORT` on the user's local certified source corpus before any candidate result is reviewed.

## Claim boundary

`NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN`

This work does not prove option P&L, transaction costs, fill quality, WFA certification, paper readiness, production readiness, or live readiness. No production strategy, broker, execution, order, risk, feed, ranking, dashboard, credentials, or live configuration behavior is changed.