# ORB Phase 1 v2 Source-Provenance Recertification

## Agent Work Contract
- mode: ORB_PHASE1_V2_RECERTIFICATION_SUMMARY
- candidate_id: opening_range_retest_causal_replay_summary_v2
- decision: ORB_PHASE1_V2_NOT_CERTIFIED
- reason: Fresh Phase 1 v2 replay recertifies source provenance only; outcome measurement excluded.
- timestamp: 2026-07-19T08:17:45.622317+00:00
- source: research.opening_range_retest_v2.recertification
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source_agent: Codex
- action: ORB_PHASE1_V2_SOURCE_PROVENANCE_RECERTIFICATION
- title: ORB Phase 1 v2 source-provenance repair and fresh recertification
- scope: research/opening_range_retest_v2, scripts, tests, docs/agent_reviews v2 artifacts
- requested_paths: research/opening_range_retest_v2/, scripts/run_opening_range_retest_phase1_v2_recertification.py, tests/test_opening_range_retest_phase1_v2_recertification.py, docs/agent_reviews/opening_range_retest_*_v2*
- allowed_paths: research/opening_range_retest/, research/opening_range_retest_v2/, scripts/, tests/, docs/agent_reviews/
- forbidden_paths: strategies/, core/, config/, broker/execution/risk/feed paths, runtime source parquet, credentials, main.py, run_live.sh, PR #674
- expected_tests: py_compile, ruff, focused v2 tests, determinism run, evidence gate, scoped CE, GitHub workflows
- acceptance_proof: v2 JSON artifacts, sidecars, independent audits, reconciliation, and this report

## Scope Guard
- read_only_source_handling=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false
- PRODUCTION FILES TOUCHED: NONE
- SOURCE DATA FILES MUTATED: NONE

## Grill Me Review
- Safety conclusion: fail-closed. Source and candidate v2 artifacts were generated, but overall recertification remains not certified because unaffected subset hash reconciliation is not proven.
- The report does not soften this into a pass.

## Hermes Review
- The v2 contract separates portable source identity from diagnostic absolute paths.
- Candidate core semantics and provenance-inclusive semantics are hashed separately.

## GSD Review
- Implementation is isolated to research tooling, tests, scripts, and new v2 evidence artifacts.
- Existing v1 artifacts are not silently edited.

## QA / Safety Review
- Independent source and candidate oracles fail closed on uniqueness, hash, and provenance violations.
- No outcome, broker, paper, live, or profitability claim is made.

## Source Manifest
- version: v2
- record_count: 1512
- semantic_hash: `a2790d859e7c613c7da70da9ada5aaf2a33b29e23bfdbd41ab81395780db7466`
- independent_source_oracle_verdict: `ORB_PHASE1_V2_SOURCE_MANIFEST_CERTIFIED`
- source_root_containment_failures: 0
- complete_session_failures: 0

## Candidate Ledger
- candidate_count: 2215
- candidate_core_semantic_hash: `8f28637e86095884b76ff931bf4f8b1606301895a226f7839949152c630e189a`
- candidate_provenance_semantic_hash: `6a07f0181e2fbf78bc210860e9688faff61533ff83e3ce79b6db44224d6b7ba9`
- independent_candidate_oracle_verdict: `ORB_PHASE1_V2_CANDIDATE_LEDGER_CERTIFIED`
- candidates_with_complete_source_provenance: 2215

## Reconciliation
- v1_source_record_count: 1512
- v2_source_record_count: 1512
- unchanged_source_record_count: 1507
- changed_source_record_count: 5
- source_symbol_reassignments: `[{"from_symbol": "NIFTY", "logical_path": "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet", "to_symbol": "BANKNIFTY"}, {"from_symbol": "NIFTY", "logical_path": "runtime/upstox_candidate_replay/20260707/underlying/NSE_INDEX|Nifty Bank_20260707.parquet", "to_symbol": "BANKNIFTY"}, {"from_symbol": "NIFTY", "logical_path": "runtime/upstox_candidate_replay/20260708/underlying/NSE_INDEX|Nifty Bank_20260708.parquet", "to_symbol": "BANKNIFTY"}, {"from_symbol": "NIFTY", "logical_path": "runtime/upstox_candidate_replay/20260709/underlying/NSE_INDEX|Nifty Bank_20260709.parquet", "to_symbol": "BANKNIFTY"}, {"from_symbol": "NIFTY", "logical_path": "runtime/upstox_candidate_replay/20260710/underlying/NSE_INDEX|Nifty Bank_20260710.parquet", "to_symbol": "BANKNIFTY"}]`
- source_byte_mutations: NONE
- v1_unaffected_candidate_count: 2192
- v2_unaffected_candidate_count: 2205
- unaffected_subset_reconciliation: `UNAFFECTED_SUBSET_NOT_RECONCILED`

## Acceptance Proof
- source_manifest_verdict: `ORB_PHASE1_V2_SOURCE_MANIFEST_CERTIFIED`
- candidate_ledger_verdict: `ORB_PHASE1_V2_CANDIDATE_LEDGER_CERTIFIED`
- two_directory_determinism: `TWO_DIRECTORY_DETERMINISM_PASS`
- overall_decision: `ORB_PHASE1_V2_NOT_CERTIFIED`

## Runtime Proof Required After Merge
- A human must review the fail-closed v2 reconciliation result before any future recertification or outcome-measurement task.

## What This PR Does Not Prove
- It does not prove profitability, structural edge, option P&L, live readiness, paper readiness, broker behavior, or PR #674 outcome validity.

## Human Approval
- Required before interpreting any v2 artifact as certification evidence because the current overall verdict is fail-closed.

## Artifact Digests
- source_manifest: `bc6b00315c0cbe6a5d8a2d4da8116cb675813309ae3db116b93c1cc3dd763be9`
- candidate_ledger: `9949058d008a6790d4b4a3d7d6c5ab7af3465a19449ecd947da0716aaad2085d`
- summary: `8e05b4638f927a8135ef3607e7ca6a492d88d8d58b8823a52e08876092f635a0`
- reconciliation: `90c2637b73e7a1e93d26cdde52c95fc428d74ad3be0fab33398ab7556f43aeaf`

## Claims Not Proven
- No profitability, structural edge, option P&L, paper readiness, live readiness, or PR #674 outcome validity is claimed.

## Final Verdict
`ORB_PHASE1_V2_NOT_CERTIFIED`
