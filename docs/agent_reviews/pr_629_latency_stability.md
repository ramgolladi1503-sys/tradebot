# PR 629: Latency Stability and JIT Quote Revalidation

## Agent Work Contract

- source_agent: Antigravity
- action: LATENCY_STABILITY_FIX
- title: Implement Splitting Quote Freshness & Just-In-Time Revalidation and move heavy IO out of cycle critical path
- scope: orchestrator
- requested_paths: core/orchestrator.py, tests/test_jit_quote_revalidation.py
- allowed_paths: core/orchestrator.py, tests/test_jit_quote_revalidation.py
- forbidden_paths: main.py, .env, run_live.sh
- expected_tests: tests/test_jit_quote_revalidation.py
- acceptance_proof: CI passes and test_jit_quote_revalidation.py proves safe block of stale quotes.

## Scope Guard

This PR is strictly limited to latency safety improvements inside the `_legacy_live_monitoring` loop of `core/orchestrator.py`. No logic changes were made to broker calls, order actions, or actual strategy decision thresholds.

## High-Risk Path Review

- `core/orchestrator.py`
We changed how and when candidates are marked as executable by injecting a Just-In-Time (JIT) quote revalidation block right before the `execution_guard.evaluate` check. If the final executable quote age is > 2.5s, the candidate is blocked. We also moved heavy telemetry logging (`produce_and_store_runtime_snapshots`) to the very end of the cycle.
Is it safe? Yes, this enforces strict latency cutoffs for execution while preserving observability.

## Grill Me Review

- **Q: Does this change what we trade?**
  A: It strictly prevents trading on stale data. No new trades are allowed that wouldn't have been allowed before, only stale trades are blocked.
- **Q: Does this break cycle timing?**
  A: No, moving the heavy IO down actually improves critical path timing.

## Hermes Review

The execution pipeline architecture remains fail-closed. Telemetry hooks for `cycle_processing_latency_ms` and `final_quote_revalidation_age_ms` were cleanly added into the existing `update_execution` structure.

## GSD Review

Plan was executed. Mocks were explicitly isolated in a new robust test file `tests/test_jit_quote_revalidation.py` to prove both the block-on-stale and allow-on-fresh paths.

## QA / Safety Review

- Broker API called = false
- Order action = false
- Live config change = false

## Acceptance Proof

```
pytest -q tests/test_jit_quote_revalidation.py
3 passed
```

## Runtime Proof Required After Merge

Verify that `logs/main.log` shows `"execution_guard_trade_blocked reason=stale_final_executable_quote age=..."` when quote lag spikes above 2.5s. Also verify that dashboard snapshots continue to update normally.

## What This PR Does Not Prove

- This PR does NOT prove broker API stability.
- This PR does NOT prove strategy profitability.

## Human Approval

Approved by user for merge to resolve leftover latency stability refactoring.

## Runtime Traceability Check
- mode=N/A
- candidate_id=N/A
- decision=N/A
- reason=N/A
- timestamp=N/A
- is_order_action=false
- broker_api_called=false
- source=Antigravity
