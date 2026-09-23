# Pipeline Reason Code Taxonomy

1. `STRATEGY_INAPPLICABLE`: Target symbol does not belong to the asset universe required by the strategy.
2. `STRATEGY_DISABLED`: Strategy declaration has `enabled: False`.
3. `PREREQUISITE_MISSING`: Required historical or reference primitives (e.g. prev_day_close, vwap) not loaded.
4. `NO_QUALIFIED_SIGNAL`: Mathematical signal model produced `direction == UNKNOWN` or `confidence < 0.50`.
5. `NEAR_SIGNAL`: Mathematical signal produced valid direction with `0.50 <= confidence < 0.70`.
6. `REQUIRED_LIVE_INPUT_STALE`: Strategy signal computation strictly requires real-time tick/LTP, but quote age > 2.5s.
7. `FEED_STALE_EXECUTION_BLOCK`: Strategy signal is validly qualified from completed bars, but current quote tick > 2.5s.
8. `EXECUTION_ELIGIBLE`: Candidate is strategy qualified AND current execution quote tick <= 2.5s.
