# Opening Range Retest Latest-Main Integration

IMPLEMENTATION DIRECTION: RIGHT_WITH_GAPS

WORKTREE: /Users/madhuram/tradebot-orb-latest-main-integration

BRANCH: integration/opening-range-retest-latest-main

APPROVED OBJECTIVE: Safely integrate the completed `opening_range_retest_v1` owner-authority branch against the latest `origin/main`, verify compatibility with PR #657 and PR #658, and preserve the accepted ORB owner semantics without changing strategy formulas, thresholds, completed-history semantics, ranking, TradeBuilder, Phase 1, Phase 2, broker, execution, or risk code.

WHAT WAS ACTUALLY IMPLEMENTED: Created a clean integration worktree from `origin/main`, merged `origin/fix/opening-range-retest-owner-integration`, resolved one mechanical test conflict in `tests/test_htf_real_paper_monitor.py`, and corrected a merge regression in `core/market_data.py` where the new completed-history wiring referenced a nonexistent `now` variable. The integrated tree preserves the ORB durable-owner boundary, the PR #657 canonical completed-bar contract, and the PR #658 test-tiering policy.

ARCHITECTURE CHANGE: NONE

CURRENT_ORIGIN_MAIN_HEAD: `58881fd873c307df3adaa5402ed27936573a1873`

CURRENT_ORB_REMOTE_HEAD: `c8067877dc004f21aa2e4506643fbeb164d46588`

MERGE_BASE: `691b8a750e805c0acffb7543e3f5b3cede2ee6d9`

PR #657 COMPATIBILITY:
- `origin/main` contains PR #657 by ancestry at `58881fd8`.
- Baseline compatibility slice on the `origin/main` worktree passed: `74 passed`.
- The integration candidate passed the same canonical-history slice after the merge fix: `74 passed`.
- Representative files verified: `core/market_data.py`, `core/market_data_warmup_contract.py`, `core/ohlc_buffer.py`, `tests/core/test_canonical_strategy_input_truth.py`.

PR #658 COMPATIBILITY:
- `origin/main` contains PR #658 by ancestry through `3e1e6d9b`.
- The feed tiering policy test passed in the integration candidate: `tests/test_feed_soak_tiering_policy.py` -> `79 passed`.
- ORB test collection remained in the normal deterministic tier: `52 tests collected` across `tests/test_opening_range_retest_owner_integration.py` and `tests/test_opening_range_retest_temporal_fixture_contract.py`.
- Representative files verified: `pytest.ini`, `tests/conftest.py`, `.github/workflows/feed-smoke.yml`, `.github/workflows/feed-resource-soak.yml`.

CONFLICTS ENCOUNTERED:
- One content conflict occurred in `tests/test_htf_real_paper_monitor.py`.
- Conflict classification: `TEST_EXPECTATION`.
- Resolution: keep the existing restart assertion and preserve the added exact-string round-trip coverage for `signal_id`.
- A merge regression in `core/market_data.py` was uncovered by the focused canonical-history slice and fixed by using `cycle_cutoff` instead of an undefined `now`.

CANONICAL-HISTORY TEST RESULTS:
- `python -m pytest -q tests/core/test_canonical_strategy_input_truth.py tests/test_market_data_index_quote_cache.py tests/test_market_data_warm_seed.py tests/test_time_sanity_staleness.py`
- Result on integration candidate after fix: `74 passed`
- Baseline comparison on `origin/main`: `74 passed`

ORB TEMPORAL TEST RESULTS:
- `python -m pytest -q tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_opening_range_retest_temporal_audit.py tests/test_opening_movement_strategies.py tests/test_orb_ohlcv_validation.py`
- Result: `79 passed`

OWNER-AUTHORITY TEST RESULTS:
- `python -m pytest -q tests/test_opening_range_retest_owner_integration.py tests/test_candidate_phase2_ownership.py tests/test_candidate_phase2_semantic_ownership.py tests/test_strategy_context_truth.py tests/test_strategy_profile_fail_closed.py tests/test_strategy_missing_evidence_policy.py tests/test_strategy_missing_evidence_observability.py tests/test_strategy_registry_integrity.py tests/test_feed_soak_tiering_policy.py`
- Result: `103 passed`

CI-TIERING COLLECTION PROOF:
- `python -m pytest --collect-only -q tests/test_opening_range_retest_owner_integration.py tests/test_opening_range_retest_temporal_fixture_contract.py`
- Result: `52 tests collected`

FULL-SUITE RESULT:
- `python -m pytest -q`
- Result on integration candidate: `5997 passed, 3 failed, 24 deselected, 934 warnings`

KNOWN AUTH FAILURE:
- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- Failure text: `RuntimeError: [AUTH] missing_kite_access_token`

ORDER-SENSITIVE / ENVIRONMENT-SENSITIVE FAILURES:
- `tests/test_strategy_pure_signals.py::test_zero_hero_pure_signal`
- `tests/test_strategy_pure_signals.py::test_banknifty_pure_signal`
- Both failures reproduced on the `origin/main` baseline worktree as well, so they are not attributable to the ORB merge candidate.

SUBAGENT FINDINGS:
- Caller inventory audit: production reaches `build_candidate_pool_report(...)` from `core/ranking_orchestrator.py` without an owner store; the ORB owner boundary is therefore bypassed in the current production caller shape and remains a follow-up integration concern.
- Main compatibility audit: `origin/main` already contains PR #657 and PR #658 by ancestry; the audit flagged a potential pytest-tiering clash, but the requested feed-tiering test and ORB collection checks passed in the integration candidate.
- Exactly-once audit: the ORB owner semantics remain consistent with the committed branch behavior; accepted outputs remain singular, restart duplicates do not create a new exposed candidate, and blocked owner states fail closed.

FINAL CLAIM BOUNDARY:
- This integration proves compatibility of the pushed ORB owner-authority branch with the latest `origin/main` plus the merged PR #657 / #658 baseline behavior.
- It does not prove profitability, ranking superiority, execution readiness, live readiness, or production certification.
