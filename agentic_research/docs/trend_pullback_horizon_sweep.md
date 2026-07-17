# TREND_PULLBACK fixed-signal holding-horizon study

## Question

For the same causal `trend_pullback_v1` signals, determine whether the 15-minute timeout is prematurely closing trades that would later hit the 1.5R target, or whether unresolved trades are more likely to hit the stop.

## Frozen rules

- Production `trend_pullback_v1` callable and production movement-regime classifier.
- Entry at the next one-minute bar open after the completed trigger bar.
- The original structure-anchored stop and 1.5R target remain fixed for the complete path.
- Stop and target are checked on every one-minute candle.
- If stop and target are both touched in one candle, the stop is recorded first.
- No overnight carry and no cross-session continuation.
- Every included signal must have a complete, gap-free 60-minute future path.
- Holding horizons: 15, 20, 25, 30, 35, 40, 45, 50, 55 and 60 minutes.
- Baseline cost: 2 bps round trip.

## Two views

### Fixed-signal event study

Every horizon evaluates the exact same signal cohort. This answers:

- how many signals hit stop by each horizon;
- how many hit target by each horizon;
- how many remain timeout exits;
- at which exact bar stops and targets first occur;
- among 15-minute timeouts, how many later hit target, later hit stop or remain unresolved by 60 minutes.

Overlapping signals are retained because this view measures signal behaviour rather than portfolio capacity.

### One-position-at-a-time simulation

Signals that arrive while an earlier selected trade remains open are suppressed. This measures the operational consequence of extending the holding window, including lost later opportunities.

## Selection and evidence status

A diagnostic horizon is selected from development sessions using rolling-OOS positive-fold fraction first and net expectancy second. Its result is then read on the already-used historical holdout.

Because all horizons are also inspected on that existing holdout, this study is diagnostic and cannot certify a new edge. Any apparent recovery requires a fresh untouched period such as 2015 or an independent recent Upstox futures corpus.

Possible verdicts:

- `INVALID_DUE_TO_DATA`
- `NO_HORIZON_RECOVERY`
- `DIAGNOSTIC_HORIZON_RECOVERY_REQUIRES_FRESH_HOLDOUT`

No result certifies option execution or live profitability.
