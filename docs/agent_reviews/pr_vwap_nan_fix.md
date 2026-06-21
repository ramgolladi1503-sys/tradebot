# PR: Fix VWAP Mean Reversion Intent Logic and NaN Vulnerabilities

## Agent Work Contract
This PR fixes 3 critical implementation bugs identified during the rejected-strategy truth audit:
1. `LIQUIDITY_IMBALANCE` bypassing strict gating when `bid_qty` or `ask_qty` is NaN.
2. `VOL_EXPANSION_NAIVE` bypassing gating when `atr` is NaN.
3. `VWAP_MEAN_REVERSION` over-gating valid directional intents to `NO_TRADE`.

## Scope Guard
In scope:
- Fixing `_safe_float` in `strategies/pro_layer/pro_strategy_engine.py` to intercept `NaN` outputs.
- Modifying `build_mean_reversion_candidate_intents` in `core/mean_reversion_candidate_generator.py` to preserve `INTENT_TYPE_ENTRY` when a valid directional trade exists, regardless of internal strategy blockers.
- Updating `test_edge_74_mean_reversion_candidate_generator.py` to match the expected behavior.

Out of scope:
- Re-enabling rejected strategies for live trading.
- Modifying broker APIs.
- Weakening execution gates or kill switches.

## Grill Me Review
We assume returning `default` for `NaN` inputs to `_safe_float` correctly disables the strategy because the strategy checks will catch `0.0`. This assumption holds because the strategies inherently check for zero (`<= 0`) and block execution.

## Hermes Review
Architecture boundaries are respected. Strategy intent is correctly passed down the pipeline without being accidentally mutated to `NO_TRADE` when soft blocks occur.

## GSD Review
Delivery check:
- Tests pass.
- Fixes applied.
- Scope is narrow.

## QA / Safety Review
- Ensures safety by blocking `NaN` driven live execution.
- Ensures truth in intent reporting.
- Does not change live production strategy active status.

## High-Risk Path Review
Reviewed `strategies/pro_layer/pro_strategy_engine.py` and `core/mean_reversion_candidate_generator.py`. `NaN` protection directly improves safety. Intent-type changes restore architectural truth without weakening downstream execution gates.

## Acceptance Proof
All pytest fallback test suites pass (`pytest tests -q`).

## Runtime Proof Required After Merge
No runtime evidence required.

## What This PR Does Not Prove
This PR does not prove edge for any of the repaired strategies. It simply proves the logic operates safely as intended.

## Human Approval
Requires PR review and manual merge.
