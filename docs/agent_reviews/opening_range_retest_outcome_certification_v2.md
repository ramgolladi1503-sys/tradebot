# ORB Underlying Outcomes v2 Certification

- mode: ORB_OUTCOME_CERTIFICATION_V2
- candidate_id: ALL_ORB_PHASE1_V2_CANDIDATES
- decision: ORB_OUTCOMES_V2_MEASURED_AND_CERTIFIED
- reason: certified descriptive underlying outcomes after PR 676 merge using strict file-backed source authority
- timestamp: 2026-07-19T00:00:00Z
- source: opening_range_retest_outcome_summary_v2.json
- contract_verdict: ORB_OUTCOME_CONTRACT_V2_FROZEN
- ledger_verdict: ORB_OUTCOME_LEDGER_V2_CERTIFIED
- audit_verdict: ORB_OUTCOMES_V2_AUDIT_CERTIFIED
- negative_control_verdict: ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED
- negative_control_count: 154
- candidate_conservation: CANDIDATE_CONSERVATION_PASS
- sidecar_verdict: ARTIFACT_SIDECARS_CERTIFIED
- portable_sidecar_identity: PORTABLE_LOGICAL_FILENAME
- cross_worktree_determinism: CROSS_WORKTREE_OUTCOME_DETERMINISM_PASS
- contract_hash: `6f18d094b21ee640aa1d88a163cb04313b64e9ffc3dfb18fd8ac82faa2c306b4`
- outcome_ledger_hash: `aa2faccdfc2ddddcb052cf548575c98ab62d22be3da6cb8201156f636d82d644`
- summary_hash: `be18714b259328947dd34164c381bb3e323b0c54550be8a0a4f9804ac2e76525`
- frozen_code_sha: `035702df97dccea07f54d2d3d2d7d22747b42324`
- implementation_tree_hash: `8da594d0b7a3806eb3c2b912f9fc87ab2e9a6da0fe2bf042cd8d769a1518918e`

## Agent Work Contract

- source_agent: Codex
- action: OFFLINE_OUTCOME_MEASUREMENT
- title: ORB underlying outcomes v2 certification
- scope: read-only Phase 1 v2 candidate/source artifacts and certified source parquet bars
- expected_tests: py_compile, ruff, focused outcome tests, Phase 1 v2 recertification tests, generator, independent audit
- acceptance_proof: ledger decision and audit verdict in this document

## Scope Guard

- DESCRIPTIVE_ONLY
- PRE_COST_UNDERLYING_ONLY
- NOT_EDGE_EVIDENCE
- NOT_OPTION_PNL
- PRODUCTION FILES TOUCHED: NONE
- SOURCE DATA FILES MUTATED: NONE
- SOURCE DATA FILES COPIED: NONE
- SOURCE SYMLINKS CREATED: NONE
- PHASE 1 V2 ARTIFACTS MODIFIED: NONE
- PR #674 MODIFIED: NO

## Grill Me Review

- finding: Outcome measurement remains descriptive underlying-bar evidence only.
- finding: No profitability, option PnL, fill, slippage, latency, paper/live readiness, or production-promotion claim is made.
- finding: PR #674 remains a negative-control/stale outcome attempt and is not modified or relied on as certification.

## Hermes Review

- design: Source authority is file-backed by Phase 1 v2 `source_record_id`, source SHA-256, byte size, observed symbol, observed session date, and 1-minute cadence validation.
- design: Entry is the first underlying bar strictly after `proposal_ready_at_iso`; horizons require exact elapsed source bars and do not interpolate or fall forward.
- design: Artifacts are append-free, offline, deterministic, and include SHA-256 sidecars.

## GSD Review

- implementation: Added isolated `research/opening_range_retest_outcomes_v2` contract, engine, overlap, artifact, and audit modules.
- implementation: Added generator and audit CLIs plus focused negative-control tests.
- implementation: Generated contract, ledger, summary, overlap, audit, certification, and sidecar artifacts.
- implementation: Generated negative-control matrix and sidecar artifact.
- implementation: Input sidecar paths are portable logical identities using filename-only `path` values; artifact SHA-256, declared sidecar SHA-256, and match truth remain bound in the ledger.

## QA / Safety Review

- py_compile: PASS
- ruff: PASS
- focused outcome tests: PASS
- ORB Phase 1 v2 plus outcome tests: PASS
- independent audit CLI: PASS
- negative controls: ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED
- read_only: true
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- append: false

## Acceptance Proof

- candidate_count: 2215
- source_join_verified_count: 2215
- duplicate_candidate_ids: 0
- source_failure_counts: {}
- terminal_reason_counts: {'MEASURED': 2086, 'INSUFFICIENT_HORIZON': 120, 'NO_LEGAL_ENTRY_BAR': 9}
- horizon_status_counts: {'1': {'MEASURED': 2206, 'NO_LEGAL_ENTRY_BAR': 9}, '3': {'MEASURED': 2196, 'SESSION_ENDED_BEFORE_HORIZON': 10, 'NO_LEGAL_ENTRY_BAR': 9}, '5': {'MEASURED': 2193, 'SESSION_ENDED_BEFORE_HORIZON': 13, 'NO_LEGAL_ENTRY_BAR': 9}, '15': {'MEASURED': 2155, 'SESSION_ENDED_BEFORE_HORIZON': 51, 'NO_LEGAL_ENTRY_BAR': 9}, '30': {'MEASURED': 2086, 'SESSION_ENDED_BEFORE_HORIZON': 120, 'NO_LEGAL_ENTRY_BAR': 9}}
- horizon_conservation: {'1': 2215, '3': 2215, '5': 2215, '15': 2215, '30': 2215}
- sidecar_verdict: ARTIFACT_SIDECARS_CERTIFIED
- input_sidecar_paths: PORTABLE_LOGICAL_IDENTITIES
- cross_worktree_determinism: CROSS_WORKTREE_OUTCOME_DETERMINISM_PASS

## Runtime Proof Required After Merge

- None for live runtime. This PR is offline research/evidence only and must not be used as live execution approval.
- If merged, post-merge proof is limited to rerunning the offline generator and audit on exact merged main.

## What This PR Does Not Prove

- Does not prove structural edge, profitability, option PnL, fill quality, slippage, latency, capital allocation, paper readiness, live readiness, broker correctness, or production promotion.
- This PR supersedes the implementation direction and stale evidence in PR #674. PR #674 itself was not modified.

## Human Approval

- Human approval is required before merge and before any use of these descriptive artifacts in later strategy-selection, paper, or live workflows.
