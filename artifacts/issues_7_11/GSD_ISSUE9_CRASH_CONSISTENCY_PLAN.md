# GSD execution — Issue 9 abrupt writer termination

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Test rollback after abrupt process termination during completed-bar persistence
**scope:** Test-only crash-consistency check for `MarketSessionStore.persist_completed_bar`.
**requested_paths:** `tests/core/test_market_session_store.py`
**allowed_paths:** `tests/core/test_market_session_store.py`, this plan, Hermes contract, and Issues 7–11 evidence artifacts.
**forbidden_paths:** production runtime code, broker/order/risk/feed paths, credentials, strategy thresholds, token-universe configuration.
**expected_tests:** exact targeted test below, then the complete store test module.
**acceptance_proof:** subprocess reaches actual insert, exits abruptly before the SQLite connection context commits, database reopens without the row, and `PRAGMA integrity_check` is `ok`.

## Execution

1. Create a temporary session database in the test's `tmp_path`.
2. Spawn a child Python process that initializes `MarketSessionStore`, wraps that instance's connection context so `os._exit(73)` occurs after the actual persistence method executes its SQL insert but before the original context manager exits, and calls `persist_completed_bar` with a completed deterministic bar.
3. Assert exit status 73, reopen through a new store instance, assert the bar is absent, and assert SQLite integrity is `ok`.
4. Run the exact crash test and the full store module.
5. In a temporary source copy, insert an early `conn.commit()` immediately after the actual bar INSERT. The crash test must fail because the row persists; the harness must reject collection errors/timeouts and compare checked-out hashes before/after.

## Limits

This proves one process-termination point in the existing SQLite transaction. It does not cover OS/power failure, disk/controller cache behavior, actual observer service restart, captured data parity, or every concurrent writer race. No production behavior or schema is changed.
