# ORB Phase 1 Source Provenance Audit v1

## Agent Work Contract
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
- JSON artifact SHA-256: `96c71c70c727db2ba0335f6a44ff20d3f24cb9b0b3ce302545d8f914f213b2d0`
- Decision: `AUDIT_INVALID`
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
- candidate blast radius: `{"affected_candidate_count_from_defective_source_profiles": 13, "affected_candidate_count_from_records": 23, "affected_candidate_count_from_summary": 13, "affected_candidate_count_method": "exact_defective_source_profile_emission_count", "affected_candidate_directions": {"BUY_CALL": 17, "BUY_PUT": 6}, "affected_candidate_ids": [], "affected_candidate_ids_note": "Candidate ledger entries do not retain source logical_path; session-symbol ledger match is an upper bound.", "affected_candidate_sessions": {"2026-07-06": 2, "2026-07-07": 5, "2026-07-08": 3, "2026-07-09": 9, "2026-07-10": 4}, "affected_candidate_symbols": {"NIFTY": 23}, "affected_session_symbol_keys": [["2026-07-06", "NIFTY"], ["2026-07-07", "NIFTY"], ["2026-07-08", "NIFTY"], ["2026-07-09", "NIFTY"], ["2026-07-10", "NIFTY"]], "candidate_semantic_hash_survives": false, "corrected_ids_computable": false, "defective_source_profiles": [{"emission_count": 2, "logical_path": "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet", "session_date": "2026-07-06", "symbol": "NIFTY"}, {"emission_count": 3, "logical_path": "runtime/upstox_candidate_replay/20260707/underlying/NSE_INDEX|Nifty Bank_20260707.parquet", "session_date": "2026-07-07", "symbol": "NIFTY"}, {"emission_count": 2, "logical_path": "runtime/upstox_candidate_replay/20260708/underlying/NSE_INDEX|Nifty Bank_20260708.parquet", "session_date": "2026-07-08", "symbol": "NIFTY"}, {"emission_count": 3, "logical_path": "runtime/upstox_candidate_replay/20260709/underlying/NSE_INDEX|Nifty Bank_20260709.parquet", "session_date": "2026-07-09", "symbol": "NIFTY"}, {"emission_count": 3, "logical_path": "runtime/upstox_candidate_replay/20260710/underlying/NSE_INDEX|Nifty Bank_20260710.parquet", "session_date": "2026-07-10", "symbol": "NIFTY"}], "ledger_records_available": true, "old_ids_available": true, "reason": "wrong-symbol source records fed candidate generation, so affected setup ids and full candidate semantic hash cannot be reused", "session_symbol_candidate_upper_bound": 23, "session_symbol_candidate_upper_bound_ids": ["3d11e3041f4ebff85a5e2ef920a89b1a3207c9805dc6c1ae5843420be0c18f6b", "d2eba488c3d3e7b55895f75f8b0f5ea909d8261766f8798511b2223ddfd3067c", "338caffc53cd9c3ec9d8f57ef225dc4e5bc1aeb07046709d621305982122f0e4", "1df51d93e349f013ab3a30bd16d01f17c3d2cfa788246433c3cc6d468544d45e", "c1d80124b8ee755b9a0b4bf003778fb7d0e903092aa143c5202678284c87b160", "eca7e541ae98515ba314477c218c761242a12602fc301aa139804d70039cacc4", "6a0f5a2e4e5c07c3850455af8c29fc8e3a3d2505b16dbecfaebec8df229c0ee4", "ed639e86ca944284bdcdafc4195dcc407ef52d74879ef62bdd517eea00d18014", "cb4ea05702383706b698b0953b08e947596d5e95e5b7aea6aec3522f55867715", "359eb64c572d75d1841a4dd2ea5c4d97a7009007f457b3a52f322b3d8b218075", "9724d334b3b9ee3baa56da26d6db02175f5645e8e55777adf4b1557fa2b0d95a", "b78fbb0e5d01560be960a6b6ea66a96429f9dd1c181174bcb9208a66a34f5e61", "2824763359af48691d16f6ff5b1ccf4bf0066aae09117f8ef8bfcb1c0746af25", "43f9b1247765b5bdcb30f9c0070c748bbde94a2003811e3ae7898bbe18a278fd", "9fedd66ce4698e79e3b004cdbf4a3cf93d58ab56aa05d44ff1d77672ccb18120", "7e132a798ea432a25a2236e299b0df8667119763bafc3956fe3a847665f27347", "f3aa1849bd9aa9f2ca5efcd7b12c22510a70200b750bfa8731edac4a453c8c3e", "87073bbb46e7bb70838d9d98cb34d7d96851a8d4259e6f3d8b92e246fd7bd21d", "cb37d14a1aa980f34d1b17f3cbeed7e9e799f4a169d1a1d1d939a2cd16f20860", "dbed8da0ea8b5c94ce08b35db5250dc06ae0c95eec74a91585313bcddb187ba9", "1e90c2403b84dff0015ad96043e3e2c94943f33c7369245a5e50c26c25a07cd0", "dd7785f7ef013a0d85b4559b26733b9d5ae8ef05caad53147b5c50ebaf5e0e9f", "29250e4b16a4df9e28572df3696073b56fe418dd576cd366071b0f1292494154"], "unaffected_candidate_count": 2192, "unaffected_candidate_directions": {"BUY_CALL": 1087, "BUY_PUT": 1105}, "unaffected_candidate_symbols": {"BANKNIFTY": 738, "NIFTY": 729, "SENSEX": 725}, "unaffected_subset_semantic_hash": "b0b41a1ac6844fa670151c6bd6020eabf8ca592ea4a2e2cdda6f09ea48719669"}`

## Runtime Proof Required After Merge
- No runtime proof is claimed by this PR.
- If source provenance is corrected later, rerun the ORB Phase 1 replay and independent audit from exact merged main before making outcome claims.

## What This PR Does Not Prove
- It does not prove ORB profitability, fills, live readiness, broker behavior, paper readiness, or corrected candidate outcomes.
- It does not mutate source data or certify PR #674 outcome artifacts.

## Human Approval
- Required before any future source substitution, v2 replay recertification, or outcome claim restoration.

## Final Verdict
`AUDIT_INVALID`
