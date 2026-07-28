# Trusted Option Data Joint Warehouse V1

Primary verdict: OPTION_DATA_READY_FOR_DISCOVERY
Trusted option sources: 1
Observational option sources: 1
Warehouse rows: 395923
Warehouse sessions: 386
Determinism: PASS
Independent audit pass: True

Capability support matrix:
- option_premium_replay: SUPPORTED
- premium_lead_lag_research: PARTIALLY_SUPPORTED
- strike_selection_research: SUPPORTED
- iv_oi_research: PARTIALLY_SUPPORTED_OI_ONLY
- spread_aware_fill_simulation: NOT_SUPPORTED
- algotest_comparison: NOT_SUPPORTED

Blockers:

Exact next action:
Build or point to a trusted NIFTY underlying feature warehouse covering 2024-09-26 through 2026-07-21, then rerun the joint certification before discovery.

Safety flags:
- read_only=True
- is_order_action=False
- broker_api_called=False
- allowed_for_live_execution=False
