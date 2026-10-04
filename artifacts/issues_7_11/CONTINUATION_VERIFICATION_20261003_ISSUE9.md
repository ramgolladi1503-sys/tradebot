# Issue 9 continuation verification — 2026-10-03

**source_agent:** gsd
**action:** UPDATE_DOCS
**scope:** durable completed-bar memory bridge to C1/C2
**repository start SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**branch:** `ram/issues-7-11-graph-repair`

## Changed behavior

- The existing `market_session_memory_contract.install()` now returns explicit install/store/buffer status and reattaches the singleton `OhlcBuffer` if the wrapper was installed earlier.
- The legacy market-data cycle explicitly installs the bridge before its market-data fetch. The normal fast cycle delegates into this legacy `run_once` path through `FastExecutionEngine`.
- C1/C2 requests a durable snapshot for its explicit normalized symbol and event-time cutoff. The store reads verified completed rows for that same session, requires the 09:15 session-open bar and a complete one-minute sequence through the cutoff, and derives its features from those rows.
- Current freshness comes only from the cycle row's explicit `valid is True` and `time_sanity.ok is True`. Durable history cannot refresh a stale current feed.
- Removed the fabricated empty-store snapshot values and default bar count. Store absence, corruption, incomplete history, or mismatch returns no C1/C2 result and emits a debug diagnostic.
- Evaluator thresholds, windows, ranking, token universe, feed/risk gates, and order/broker authority were not changed.

## Tests and validation

- Focused command: `pytest -q tests/core/test_market_session_runtime_bridge.py tests/core/test_market_session_store.py tests/test_c1_c2_regime_decoupling.py tests/test_primary_runtime_c1_c2_integration.py tests/test_market_event_graph_live_ohlc_buffer.py tests/test_candidate_feed_dependencies.py tests/test_edge45_symbol_execution_safety.py`
- Focused result: `85 passed, 1 warning in 3.31s`.
- Certification: `PYTHONPATH=. python3 scripts/certify_market_session_memory.py --output /tmp/issues_7_11_market_session_memory_certification.json` → `10/10 gates passed`.
- Broad command: `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q --ignore=tests/test_upstox_daily_live_capture.py --ignore=tests/trade_truth/test_raw_tick_expected_separation.py -k 'not test_v5_verifier_deep_primitive_validation'`.
- Broad result: `8596 passed, 9 skipped, 29 deselected, 1474 warnings in 787.02s`.
- Exclusions: Upstox capture test requires unavailable `upstox_client`; raw-tick test scans the large external stitched capture; the V5 primitive verifier was excluded after stalling on an external stitched-capture read in an earlier run.
- `validate_registry_entries()` returned `()` after updating the exact store and orchestrator digests. `git diff --check` and JSON parsing passed after test-artifact cleanup.

## Independent verification / limitations

Code review confirms the durable snapshot is selected by exact symbol and same-session date, persistence's completion cutoff is retained, completeness/gap checks precede feature derivation, and `freshness_watermark` is supplied independently of stored bars. Failure paths return no candidates; no alternate synthetic snapshot remains. The generic in-memory API used by analytics/replay was left intact.

This is deterministic offline evidence. No production service restart, captured/live C1/C2 parity, current runtime storage-path availability, or C2 exact signal-bar parity was observed. Those claims remain unverified; this repair does not authorize LIVE or PAPER execution.
