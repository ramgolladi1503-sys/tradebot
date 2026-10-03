# GSD Plan — Scenario A Completed-Bar Store Composition

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS
**title:** Verify one durable completed bar alongside the synthetic T-1 clean boot path
**scope:** isolated offline integration test and evidence updates only
**allowed_paths:** `tests/test_market_heritage_graph.py`, this plan, the Hermes addendum, and campaign evidence artifacts
**forbidden_paths:** production runtime, strategy semantics, candidate/ranking, broker/order/risk/feed gate changes, credentials, token universe, live/paper enablement
**expected_tests:** focused Scenario A test; heritage/market-session-store regression as needed
**acceptance_proof:** public store write and fresh-instance read verify exactly one completed fixture bar with valid integrity before healthy pulse dispatch reaches all three real shadow adapter methods; authority remains closed

## Execution

1. Retain existing synthetic pinned T-1 manifest and actual loader/registry/pulse dispatch.
2. Before dispatch, persist one deterministic 09:15 IST NIFTY bar with a 09:16 completion cutoff through `MarketSessionStore.persist_completed_bar`.
3. Reopen the isolated SQLite store, require integrity PASS, and read the one completed bar at 09:16.
4. Keep the test's explicit limits: no adapter consumes this store in the fixture; no live source, candidate eligibility, trade, or edge claim.
5. Run the focused Scenario A test and the relevant market-session-store tests.

## Verification

`PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_market_heritage_graph.py::test_scenario_a_verified_t1_clean_boot_reaches_shadow_evaluators tests/core/test_market_session_store.py` → 19 passed, 1 warning. Fresh-store read returned the completed fixture row and integrity PASS. The adapter fixture does not consume the store.
