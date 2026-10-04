# GSD execution — Issue 7 calendar edges

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Test Monday/weekend and exchange-holiday T-1 predecessor resolution
**scope:** Offline tests of the existing explicit `resolve_previous_eligible_session` contract.
**requested_paths:** `tests/test_market_heritage_graph.py`
**allowed_paths:** requested test, `scripts/verify_issues_7_11_issue7_mutations.py`, this plan, Hermes contract, and Issues 7–11 evidence artifacts.
**forbidden_paths:** production source/runtime wiring, external data files, broker/order/risk/feed paths, credentials, strategy thresholds, token-universe configuration.
**expected_tests:** both calendar edge cases pass; a temporary date-arithmetic mutant is killed; all existing Issue 7 mutations remain killed.
**acceptance_proof:** exact returned predecessor dates are Friday for Monday and Monday for the post-holiday Wednesday; only records marked eligible and verified may be selected; checkout source/test hashes stay unchanged during mutation.

## Execution plan

1. Add parameterized fixtures with full calendar identity and explicit eligible/ineligible session records.
2. Add a temporary-copy mutation replacing `max(eligible_dates)` with target-minus-one-calendar-day logic; require the new behavior test to fail.
3. Extend the harness to verify source and test hashes, reject setup errors/timeouts, and retain its existing assembler mutants.
4. Run the calendar test, complete focused Issue 7 heritage tests, and mutation harness.

## Execution result — 2026-10-03

- Calendar edge and existing gap tests: `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_market_heritage_graph.py::test_previous_eligible_session_skips_weekends_and_exchange_holidays tests/test_market_heritage_graph.py::test_previous_eligible_session_skips_calendar_gaps_without_date_arithmetic` → **3 passed, 1 warning**.
- Full `tests/test_market_heritage_graph.py` → **69 passed, 1 warning in 5.74s**.
- Mutation harness: `PATH=/tmp/tradebot-test-python-bin:$PATH python3 scripts/verify_issues_7_11_issue7_mutations.py` → **5/5 killed** (three existing assembler guards plus Monday/weekend and exchange-holiday naive date arithmetic); source and test hashes unchanged.

## Limits

No calendar provider, runtime staging, or prerequisite values are changed. This does not validate external calendar completeness or source-data authority; Issue 7 remains fail-closed where those authorities are absent.
