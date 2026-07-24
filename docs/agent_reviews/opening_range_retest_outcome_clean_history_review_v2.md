# ORB Outcome v2 Clean-History Replacement Review

- mode: ORB_OUTCOME_CLEAN_HISTORY_REPLACEMENT_V2
- candidate_id: ALL_ORB_PHASE1_V2_CANDIDATES
- decision: ORB_OUTCOME_CLEAN_HISTORY_REPLACEMENT_CERTIFIED
- verdict: ORB_OUTCOME_CLEAN_HISTORY_REPLACEMENT_CERTIFIED
- reason: Replacement branch was built from current origin/main, excludes the historical secret-shaped fixture commit, keeps .gitleaksignore unchanged, and binds outcome evidence to frozen clean-history code SHA 21895142892a71d95aea6f7d904d4ea7cd58fcfc.
- timestamp: 2026-07-19T00:00:00Z
- source: opening_range_retest_outcome_certification_v2.md
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false

## Agent Work Contract

- source_agent: Codex
- action: CLEAN_HISTORY_REPLACEMENT_PR
- title: Replace PR #677 with certified ORB underlying outcomes v2 clean-history branch
- scope: ORB outcome measurement research artifacts, audit tooling, tests, generated certification evidence, and review evidence only
- requested_paths: research/opening_range_retest_outcomes_v2/, scripts/generate_opening_range_retest_outcomes_v2.py, scripts/audit_opening_range_retest_outcomes_v2.py, tests/test_opening_range_retest_outcomes_v2.py, tests/test_opening_range_retest_outcome_controls_v2.py, tests/orb_outcome_controls/, docs/agent_reviews/opening_range_retest_outcome_*_v2*
- allowed_paths: same as requested_paths
- forbidden_paths: .gitleaksignore, workflow files, runtime/source data, Phase 1 v2 artifacts, production execution files, broker/risk/feed/live configuration files
- expected_tests: collect-only controls, control suite, outcome suite, combined Phase 1/outcome/control suite, broad opening_range_retest suite, ruff, py_compile, diff check, gitleaks, independent outcome audit, agent review evidence gate, Code Excellence
- acceptance_proof: generated artifacts certify 2215 candidates, 2215 source joins, 154 negative controls, independent audit certification, and two-directory determinism

## Scope Guard

The replacement branch starts from origin/main f9a8ad7d8032254b7869bc115d92cbda53d36a00. The historical offending commit f2fab47707bf55ce140c1a9d0a6be57382368a72 is not an ancestor of the clean-history branch. PR #674 remains untouched.

.gitleaksignore has no clean-branch diff. Runtime/source parquet files were not copied, linked, or mutated. The only non-byte-identical implementation representation versus PR #677 is the allowed Phase 3 secret-shape rewrite in research/opening_range_retest_outcomes_v2/controls.py, where the same expected sentinel text is assembled at runtime instead of stored as one scanner-triggering literal.

## Grill Me Review

The main risk is replacing a historical PR with clean commits while preserving outcome semantics. The branch avoids cherry-pick, merge, rebase, amend, force-push, scanner suppression, and workflow weakening. The secret-shaped fixture was not restored because doing so would preserve the full-history gitleaks blocker that motivated the replacement PR.

No production execution path is changed. The artifacts are research certification outputs and do not prove trading profitability, paper-readiness, or live-readiness.

## Hermes Review

The certification boundary is explicit: the frozen code SHA is 21895142892a71d95aea6f7d904d4ea7cd58fcfc, the base main SHA is f9a8ad7d8032254b7869bc115d92cbda53d36a00, and evidence sidecars bind each generated artifact to its SHA-256 digest.

The contract keeps ORB Phase 1 v2 input artifacts as read-only source authority. Outcome v2 evidence measures candidate outcomes from existing source provenance; it does not rewrite candidate provenance, source manifests, or strategy thresholds.

## GSD Review

Implementation was materialized by path-scoped archive from PR #677 final head 8b61a304d7fa92838be963195ec91a8ac288f9c4, not by cherry-pick or merge. The clean branch contains only the outcome implementation, scripts, tests, controls, and generated review evidence.

The clean-history fixture representation in controls.py is the narrow Phase 3 scanner-safe rewrite. Control IDs, expected raw failure sets, generated control results, candidate count, source joins, summary payload, overlap payload, ledger records, and independent audit verdict remain certified by the generated artifacts.

## QA / Safety Review

- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- candidate_count: 2215
- source_join_verified_count: 2215
- negative_control_count: 154
- summary_decision: ORB_OUTCOMES_V2_MEASURED_AND_CERTIFIED
- ledger_decision: ORB_OUTCOME_LEDGER_V2_CERTIFIED
- negative_control_verdict: ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED
- audit_verdict: ORB_OUTCOMES_V2_AUDIT_CERTIFIED
- two_directory_verdict: TWO_DIRECTORY_OUTCOME_DETERMINISM_PASS
- projection_hash: 01ded3680e0f4f7228eca430880fbb74bbc7d376f1e23d1a0193f20eea8d8ce8

## Acceptance Proof

- python -m pytest --collect-only -q tests/test_opening_range_retest_outcome_controls_v2.py tests/orb_outcome_controls: 356 tests collected
- python -m pytest -q tests/test_opening_range_retest_outcome_controls_v2.py tests/orb_outcome_controls: 356 passed
- python -m pytest -q tests/test_opening_range_retest_outcomes_v2.py: 18 passed
- python -m pytest -q tests/test_opening_range_retest_phase1_v2_recertification.py tests/test_opening_range_retest_outcomes_v2.py tests/test_opening_range_retest_outcome_controls_v2.py tests/orb_outcome_controls: 409 passed
- python -m pytest -q tests/test_opening_range_retest*.py tests/orb_outcome_controls: 522 passed
- python -m ruff check research/opening_range_retest_outcomes_v2 scripts/generate_opening_range_retest_outcomes_v2.py scripts/audit_opening_range_retest_outcomes_v2.py tests/test_opening_range_retest_outcome_controls_v2.py tests/orb_outcome_controls: passed
- python -m py_compile research/opening_range_retest_outcomes_v2/*.py research/opening_range_retest_outcomes_v2/control_cases/*.py scripts/generate_opening_range_retest_outcomes_v2.py scripts/audit_opening_range_retest_outcomes_v2.py: passed
- git diff --check: passed
- gitleaks detect --redact --verbose --log-opts=origin/main..HEAD: passed
- python scripts/generate_opening_range_retest_outcomes_v2.py --source-project-root /Users/madhuram/tradebot --base-main-sha f9a8ad7d8032254b7869bc115d92cbda53d36a00 --frozen-code-sha 21895142892a71d95aea6f7d904d4ea7cd58fcfc: ORB_OUTCOMES_V2_MEASURED_AND_CERTIFIED
- python scripts/audit_opening_range_retest_outcomes_v2.py --artifact-dir docs/agent_reviews --source-project-root /Users/madhuram/tradebot: ORB_OUTCOMES_V2_AUDIT_CERTIFIED with 2215 exact record matches

## Runtime Proof Required After Merge

No runtime proof is claimed by this PR. A separate human-approved runtime task is needed before any production, paper, live, broker, risk, feed, or strategy execution path may consume these research artifacts.

## What This PR Does Not Prove

This PR does not prove profitability, live execution readiness, broker connectivity, order placement safety, feed freshness, or Phase 2 production integration. It does not authorize live trading and does not alter strategy thresholds.

## Human Approval

Human review is needed before merge. Auto-merge must remain off for the replacement PR until repository CI and reviewer approval complete.
