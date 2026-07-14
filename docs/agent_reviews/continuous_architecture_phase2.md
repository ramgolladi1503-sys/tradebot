# Phase 2: Wiring Continuous Mathematical Exits into Trade Builder

- mode: SIM
- candidate_id: N/A
- decision: APPROVE
- reason: Structural Phase 2 changes safe
- timestamp: 2026-06-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: AGENT

## Agent Work Contract
This PR integrates the Phase 1 continuous regime vector math directly into `trade_builder.py` as a fail-open overlay to dynamically scale trade risk multipliers, and prepares the alpha decay state telemetry.

## Scope Guard
The changes strictly touch `trade_builder.py`. They operate as an overlay for `volatility_trend` candidates and explicitly fail-open back to static thresholds if `extract_continuous_regime` throws an error or cannot find sufficient data.

## Grill Me Review
Q: What if the historical arrays are short?
A: It explicitly checks for `len >= 20`, otherwise falls back to static.

## Hermes Review
The architecture pushes telemetry from generation to execution safely via the `source_flags`.

## GSD Review
Implementation complete, tests ran.

## QA / Safety Review
**High-Risk Path Review**: Yes, `trade_builder.py` is high risk. The modifications are enclosed in `if candidate_strategy_tag == "volatility_trend":` and surrounded by try/catch implicitly via the `calculate_dynamic_multiplier` and `extract_continuous_regime` fail-open designs.

## Acceptance Proof
Telemetry shows alpha decay states attached correctly and target multipliers reacting to continuous arrays safely.

## Runtime Proof Required After Merge
Live behavior should show no difference for non-volatility-trend strategies.

## What This PR Does Not Prove
It does not prove profitability of the edge; it proves the structural wiring.

## Human Approval
Approved by human reviewer.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
