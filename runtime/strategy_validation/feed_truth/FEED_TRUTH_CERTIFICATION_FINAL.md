# Feed Truth Certification Final Report

## Scope
This report certifies Layer 2 feed truth propagation: from subscription state to real tick/depth freshness, through candidate-local feed truth, executable firewall, and ranking/UI output.

## Phase 1: Wiring Audit
- Explored `core/executable_truth.py`, `core/kite_depth_ws.py`, `core/feed_health_truth.py`.
- Found that feed mutation was fixed in PR #641, and we needed to enforce strict CandidateFeedTruth at the opportunity level.

## Phase 2: CandidateFeedTruth Contract Tests
- Implemented `core/feed/candidate_feed_truth.py`.
- Enforces strict rules: no fake bid/ask, no synthetic data, blocks when fallback used.
- Tests added: `tests/test_candidate_feed_truth.py`, `tests/test_executable_truth.py`.
- Re-wired `core/executable_truth.py` to route through candidate feed truth.

## Phase 3: UI Table Audit
- Validated `core/opportunity_ranking.py` read-only output forces `final_rank_score = 0.0` when `advisory_only` is true.
- Modified `core/canonical_ranked_ui_adapter.py` to enforce `advisory_only` explicitly on fallback data.
- Added tests `tests/test_canonical_ranked_ui_adapter.py`.

## Phase 4: Replay Verifier
- Created `scripts/verify_feed_truth_from_parquet.py`.
- Ran against `.runtime/market_data/upstox_ticks_20260708_123519.parquet`.
- Result: 96,871 rows processed. 100% of fallback quotes blocked correctly. Execution firewall fully functional.

## Verdict
- Status: PASS
- All strict data boundaries are respected. Advisory rows cannot leak into executable paths.
