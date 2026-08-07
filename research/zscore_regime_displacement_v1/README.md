# Z-Score Regime Displacement V1

Research-only continuation of the recent Observation-First Pattern Atlas / autonomous structural-edge discovery work.

## Frozen mechanism family

This lane does **not** reopen or retune any failed PR #806 family. It introduces one genuinely new mechanism family:

`ZSCORE_REGIME_DISPLACEMENT`

The completed 5-minute NIFTY close is standardized against the **prior 12 completed bars only**:

- window: 12 bars (60 minutes)
- extreme: `|z| >= 2.0`
- re-entry: `|z| <= 1.5`
- entry: following completed 5-minute bar
- outcomes: 15 and 30 minutes only
- maximum one signal per mechanism per session
- direction is mechanical from event sign, never learned from outcomes

### H1 — Extreme re-entry + cross-sectional disagreement

An extreme displacement re-enters inside 1.5 sigma and the extreme direction was not confirmed by constituent breadth.

Direction: opposite the extreme.

### H2 — Extreme continuation + participation confirmation

An extreme displacement is confirmed by same-direction constituent breadth and same-direction returns among constituents already classified by the inherited data frame as volume shocks.

Direction: same as the extreme.

## Certification boundary

The lane reuses the pinned PRE_CAS source authority, observation-only universe selection, matched baseline, BH multiple-testing correction, chronological validation/WFA and robustness attacks from the recent research PRs.

The existing unopened tail remains sealed in this PR even if a robustness survivor appears. A separate one-shot independent procedure is required to consume it.

No option translation, strategy registry, TradeBuilder, ranking, risk, broker, paper/live, or order authority is added.
