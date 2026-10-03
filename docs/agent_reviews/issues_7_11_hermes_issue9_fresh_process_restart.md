# Hermes contract — Issue 9 fresh-process restart replay

**source_agent:** hermes
**action:** DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Verify durable OHLC bridge recovery across independent Python processes
**scope:** Offline deterministic replay through the existing trusted tick ingestion, runtime bridge, SQLite store, restored buffer, and C1 evaluator.
**requested_paths:** `tests/core/test_market_session_runtime_bridge.py`
**allowed_paths:** the requested test file, this contract, its GSD plan, and Issues 7–11 evidence artifacts.
**forbidden_paths:** production runtime code, live process interaction, broker/order/risk/feed changes, credentials, strategy thresholds, token-universe configuration.
**expected_tests:** writer subprocess persists completed bars through the real bridge, exits; a fresh reader subprocess installs a new bridge/store, restores exact completed bars, and evaluates C1 with separately supplied fresh synthetic current-cycle time evidence.
**acceptance_proof:** writer and reader are distinct processes; test uses only a temporary database; recovered completed-bar count/bounds and C1 result match the deterministic replay expectation; closed order/broker authority remains unchanged.

## Invariants and limits

Persisted bars supply historical memory only. The reader process must separately supply an explicit fresh current-cycle timestamp to the evaluator; restored history cannot certify current feed freshness. Deterministic test ticks must retain deterministic-test provenance and must not be represented as captured/live evidence. The test must not alter global project runtime paths or inspect the canonical checkout's live processes.

This is a fresh-interpreter restart replay, not a managed service restart or captured/live parity proof. No source/runtime behavior change is authorized.
