# GSD Plan — Scenario F: Missing T-1 End-to-End

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS
**title:** Prove missing T-1 remains blocked through observer registry
**scope:** offline integration test only
**requested_paths:** `tests/paper_shadow/test_t1_scenario_f_missing_manifest.py` and Issues 7–11 evidence artifacts
**allowed_paths:** the listed test and campaign artifacts
**forbidden_paths:** production runtime, strategy logic, broker/order/risk/feed safety, credentials, token universe
**expected_tests:** exact missing-manifest result, all dependent adapters disabled, registry telemetry carries precise source block, injection of legacy values cannot arm adapters
**acceptance_proof:** test invokes the actual loader and registry, asserts all authority flags and order counters, and does not reinterpret synthetic fixture evidence as live proof

## Execution steps

1. Use frozen strategy IDs/contracts and the production observer's instrument identities.
2. Supply no manifest path or pin and use a temporary approved root.
3. Construct the real `StrategyShadowAdapterRegistry` from returned values and verification data.
4. Assert source-level blocker propagation, null T-1 values, disabled adapters, and closed authority.
5. Repeat with fabricated legacy numeric values while the verification report stays blocked; values alone must not arm any adapter.
6. Run the focused test, heritage graph tests, and shadow adapter tests; update graph and verdict only with observed results.

This closes only the offline Scenario F negative path. Issue 7 source authority remains `UNKNOWN`; no positive T-1 availability or live behavior is claimed.
