# ORB Fidelity Audit Final Report

Primary verdict: `PARAMETER_CONTRACT_BROKEN`
Edge applicability: `VALID_ONLY_FOR_CURRENT_MISWIRED_VARIANT`

The historical underlying result remains frozen as `UNDERLYING_SIGNAL_WEAK_OR_UNSTABLE` and was not rerun or optimized.

Finding: the current implementation is internally deterministic, but its parameter contract is broken. `MIN_RETEST_MINUTES` and `MAX_RETEST_MINUTES` are required by the profile but inert. `MAX_RETEST_DISTANCE_PCT` and `MIN_BREAKOUT_DISTANCE_PCT` affect score only, not candidate eligibility. The emitted `vwap_alignment` tag is not backed by a VWAP predicate in the main temporal path.

Safety flags: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`.
