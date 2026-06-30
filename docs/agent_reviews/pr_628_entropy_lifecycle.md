# PR 628: Entropy Gating and Strategy Lifecycle Safety

## Agent Work Contract

- source_agent: Antigravity
- action: ENTROPY_LIFECYCLE_SAFETY_FIX
- title: Fix entropy gating and strategy lifecycle labels
- scope: market_data, orchestrator, ci_finish
- requested_paths: core/market_data.py, core/orchestrator.py, core/ci_finish_contracts.py, tests/test_entropy.py, tests/test_strategy_lifecycle_labels.py
- allowed_paths: core/market_data.py, core/orchestrator.py, core/ci_finish_contracts.py, tests/test_entropy.py, tests/test_strategy_lifecycle_labels.py
- forbidden_paths: core/kite_depth_ws.py, scripts/tick_data_collector.py
- expected_tests: tests/test_entropy.py, tests/test_strategy_lifecycle_labels.py
- acceptance_proof: 29 passing tests and evidence that SENSEX/BANKNIFTY do not get dropped on high entropy for range policies

## Scope Guard

This PR is strictly limited to fixing the false entropy starvation logic and lifecycle labelling, by passing `symbol` and `primary_regime` to the entropy gate properly.

## High-Risk Path Review

- `core/market_data.py` / `core/orchestrator.py`
We changed how `_derive_unstable_reasons` handles regime entropy. The logic delegates threshold overrides back to `evaluate_regime_entropy_gate`. This fixes false rejections on high-entropy range regimes.
Is it safe? Yes, no orders are placed. Fail-closed safety remains intact for non-range regimes.

## Grill Me Review

- **Q: Does this weaken entropy restrictions?**
  A: No, it correctly enforces the pre-existing RANGE_OVERRIDE for RANGE and RANGE_VOLATILE regimes, while preserving the strict 0.80 cutoff for directional regimes.
- **Q: Did we leak edge tests here?**
  A: No, edge tests are forbidden and absent from this PR.

## Hermes Review

Architecture remains identical. We just synchronized the internal method signatures for market snapshot diagnostic wiring.

## GSD Review

Plan was executed. Mocks were explicitly removed in favor of `ci_finish.install()` and `TradeBuilder` usage for integration test confidence.

## QA / Safety Review

- Broker API called = false
- Order action = false
- Live config change = false

## Acceptance Proof

```
pytest -q tests/test_entropy.py tests/test_strategy_lifecycle_labels.py tests/test_ranking_orchestrator.py tests/test_jit_quote_revalidation.py tests/test_audit_phase_b_jit.py
29 passed
```

## Runtime Proof Required After Merge

Verify that `logs/main.log` shows NIFTY generating `entropy_too_high` during unstable directional regimes, while SENSEX/BANKNIFTY in RANGE smoothly transition past the gate without false rejections.

## What This PR Does Not Prove

- This PR does NOT prove strategy edge.
- This PR does NOT prove latency or feed staleness improvements (scheduled for Phase B JIT).

## Human Approval

Approved by user for merge as `ENTROPY_LIFECYCLE_SAFETY_FIX`.

## Runtime Traceability Check
- mode=N/A
- candidate_id=N/A
- decision=N/A
- reason=N/A
- timestamp=N/A
- is_order_action=false
- broker_api_called=false
- source=Antigravity
