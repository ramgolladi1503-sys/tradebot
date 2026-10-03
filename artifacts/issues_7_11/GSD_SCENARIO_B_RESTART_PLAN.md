# GSD Plan — Scenario B Mid-Session Restart Composition

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, VERIFY, UPDATE_DOCS
**title:** Compose durable bars and verified CAS inheritance across a simulated restart
**scope:** tests-only offline integration under `docs/agent_reviews/issues_7_11_hermes_scenario_b_restart.md`
**allowed_paths:** `tests/test_issues_7_11_scenario_b_restart.py`, this plan, and listed Issues 7–11 evidence artifacts
**forbidden_paths:** production code/config, strategy thresholds, feed/risk semantics, broker/order/credentials, token universe, PR #936
**expected_tests:** positive inherited-CAS + restored-bar path; cross-date/corrupt/stale-input rejection; closed authority assertions
**acceptance_proof:** focused test passes, adversarial cases reject, graph/evidence JSON parses, `git diff --check` clean

## Execution

1. Reuse `MarketSessionStore`, `CASPrimitiveStore`, `publish_same_session_cas_manifest`, `load_same_session_cas_references`, `produce_and_store_runtime_snapshots`, and `read_only_consumer_cycle._evaluate_cas`; do not hand-build verified outputs.
2. Generate deterministic synthetic hash-bound events in a temporary directory. Simulate restart by reopening the SQLite store and clearing process-local OHLC state.
3. Require exact same-day session, NIFTY token identity, causal event times, completed-bar cutoff and synthetic fresh exact current spot evidence at the existing 15:14 CAS boundary. Preserve the real C1 out-of-window result at that time; rely on the existing 09:45 restart test for in-window C1 qualification.
4. Exercise cross-date, corrupted and conflicting heritage; stale and mismatched spot; pre-cutoff CAS; and incomplete/future completed bars as negative paths. Keep read-only/advisory authority closed.
5. Run only the focused scenario first, then its directly touched CAS/bar/evaluator regression tests.
6. Update campaign artifacts with exact command/result and explicit offline-only limits. JSON/evidence parsing and `git diff --check` are verification steps to record after execution; do not claim captured/live parity or close the campaign.

## Rollback surface and risk

Only a new offline test and campaign evidence are expected. A failing test is retained as evidence and investigated; no behavior assertions may be weakened. Temporary fixtures are isolated under pytest `tmp_path`.
