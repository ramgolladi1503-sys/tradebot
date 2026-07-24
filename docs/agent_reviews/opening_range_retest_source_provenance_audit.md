# ORB Phase 1 Source Provenance Audit v1

## Agent Work Contract
- mode: RESEARCH_ORB_PHASE1_SOURCE_PROVENANCE_AUDIT
- candidate_id: opening_range_retest_source_provenance_audit_v1
- decision: ORB_PHASE1_INVALID
- reason: ORB Phase 1 source manifest has verified source identity defects; v1 source and candidate hashes cannot certify Phase 1.
- timestamp: 2026-07-19T06:32:14.326335+00:00
- is_order_action: false
- broker_api_called: false
- source: docs/agent_reviews/opening_range_retest_source_provenance_audit_v1.json
- source_agent: Codex
- action: READ_ONLY_SOURCE_PROVENANCE_AUDIT
- title: ORB Phase 1 source-provenance repair and blast-radius certification
- scope: docs/research/source-provenance audit only
- requested_paths: research/opening_range_retest_source_provenance/, scripts/audit_opening_range_retest_source_provenance.py, tests/test_opening_range_retest_source_provenance.py, docs/agent_reviews/opening_range_retest_source_provenance_audit*
- allowed_paths: research/opening_range_retest_source_provenance/, scripts/audit_opening_range_retest_source_provenance.py, tests/test_opening_range_retest_source_provenance.py, docs/agent_reviews/
- forbidden_paths: strategies/, core/, config/, broker/execution/risk/feed paths, runtime source parquet, credentials, main.py, run_live.sh
- expected_tests: pytest, py_compile, ruff, evidence gate
- acceptance_proof: JSON audit, SHA-256 sidecar, and this markdown report

## Scope Guard
- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false
- PRODUCTION FILES TOUCHED: NONE
- SOURCE DATA FILES MUTATED: NONE

## Grill Me Review
- Verdict: PASS for failing closed. The audit found source identity contradictions, so Phase 1 outcome certification must not continue from the challenged artifacts.
- Defective source records: 10
- Mislabeled source records: 5
- Duplicate-contaminated source records: 10
- Affected session/symbol keys: [['2026-07-06', 'NIFTY'], ['2026-07-07', 'NIFTY'], ['2026-07-08', 'NIFTY'], ['2026-07-09', 'NIFTY'], ['2026-07-10', 'NIFTY']]

## Hermes Review
- The repair path is a separate provenance-audit artifact, not silent mutation of v1 replay outputs.
- Source roots are treated as mutable local paths; immutable identity comes from logical path, session, symbol, size, row count, and SHA-256.

## GSD Review
- JSON artifact SHA-256: `bdcac1d8a175b3dff999d3496c8c3563e75616a1a0d7bd3f841d7e3cb1267e9d`
- Decision: `ORB_PHASE1_INVALID`
- Classification counts: `{"CORRECT_ALTERNATIVE_SOURCE_FOUND": 5, "DUPLICATE_SOURCE_ASSIGNMENT": 10, "EXACT_MATCH": 1502, "INVENTORY_SYMBOL_MISMATCH": 5, "MANIFEST_PATH_MISMATCH": 5, "SOURCE_CONTENT_SYMBOL_MISMATCH": 5}`

## QA / Safety Review
- The auditor reads all manifest records and continues after per-record failures.
- It checks manifest path identity, inventory symbol identity, file content symbol identity, size, row count, hash, schema, session, history, duplicate assignments, and alternatives.
- Observed consistency findings mean the named component does not agree with the manifest record's declared symbol; they do not imply the component itself is corrupt.

## Historical Causality
- causal_root_cause: SELECTOR_SYMBOL_NORMALIZATION_MISCLASSIFIED_BANKNIFTY_AS_NIFTY
- causal_consequences: MANIFEST_SELECTED_WRONG_SYMBOL_SOURCE, DUPLICATE_NIFTY_SESSION_ASSIGNMENT, WRONG_SYMBOL_BARS_FED_REPLAY
- inventory/parquet internal agreement: filename, inventory metadata, and byte-probed parquet content agree the five defective files are BANKNIFTY.
- non-causal observed findings: MANIFEST_PATH_MISMATCH, INVENTORY_SYMBOL_MISMATCH, SOURCE_CONTENT_SYMBOL_MISMATCH, DUPLICATE_SOURCE_ASSIGNMENT are relative to the incorrect NIFTY manifest assignment.
- causal_root_cause_count: 5
- affected_dates: ['2026-07-06', '2026-07-07', '2026-07-08', '2026-07-09', '2026-07-10']

## Source Root Containment
- allowed_source_roots: ['/Users/madhuram/tradebot-orb-source-provenance-repair/runtime/upstox_candidate_replay', '/Users/madhuram/tradebot/runtime/upstox_candidate_replay']
- source_root_containment_failures: 0
- containment policy: candidate source paths must resolve under an allowed source root before hashing, stat, or parquet reads.

## Duplicate Identity Audit
- declared identity duplicates are computed from manifest/inventory metadata.
- observed identity duplicates are computed only from contained, successfully probed files.
- declared_duplicate_identity_counts: `{"declared_cross_symbol_path_reuse": 0, "declared_cross_symbol_sha_reuse": 0, "declared_duplicate_inventory_record_identity": 0, "declared_duplicate_logical_path": 0, "declared_duplicate_manifest_record_identity": 0, "declared_duplicate_resolved_path": 0, "declared_duplicate_session_symbol_assignment": 5, "declared_duplicate_sha": 0}`
- observed_duplicate_identity_counts: `{"observed_cross_symbol_actual_sha_reuse": 0, "observed_cross_symbol_physical_file_reuse": 0, "observed_duplicate_actual_sha": 0, "observed_duplicate_resolved_path": 0}`

## Alternative Session Contract
- complete-session alternative contract: 375 unique, strictly increasing one-minute bars from 09:15 through 15:29 local IST representation.
- alternative_session_contract_failures: 0

## Acceptance Proof
- records_audited: 1512
- selected source count observed: 1512
- source-universe hash observed: `cf4cc9cacb2db3a2f9cdc006465ebd5f8af6e6146e6a6a59048e1af38f2393bc`
- candidate count observed: 2215
- candidate semantic hash observed: `53c8cf67f33d1e958bc2ffa1730c00c86d222e67ae76d2e865da6962892e1d24`
- exact_wrong_source_emission_count: 13
- session_symbol_candidate_upper_bound_count: 23
- exact_affected_candidate_ids_available: false
- unaffected_candidate_count: 2192
- unaffected_subset_semantic_hash: `b0b41a1ac6844fa670151c6bd6020eabf8ca592ea4a2e2cdda6f09ea48719669`

## Runtime Proof Required After Merge
- No runtime proof is claimed by this PR.
- If source provenance is corrected later, rerun the ORB Phase 1 replay and independent audit from exact merged main before making outcome claims.

## What This PR Does Not Prove
- It does not prove ORB profitability, fills, live readiness, broker behavior, paper readiness, or corrected candidate outcomes.
- It does not mutate source data or certify PR #674 outcome artifacts.

## Human Approval
- Required before any future source substitution, v2 replay recertification, or outcome claim restoration.

## Final Verdict
`ORB_PHASE1_INVALID`
