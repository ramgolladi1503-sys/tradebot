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
- negative_control_count: 70
- candidate_conservation: CANDIDATE_CONSERVATION_PASS
- sidecar_verdict: ARTIFACT_SIDECARS_CERTIFIED
- contract_hash: `8826adfa54bc95308de827d658901762cc8590c4fc418e787fa1d92afc911365`
- outcome_ledger_hash: `91a9e850043c8b3ec84daf0d2a54d150adbd4f4e92e75f5e179a7cdbe182f357`
- summary_hash: `ad81556f3890b8e6e0d1d262845525df654f14b2676da7144710bec4bb1953b6`
- frozen_code_sha: `c5bcbe9e368ae4671608bba0cacda81c30418dc1`
- implementation_tree_hash: `d083ae3a92771137c6287d29e2958eac67bcc0c6405551f8d8e4962356dd09f7`

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

## Runtime Proof Required After Merge

- None for live runtime. This PR is offline research/evidence only and must not be used as live execution approval.
- If merged, post-merge proof is limited to rerunning the offline generator and audit on exact merged main.

## What This PR Does Not Prove

- Does not prove structural edge, profitability, option PnL, fill quality, slippage, latency, capital allocation, paper readiness, live readiness, broker correctness, or production promotion.
- This PR supersedes the implementation direction and stale evidence in PR #674. PR #674 itself was not modified.

## Human Approval

- Human approval is required before merge and before any use of these descriptive artifacts in later strategy-selection, paper, or live workflows.
