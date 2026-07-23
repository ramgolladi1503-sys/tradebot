# ORB Outcome v2 Portable Sidecar Review

- mode: ORB_OUTCOME_PORTABLE_SIDECAR_REVIEW_V2
- candidate_id: ALL_ORB_PHASE1_V2_CANDIDATES
- decision: ORB_OUTCOMES_V2_PORTABLE_SIDECAR_IDENTITY_CERTIFIED
- reason: input sidecar identity is filename-only and generic POSIX, Windows drive, and UNC absolute filesystem paths are rejected without removing sidecar hashes from projection
- timestamp: 2026-07-20T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: opening_range_retest_outcome_portable_sidecar_review_v2.md

## Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: ORB Outcome v2 portable sidecar identity closure
- scope: Repair environment-dependent input sidecar identity in ORB outcome-v2 evidence and recertify generated artifacts.
- requested_paths: `research/opening_range_retest_outcomes_v2/`, `scripts/generate_opening_range_retest_outcomes_v2.py`, `tests/test_opening_range_retest_outcome_portability_v2.py`, `docs/agent_reviews/opening_range_retest_outcome_*_v2*`
- allowed_paths: ORB outcome-v2 research, generator, focused tests, and ORB outcome-v2 evidence docs only.
- forbidden_paths: production runtime, `core/`, `config/`, broker, risk, feed, workflows, `.gitleaksignore`, source parquet data, Phase 1 v2 source artifacts, PR #674.
- expected_tests: focused portability tests, outcome replay tests, 154-control authority tests, combined ORB suites, ruff, py_compile, evidence gate, scoped CE, gitleaks.
- acceptance_proof: committed sidecar paths are logical filenames; sidecar hashes remain bound; cross-worktree byte comparison passes; economic outcome records remain unchanged.

## Scope Guard

- PRODUCTION FILES TOUCHED: NONE
- SOURCE DATA FILES MUTATED: NONE
- SOURCE DATA FILES COPIED: NONE
- SOURCE SYMLINKS CREATED: NONE
- PHASE 1 V2 ARTIFACTS MODIFIED: NONE
- PR #674 MODIFIED: NO
- BROKER API CALLED: NO
- ORDER ACTIONS: NONE
- LIVE EXECUTION ENABLED: NO

## Grill Me Review

The original defect was an evidence-schema portability gap, not a trading-math change. The risk was that `ledger.input_sidecars.*.path` embedded absolute checkout roots, causing cross-worktree semantic projection drift even when every outcome record and economic field matched. This patch keeps sidecar evidence in the projection rather than waiving it, and rejects absolute path leakage in the projection path using generic POSIX, Windows drive, and UNC detection.

## Hermes Review

Portable sidecar identity is now the filename-level logical artifact identity. Artifact SHA-256, declared sidecar SHA-256, and match truth remain bound to each input sidecar. The engine and independent oracle use the same portable sidecar schema, and the audit independently recomputes expected sidecar metadata rather than trusting ledger metadata.

## GSD Review

Implementation stayed inside ORB outcome-v2 research, generator, focused tests, and generated evidence. The previous frozen code SHA was `035702df97dccea07f54d2d3d2d7d22747b42324`. The new frozen code SHA is `9e4798d48a39f414c88095a1d1a70d055dda98a8`; after that SHA, only `docs/agent_reviews/opening_range_retest_outcome_*_v2*` evidence files were modified.

## QA / Safety Review

- `python -m pytest -q tests/test_opening_range_retest_outcome_portability_v2.py`: 7 passed.
- `python -m pytest -q tests/test_opening_range_retest_outcomes_v2.py`: 18 passed in three consecutive runs.
- `python -m pytest -q tests/test_opening_range_retest_outcome_controls_v2.py tests/orb_outcome_controls`: 356 passed in three consecutive runs.
- `python -m pytest -q tests/test_opening_range_retest_phase1_v2_recertification.py tests/test_opening_range_retest_outcomes_v2.py tests/test_opening_range_retest_outcome_controls_v2.py tests/orb_outcome_controls`: 409 passed.
- `python -m pytest -q tests/test_opening_range_retest*.py tests/orb_outcome_controls`: 527 passed.
- `python -m ruff check ...`: passed.
- `python -m py_compile ... && git diff --check`: passed.
- `gitleaks detect --redact --verbose --log-opts=5f0fe7cd74d8929ba9f270b7cffb1b998aa89948..HEAD`: no leaks found.

## Acceptance Proof

- outcome_record_count: 2215
- source_join_verified_count: 2215
- negative_control_count: 154
- portable_sidecar_identity: PORTABLE_LOGICAL_FILENAME
- generic_posix_path_negative_controls: PASS
- windows_unc_path_negative_controls: PASS
- non_path_false_positive_controls: PASS
- input_sidecar_portability_violations: 0
- semantic_absolute_path_leaks: 0
- cross_worktree_determinism: CROSS_WORKTREE_OUTCOME_DETERMINISM_PASS
- economic_field_differences: 0
- economic_outcome_equivalence: ECONOMIC_OUTCOME_RECORD_EQUIVALENCE_PASS
- projection_hash: `23ada7617040d2824e8e5e49742bfbb2d91e676994a3ba4f371d3e573014c581`
- implementation_tree_hash: `dfdeefa882879267ccdffff7e10454d4298d3767e8b3f687cfdbe6a0cd86bf14`
- contract_sha256: `f3778e2b3b025b88ae9101e1a4263c4ea4917b06541fc70454287901f5def4d5`
- ledger_sha256: `2136cf84f19aa93d4b81d3b30c3e69cc91aaaa5e849ad286b7f213ae3ec21a3a`
- summary_sha256: `bdf02a79fb15979667b0c786255f282724230657c5814819c2c37598edf866f8`
- overlap_sha256: `2e5889719a47e6ddf04e357b5fe01bedd51cfaf71221bea22d2287eddc9fb354`
- controls_sha256: `50353802cb2ffb7d38f3bda6e3c5a09490b30f121e45468776674252b2ddec75`
- audit_sha256: `2f735953256922c0119691107758863c9b9a4e26ad46998bf597bc96c7deac33`
- certification_sha256: `ca6adb16a36430899808a5bf0df95ce7e50f7eba885b133f6f55d979cd9f64b2`

## Runtime Proof Required After Merge

After this PR is human-merged, rerun post-merge ORB outcome-v2 verification from exact merged `origin/main` in a fresh isolated worktree. Required post-merge proof is byte-stable generated outcome-v2 evidence across two clean worktree roots with the same candidate count, source joins, negative controls, audit verdict, and no semantic absolute-path leaks.

## What This PR Does Not Prove

This PR does not prove profitability, strategy edge, paper readiness, live readiness, broker execution readiness, structural-edge validity, or Phase 2 integration. It proves only portable ORB outcome-v2 evidence identity and preserved measured outcome semantics for the certified replay artifacts.

## Human Approval

Human approval is required for merge and any post-merge certification step. This PR must not be auto-merged by Codex.
