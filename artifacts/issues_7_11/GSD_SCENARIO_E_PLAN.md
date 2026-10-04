# GSD Plan — Scenario E restart + stale required spot + advisory

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, VERIFY, UPDATE_DOCS
**title:** Compose completed-bar restart, stale required spot rejection, and scoped advisory projection
**scope:** offline composition and additive fail-closed receipt metadata under `docs/agent_reviews/issues_7_11_hermes_scenario_e.md`
**allowed_paths:** `core/read_only_consumer_cycle.py` (all CAS output authority metadata only), `tests/test_issues_7_11_scenario_b_restart.py`, `tests/test_read_only_consumer_cycle.py`, this plan, and listed Issues 7–11 evidence artifacts
**forbidden_paths:** all other production code/config, strategy/feed/risk/broker/order behavior, credentials, live processes, token universe, PR #936
**expected_tests:** actual reopened store/memory reader; actual producer stale-spot gate and CAS evaluator; actual advisory builder with an explicit valid-empty source; exact closed-authority assertions on the gate, PENDING/PASS states, writable readiness receipts, and advisory artifact
**acceptance_proof:** focused Scenario E test passes; stale required spot creates no CAS artifact despite restored bars; advisory is zero-row from the exact supplied ledger; graph and manifest hashes verify; `git diff --check` clean

## Execution steps

1. Add the complete closed-authority tuple to every CAS state, readiness receipt, and advisory artifact. Do not retry a readiness write after ledger completion itself fails. Preserve CAS decision/reason behavior.
2. Reuse the existing Scenario B fixture that persists deterministic-test completed bars, reopens the SQLite store, and loads verified same-day synthetic heritage.
3. Make the current NIFTY quote unhealthy in the actual runtime snapshot producer path; preserve its existing feed/identity checks.
4. Use the actual advisory projection with an explicit valid-empty candidate-decision file, not a mocked row payload.
5. Assert restored bar memory exists, CAS is blocked and produces no artifact, advisory source path is exact and row count is zero, and authority remains closed. Exercise missing, malformed, duplicate, write-failure and incomplete-completion PENDING exits.
6. Run Scenario E, then Scenario B and directly related producer/store/advisory/CAS tests.
7. Update graph, cross-issue results, attack/evidence ledger and source manifest. Keep the overall campaign verdict false/open.

## Rollback and risk

The production changes add closed-authority metadata to CAS outputs; evaluation and execution decisions stay unchanged. Do not loosen production gates or infer source authority from synthetic bars/CAS fixtures. A failed assertion is investigated without weakening the contract.
