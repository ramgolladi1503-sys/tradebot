# Volatility Expansion Strategy Family: Hypotheses

The `HTF_RANGE_EXPANSION` edge decomposition reveals that the highest-expectancy expansions occur via `trend_continuation_expansion` and `midday_expansion` patterns with massive `expansion_ratio` metrics (~4.89x ATR). 

Leveraging this specific native edge source, we hypothesize the following related strategy concepts that exploit mathematically identical structural phenomena:

## 1. Expansion After Compression (EAC)
**Hypothesis**: The most violently profitable expansions occur when the preceding 60 minutes exhibit abnormally tight range compression (e.g. `ATR < 50% of mean`). Entering the breakout of this micro-compression specifically inside the `VOL_EXPANSION` regime will drastically reduce the structural stop-loss width, exponentially increasing the R-multiple capture.

## 2. Failed Expansion Reversal (FER)
**Hypothesis**: If an opening drive triggers a structural expansion signal but mathematically fails to reach `1.0R` within 30 minutes, it indicates the `VOL_EXPANSION` regime is experiencing a directional exhaustion event. A reverse-momentum entry at the failure of the initial stop-loss will capture the slingshot momentum in the opposite direction.

## 3. Second-Day Expansion Continuation
**Hypothesis**: If Day `T` is a confirmed `VOL_EXPANSION` regime closing near its highs/lows, Day `T+1` inherently possesses an opening momentum bias. Taking the first 15m breakout purely in the direction of the `T` close will front-run the secondary expansion wave before the day's formal regime is even algorithmically classified.

## 4. Volatility Squeeze Release (Midday Vector)
**Hypothesis**: The decomposition proved `midday_expansion` dominates the top 20% of PnL distribution. If the market is in a `VOL_EXPANSION` regime but enters a tight VWAP-hugging chop between 11:30 and 13:00, the mathematical break of this VWAP squeeze post-13:00 will carry disproportionate edge because retail algorithms will trigger cascading stop-outs.

> [!CAUTION]
> These are purely theoretical mathematical hypotheses derived from the feature attribution matrices. None of these strategies have been coded, backtested, or promoted. They represent the `RESEARCH_ONLY` backlog for Phase 3 Edge Discovery.
