# GSD Plan — Scenarios C/D Read-Only Health Consumer

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS
**title:** Compose stale option and stale underlying health at the observer boundary
**scope:** tests-only offline producer-to-shadow-consumer integration
**allowed_paths:** `tests/paper_shadow/test_issue11_scenarios_cd.py` and campaign artifacts
**forbidden_paths:** production runtime, shared classifiers, candidate/ranking semantics, broker/order/risk, credentials, token universe
**expected_tests:** option-domain degradation with healthy exact spot remains observer-only healthy; stale spot and transport failure remain degraded; stale option snapshot remains degraded
**acceptance_proof:** test uses actual feed-health payload builder and snapshot builder; asserts exact identity, closed authority, no executable claim; independent verifier checks this boundary and limitations

## Execution

1. Use actual `build_feed_health_truth_latest_payload` output and actual `StrategyMarketSnapshotBuilder`.
2. Exercise Scenario C (healthy spot, stale options) and Scenario D (stale required spot), plus shared transport failure.
3. Assert only the observer snapshot health contract; do not infer candidate/evaluator isolation.
4. Run the scenario test and existing observer/feed safety suites; update graph/verdict with bounded claim.
