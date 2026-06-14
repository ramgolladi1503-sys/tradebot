# Elite Regime Router Phase 1: Strategy Hardening

## Agent Work Contract
source: GSD
action: GENERATE_PATCH

## Scope Guard
### Requested Paths
- `strategies/vwap_orb.py`
- `strategies/volatility_trend.py`
- `strategies/pairs_arbitrage.py`
- `tests/test_pairs_candidate_generator.py`

### Allowed Paths
- `strategies/vwap_orb.py`
- `strategies/volatility_trend.py`
- `strategies/pairs_arbitrage.py`
- `tests/test_pairs_candidate_generator.py`
- `docs/agent_reviews/elite-regime-router-phase1-20260614.md`

### Forbidden Paths
- `main.py`
- `runtime/*`
- `core/runtime_safety_boot_guard.py`

## QA / Safety Review
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
read_only: true
mode: OFFLINE
candidate_id: N/A
decision: N/A
reason: N/A
timestamp: 2026-06-14

## Grill Me Review
Basic heuristics have been identified as inadequate for LIVE execution. This PR forces institutional rigor onto the strategies before any LIVE gating is permitted. 

## Hermes Review
Phase 1 of the Regime Router architecture. Upgrades strategy modules independently before they are wired into the global Regime Router in Phase 3.

## GSD Review
Implemented Dealer Gamma Exposure (GEX) and Cumulative Volume Delta (CVD) vetoes in `vwap_orb.py`. Created a new `volatility_trend.py` using ATR inversely for lot sizing. Replaced basic correlation with ADF Cointegration tests in `pairs_arbitrage.py`. Tests updated to provide the new required flags.

## Expected Tests
- `test_pairs_candidate_generator_spread_zscore` (Fixed to provide cointegration flag)

## Acceptance Proof
All local Pytest unit tests pass. 

## Runtime Proof Required After Merge
None. This is offline strategy hardening.

## What This PR Does Not Prove
This PR does not prove live profitability, nor does it wire the strategies into the execution path yet. It prepares them for the Phase 3 Regime Router.

## Human Approval
Approved.
