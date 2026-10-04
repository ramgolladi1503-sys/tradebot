# GSD Plan — Scenario A Verified T-1 Clean Boot

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS
**title:** Prove positive verified-prerequisite wiring through clean shadow boot
**scope:** offline integration test only
**allowed_paths:** `tests/test_market_heritage_graph.py` and campaign artifacts
**forbidden_paths:** production runtime, strategy semantics, candidates/ranking, broker/order/risk/feed gate changes, credentials, token universe, live/paper enablement
**expected_tests:** pinned synthetic T-1 manifest verifies; all three adapters register; healthy pulse dispatch reaches all adapter methods; clean store integrity passes; authority stays closed
**acceptance_proof:** actual publisher, independent verifier, loader, registry, dispatcher, and store are composed; no assertion requires a signal/trade; source authority is explicitly fixture-only

## Execution

1. Reuse `_publish_t1_manifest` in the existing heritage test module rather than duplicating fixture logic.
2. Pass the exact path/hash to `load_verified_t1_prerequisites`.
3. Build the production shadow registry from the returned values/report and dispatch deterministic healthy market evidence.
4. Assert adapter invocation only, not candidate success or trade output.
5. Run the composed test and the heritage, registry, observer, and session-store focused tests.
6. Preserve live T-1 authority as UNKNOWN.
