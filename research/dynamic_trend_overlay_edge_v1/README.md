# Dynamic Trend Overlay Edge Research V1

## Objective

Falsify the public Dynamic Trend Overlay concept on the preserved NIFTY constituent and Upstox expired-option corpus, then test only tightly adjacent causal mechanisms.

This campaign is a semantic recreation from the public indicator description. It does not copy or claim exact equivalence to the Pine source.

## Frozen hypothesis family

1. `DTO_FLIP_MTF` — chart-timeframe EMA/ATR trail flip aligned with a completed 15-minute trail.
2. `DTO_REENTRY_STOCH` — aligned trend, controlled trail pullback and completed-bar StochRSI re-expansion.
3. `DTO_REENTRY_BREADTH` — replaces oscillator confirmation with constituent breadth repair.
4. `DTO_PARTICIPATION_SEQUENCE` — pullback contraction followed by broad participation re-expansion.
5. `DTO_OPTION_UNDERREACTION` — aligned underlying/constituent impulse while the same-direction option has not fully repriced.
6. `DTO_EXHAUSTION_FILTERED` — participation sequence with an ATR-distance exhaustion blocker.

## Causal execution contract

- NIFTY five-minute completed bars only.
- Chart trail: EMA 10, ATR 10, multiplier 1.8.
- Higher-timeframe trail: completed 15-minute bars, EMA 8, ATR 8, multiplier 2.0.
- Minimum 40 constituent returns at the signal bar.
- Maximum two signals per variant per session with a 20-minute cooldown.
- Nearest non-expired same-strike ATM CE/PE pair within 100 NIFTY points.
- Contract selection uses signal-time spot before entry prices are read.
- Entry is the exact one-minute option open at the completed five-minute signal timestamp.
- Exit is the option close nine minutes later.
- Primary friction is 1.0% of premium return; severe friction is 1.5%.
- Development/validation/holdout sessions are chronological 70/15/15.
- At most one development-plus-validation survivor may open holdout.

## Survival gates

The campaign requires sufficient trades and sessions, positive after-cost expectancy, profit factor above one, positive bootstrap lower bound, survival after removing the five largest winners, severe-friction survival, low session concentration, opposite-wing degradation and five-minute delayed-entry degradation.

A failure is retained as `NO_EDGE_IN_TESTED_DTO_FAMILY`. A validation survivor that fails sealed holdout is retained as `DTO_VALIDATION_SURVIVOR_FAILED_HOLDOUT`.

## Safety and claim boundary

- Research only.
- No broker or provider calls.
- No order actions.
- No production strategy, feed, risk, ranking or execution changes.
- Historical option OHLCV is a candle proxy, not executable bid/ask certification.
- Even a survivor is not paper- or live-authorized.
