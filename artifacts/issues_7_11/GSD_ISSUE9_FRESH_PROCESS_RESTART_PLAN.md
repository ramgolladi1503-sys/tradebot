# GSD execution — Issue 9 fresh-process restart replay

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Exercise durable OHLC restoration across two independent interpreters
**scope:** Test-only process-boundary proof of the existing trusted-tick persistence bridge and C1 warm-start.
**requested_paths:** `tests/core/test_market_session_runtime_bridge.py`
**allowed_paths:** requested test, this plan, Hermes contract, and Issues 7–11 evidence artifacts.
**forbidden_paths:** production runtime code, live process interaction, broker/order/risk/feed changes, credentials, strategy thresholds, token-universe configuration.
**expected_tests:** writer subprocess plus independent reader subprocess; existing bridge/store regression suite.
**acceptance_proof:** exact completed bars are reopened/restored in the second interpreter and the actual C1 evaluator returns the expected deterministic result using explicit fresh synthetic cycle-time evidence.

## Plan

1. Give both subprocesses temporary `DB_ROOT` and `DATA_ROOT` values to prevent touching repository runtime storage.
2. In the writer process, instantiate the store at the test path, install the existing bridge, and feed deterministic ticks through `_ingest_trusted_ltp_tick` until 30 completed bars have been committed.
3. Exit the writer process normally, modeling clean process termination after completed writes.
4. In a separate reader process, initialize a new store and bridge against the same temporary database, restore completed bars into a fresh buffer, and call the actual C1/C2 evaluator with explicit fresh synthetic cycle evidence.
5. Assert exact count and first/last timestamps, qualified C1 result, and zero order/broker authority; then run the bridge/store focused suite.

## Limits

This is a separate-process deterministic replay, not a managed service lifecycle test, crash-at-arbitrary-instruction test, power-loss proof, capture parity, or live verification. No production behavior/schema change is included.
