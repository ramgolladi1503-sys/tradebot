# ORB Phase 1 Source Provenance Audit v1

## Agent Work Contract
- mode: RESEARCH_ORB_PHASE1_SOURCE_PROVENANCE_AUDIT
- candidate_id: opening_range_retest_source_provenance_audit_v1
- decision: ORB_PHASE1_INVALID
- reason: ORB Phase 1 source manifest has verified source identity defects; v1 source and candidate hashes cannot certify Phase 1.
- timestamp: 2026-07-18T22:58:13.947246+00:00
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
- JSON artifact SHA-256: `62c1fa5d6590642df11a1260b8e472bd2890f7a8207978548813d96d3cc982c5`
- Decision: `ORB_PHASE1_INVALID`
- Classification counts: `{"CORRECT_ALTERNATIVE_SOURCE_FOUND": 5, "DUPLICATE_SOURCE_ASSIGNMENT": 10, "EXACT_MATCH": 1502, "INVENTORY_SYMBOL_MISMATCH": 5, "MANIFEST_PATH_MISMATCH": 5, "SOURCE_CONTENT_SYMBOL_MISMATCH": 5}`

## QA / Safety Review
- The auditor reads all manifest records and continues after per-record failures.
- It checks manifest path identity, inventory symbol identity, file content symbol identity, size, row count, hash, schema, session, history, duplicate assignments, and alternatives.

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
