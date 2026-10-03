# GSD Plan — Issue 11 CAS candidate dependency gate

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Require current exact NIFTY spot health before bridging CAS advisory inputs
**scope:** Execute only the two Issue 11 Hermes contracts listed below.

## Files

Every implementation or evidence file is listed below before execution. The single new config key list is empty; existing `FEED_TRUTH_SNAPSHOT_MAX_AGE_SEC` supplies the snapshot age bound.

- `core/runtime_snapshot_producer.py`: add a pure fail-closed check over the current NIFTY symbol/token, non-executable fresh quote, healthy finite age, and recent timezone-aware snapshot before the existing CAS bridge.
- `docs/agent_reviews/issues_7_11_hermes_issue11_transport_consistency.md`: define that `effective_ws_connected` is authoritative when present, with exact-True legacy fallback only when absent.
- `tests/core/test_runtime_snapshot_producer.py`: provide reusable current-cycle snapshot fixture and actual producer → real CAS evaluator Scenario C and D.
- `tests/core/test_issue11_cas_dependency_adversarial.py`: attack missing/wrong quote identity, non-boolean freshness, executable-quote authority, malformed/non-finite/stale age, missing NIFTY evidence, malformed/naive/future/stale snapshot time, and shared transport loss through the actual producer/evaluator path.
- `scripts/verify_issues_7_11_issue11_transport_mutation.py`: isolated OR-logic mutant proving the contradictory transport regression kills the prior behavior.
- `tests/test_v23_production_equivalent_harness.py`: supply valid current-cycle observer quote evidence in the production-equivalent harness so the strengthened gate is exercised with its declared inputs.
- `artifacts/issues_7_11/defect_graph.json` and `.md`: mark CAS-local spot isolation as offline verified while keeping general candidate isolation and live behavior UNKNOWN.
- `artifacts/issues_7_11/INDEPENDENT_VERIFICATION.md`: record executor tests and limits; do not claim independent certification.
- `artifacts/issues_7_11/FINAL_VERDICT.json`: preserve campaign `implementation_valid=false`, offline campaign false until all gates pass, and `live_verified=false`.

## Execution

1. Add tests first around the actual snapshot producer and `_evaluate_cas` boundary.
2. Validate exact `NIFTY` identity, exact positive integer token equal to both captured primitives, non-executable quote, explicit true freshness, explicit `HEALTHY` domain status, exact finite nonnegative quote age within the existing SLA, and aware recent snapshot generation time bounded by the existing snapshot-age config.
3. Require adversarial malformed and absent evidence at every boundary to block input construction and leave the actual CAS evaluator PENDING without an artifact. When `effective_ws_connected` is present, it must be exactly true; accept the legacy field only when the effective field is absent.
4. Preserve the existing global feed-runtime connected gate and CAS advisory semantics.
5. Emit explicit missing/blocked gate state and reason when inputs cannot be bridged.
6. Run focused producer/CAS/reject-shadow/read-only tests, required-spot-predicate and shared-transport-OR mutants, `py_compile`, `git diff --check`, then broad offline regression.
7. Do not claim generic option-dependent candidate isolation, source identity authority beyond existing primitive validation, or captured/live parity.

## Authority

No shared feed-classifier/producer, generic ranking, candidate registry, strategy calculation, freshness threshold, risk, broker/order, paper/live authority, or token-universe changes. Existing `FEED_TRUTH_SNAPSHOT_MAX_AGE_SEC` is reused; no new config key is planned.
