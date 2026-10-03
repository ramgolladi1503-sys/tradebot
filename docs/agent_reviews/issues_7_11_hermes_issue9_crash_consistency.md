# Hermes contract — Issue 9 abrupt writer termination

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
**title:** Verify completed-bar insert atomicity under process death
**scope:** Offline test of the existing `MarketSessionStore.persist_completed_bar` SQLite transaction boundary.
**requested_paths:** `tests/core/test_market_session_store.py`
**allowed_paths:** `tests/core/test_market_session_store.py`, this contract, its GSD plan, and Issues 7–11 evidence artifacts.
**forbidden_paths:** production runtime code, broker/order/risk/feed paths, credentials, strategy thresholds, token-universe configuration.
**expected_tests:** child process performs the real store insert and exits without unwinding the SQLite connection context; a fresh store must expose no row and SQLite integrity must remain `ok`.
**acceptance_proof:** subprocess exits using the designated abrupt status after `persist_completed_bar` reaches the insert; reopening shows no completed bar and an integrity check succeeds.

## Invariant and risk boundary

The existing store relies on SQLite's transaction context to commit only after `persist_completed_bar` leaves its connection context. If the process terminates after the SQL insert but before context exit, SQLite must roll back the uncommitted row during recovery. The test must exercise the actual public persistence method, not reimplement its SQL. It is deterministic offline evidence of SQLite crash recovery for this interruption point; it does not prove power-loss behavior on every filesystem, a running-service restart, or captured/live parity.

No source behavior, authority, or persistence schema changes are authorized. The child process is isolated to a temporary database and cannot invoke broker or order paths.

## Mutation contract

In a temporary source copy only, sabotage the transaction boundary by committing immediately after the completed-bar INSERT and before leaving the connection context. The designated crash test must fail because the row survives the subsequent abrupt exit. The harness must reject timeouts, collection errors, and unrelated failures and verify that checked-out source/test bytes are unchanged. This tests the oracle's sensitivity; it is not a production patch.
