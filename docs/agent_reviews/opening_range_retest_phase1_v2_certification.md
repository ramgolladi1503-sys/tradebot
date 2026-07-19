# ORB Phase 1 v2 Source-Provenance Recertification

## Agent Work Contract
- mode: ORB_PHASE1_V2_RECERTIFICATION_SUMMARY
- candidate_id: opening_range_retest_causal_replay_summary_v2
- decision: ORB_PHASE1_V2_NOT_CERTIFIED
- reason: Fresh Phase 1 v2 replay recertifies source provenance only; outcome measurement excluded.
- timestamp: 2026-07-19T10:24:29.150286+00:00
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
- Safety conclusion: fail-closed. Source and candidate v2 artifacts were generated, reconciliation is proven, but overall recertification remains not certified because the independent source oracle could not byte-probe contained source files in this isolated worktree.
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
- independent_source_oracle_verdict: `ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED`
- source_files_byte_probed: 0
- source_oracle_failures: `["SOURCE_FILE_MISSING"]`
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
- source_symbol_reassignments: `[{"actual_sha256": "ab0aeab2b747d9c175631f337601fddbf47dcf18c6bd1b1f93ca24a6dfa21b18", "from_symbol": "NIFTY", "logical_path": "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet", "new_key": ["2026-07-06", "BANKNIFTY"], "old_key": ["2026-07-06", "NIFTY"], "to_symbol": "BANKNIFTY"}, {"actual_sha256": "9fe9283f4ee7cf3e2b722938e5bc509eef786285e5e4dff22721b27c1f2f7119", "from_symbol": "NIFTY", "logical_path": "runtime/upstox_candidate_replay/20260707/underlying/NSE_INDEX|Nifty Bank_20260707.parquet", "new_key": ["2026-07-07", "BANKNIFTY"], "old_key": ["2026-07-07", "NIFTY"], "to_symbol": "BANKNIFTY"}, {"actual_sha256": "bc13b32287eac200d36cb5be234a96d003abe6811704e90a4e3e291378cdaab9", "from_symbol": "NIFTY", "logical_path": "runtime/upstox_candidate_replay/20260708/underlying/NSE_INDEX|Nifty Bank_20260708.parquet", "new_key": ["2026-07-08", "BANKNIFTY"], "old_key": ["2026-07-08", "NIFTY"], "to_symbol": "BANKNIFTY"}, {"actual_sha256": "8dfdc7b8a2c06ce46379d8f7f1cb59d10cd075bd34ceff0643c2b053ccdeb718", "from_symbol": "NIFTY", "logical_path": "runtime/upstox_candidate_replay/20260709/underlying/NSE_INDEX|Nifty Bank_20260709.parquet", "new_key": ["2026-07-09", "BANKNIFTY"], "old_key": ["2026-07-09", "NIFTY"], "to_symbol": "BANKNIFTY"}, {"actual_sha256": "2e4ccae957b1b0121a583f23b772c1cf680d8ab1cd6dfcbaa38bcdcae7b272aa", "from_symbol": "NIFTY", "logical_path": "runtime/upstox_candidate_replay/20260710/underlying/NSE_INDEX|Nifty Bank_20260710.parquet", "new_key": ["2026-07-10", "BANKNIFTY"], "old_key": ["2026-07-10", "NIFTY"], "to_symbol": "BANKNIFTY"}]`
- source_byte_mutations: NONE
- v1_unaffected_candidate_count: 2192
- v2_unaffected_candidate_count: 2192
- unaffected_subset_reconciliation: `UNAFFECTED_SUBSET_RECONCILED`

## Acceptance Proof
- source_manifest_verdict: `ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED`
- candidate_ledger_verdict: `ORB_PHASE1_V2_CANDIDATE_LEDGER_CERTIFIED`
- two_directory_determinism: `TWO_DIRECTORY_DETERMINISM_PASS`
- overall_decision: `ORB_PHASE1_V2_NOT_CERTIFIED`

## Runtime Proof Required After Merge
- A human must provide or mount the selected source parquet corpus inside the isolated worktree before any future recertification or outcome-measurement task.

## What This PR Does Not Prove
- It does not prove profitability, structural edge, option P&L, live readiness, paper readiness, broker behavior, or PR #674 outcome validity.

## Human Approval
- Required before interpreting any v2 artifact as certification evidence because the current overall verdict is fail-closed.

## Artifact Digests
- source_manifest: `75c3af56f89fdd4a95dc65c61243a3b26cd0e3a8faf0da9302b0840d81e7312d`
- candidate_ledger: `67a77e7a03e91b778d716a2bb39beea1766dc6af6dac54a1c50e1e29626ba92c`
- summary: `539fab92f6be2da01d032c1544f257e56370ef95a9c2599a733359329e237b33`
- reconciliation: `d5db372bc3661c801469e9379ef9c977bfcd4a26c50728ad3dc7ea9d6f6721c7`

## Claims Not Proven
- No profitability, structural edge, option P&L, paper readiness, live readiness, or PR #674 outcome validity is claimed.

## Final Verdict
`ORB_PHASE1_V2_NOT_CERTIFIED`
