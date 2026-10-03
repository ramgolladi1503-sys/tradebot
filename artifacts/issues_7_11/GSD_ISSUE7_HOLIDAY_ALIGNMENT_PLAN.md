# GSD execution — Issue 7 shared NSE F&O holiday calendar

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Align shared session/expiry holiday membership with NSE F&O preflight
**scope:** Shared 2026 NSE F&O holiday source and its existing session-state/expiry consumers.
**requested_paths:** `core/market_calendar.py`, `scripts/run_market_event_graph_live_session_v1.py`, `tests/test_market_session_state.py`, `tests/test_market_event_graph_live_session_preflight.py`, `tests/test_expiry_selection.py`, `tests/test_market_heritage_graph.py`
**allowed_paths:** requested paths, this plan, the Hermes alignment contract, and Issues 7–11 evidence artifacts.
**forbidden_paths:** broker/order/risk/feed behavior, credentials, strategy thresholds, token-universe configuration, T-1 value generation/staging, runtime network access.
**expected_tests:** shared/preflight holiday parity, Jan 15 amendment, March 3 closed session, expiry date exclusion, Issue 7 calendar predecessor and mutation tests.
**acceptance_proof:** exact versioned holiday dates are imported by preflight and included in shared membership; session and expiry consumers reject March 3; all focused regressions and targeted mutation harness pass.

## Execution plan

1. Define the 2026 NSE F&O holiday set and source URL once in `core.market_calendar` from the official NSE circular, including the January 15 amendment.
2. Union these dates into existing shared holiday membership without removing the existing conservative dates.
3. Replace the duplicate preflight holiday set/source with imports from the shared module.
4. Add consumer tests for every shared official date, the January amendment, March 3 closed-state behavior, and expiry-date exclusion.
5. Rerun the heritage graph tests and Issue 7 mutation harness. Validate diff scope, graph, verdict, and manifest.

## Execution result — 2026-10-03

- Focused command: `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_market_session_state.py tests/test_market_event_graph_live_session_preflight.py tests/test_expiry_selection.py tests/test_market_heritage_graph.py` → **81 passed, 1 warning in 9.61s**.
- Mutation command: `PATH=/tmp/tradebot-test-python-bin:$PATH python3 scripts/verify_issues_7_11_issue7_mutations.py` → **5/5 killed**; all three existing T-1 assembler mutants and both calendar arithmetic mutants were killed. The harness verifies unchanged checkout source and test hashes.
- First mutation attempt after the new calendar test import failed during harness collection because its `PYTHONPATH` omitted the repository root. The runner was corrected to expose the repository after the temporary copy; the full five-mutant rerun then passed.

## Limits

This fixes a proven 2026 mismatch only. It does not certify calendar completeness for other years, supply the missing 2026-09-30 futures bar, alter T-1 data authority, or prove live session behavior. Preserve overall Issue 7/campaign verdict as open.
