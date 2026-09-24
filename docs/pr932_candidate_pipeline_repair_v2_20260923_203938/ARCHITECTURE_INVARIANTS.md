# Architecture Invariants - Candidate Pipeline

1. **Strategy Qualification Separation**: Strategy qualification is an intrinsic analytical property of completed market information. Execution eligibility is an extrinsic state depending on live market feed freshness, spread, and broker readiness.
2. **Fail-Closed on Degraded Feed**: When an input required for qualification is missing or stale (>2.5s), qualification state must be UNKNOWN, not FALSE or SYNTHETIC.
3. **No Phantom Execution**: No candidate is marked `execution_eligible=True` unless `feed_ok=True` and `feed_age_sec <= 2.5`.
4. **Conservation of Observations**: Every incoming symbol evaluation maps 1-to-1 to a `StrategyObservation` record.
5. **Truth Law Adherence**: Missing prices remain `None`. No arbitrary fallbacks (e.g. 100.0) are allowed.
