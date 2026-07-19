# ORB Underlying Outcomes v2 Certification

- decision: ORB_OUTCOMES_V2_MEASURED_AND_CERTIFIED
- contract_verdict: ORB_OUTCOME_CONTRACT_V2_FROZEN
- ledger_verdict: ORB_OUTCOME_LEDGER_V2_CERTIFIED
- audit_verdict: ORB_OUTCOMES_V2_AUDIT_CERTIFIED
- candidate_conservation: CANDIDATE_CONSERVATION_PASS
- sidecar_verdict: ARTIFACT_SIDECARS_CERTIFIED
- contract_hash: `d84c08681cc15eb499fac1d75b4968bfef1b078bf873a2af57e3bc7523168494`
- outcome_ledger_hash: `3b736db0b9ef631d165b8fb20a6ea140f6cc4de613cf35097b09cb915d6bb245`

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

## QA / Safety Review

- py_compile: PASS
- ruff: PASS
- focused outcome tests: PASS
- ORB Phase 1 v2 plus outcome tests: PASS
- independent audit CLI: PASS
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
- horizon_status_counts: {'1': {'MEASURED': 2206}, '3': {'MEASURED': 2196, 'SESSION_ENDED_BEFORE_HORIZON': 10}, '5': {'MEASURED': 2193, 'SESSION_ENDED_BEFORE_HORIZON': 13}, '15': {'MEASURED': 2155, 'SESSION_ENDED_BEFORE_HORIZON': 51}, '30': {'MEASURED': 2086, 'SESSION_ENDED_BEFORE_HORIZON': 120}}
- sidecar_verdict: ARTIFACT_SIDECARS_CERTIFIED

## Runtime Proof Required After Merge

- None for live runtime. This PR is offline research/evidence only and must not be used as live execution approval.
- If merged, post-merge proof is limited to rerunning the offline generator and audit on exact merged main.

## What This PR Does Not Prove

- Does not prove structural edge, profitability, option PnL, fill quality, slippage, latency, capital allocation, paper readiness, live readiness, broker correctness, or production promotion.

## Human Approval

- Human approval is required before merge and before any use of these descriptive artifacts in later strategy-selection, paper, or live workflows.
