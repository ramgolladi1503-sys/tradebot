# Closure Note: NIFTY RSI(2) Mean Reversion

## What Was Tested
The hypothesis evaluated a classic RSI(2) mean-reversion strategy on the NIFTY index, specifically analyzing whether extreme short-term oversold readings constitute a structural statistical edge.

## Misleading Win Rate
The initial evaluation reported a 66% win rate, which appeared promising. However, this high win rate was an artifact of the positively skewed, heavy-tailed distribution characteristic of short-term mean-reversion strategies, masking a fragile risk-adjusted expectancy.

## Decisive Matched-Random Result
To rigorously test the edge, the strategy was compared against 1,000 matched-random replicates. In this analysis, 82.7% of the random portfolios outperformed the actual RSI(2) signals. The inability to convincingly beat a random entry generator decisively nullifies the claim of structural edge.

## Parameter Fragility
While certain adjacent thresholds or localized parameter neighborhoods yielded positive backtest results, these variations proved highly unstable across different splits. The positive neighborhood results do not rescue the strategy; they are hallmarks of curve-fitting rather than an underlying causal mechanic.

## Unacceptable Tail Risk
The base exit rule exposed severe regime-transition tail risk. In the event of a trend dislocation, the strategy suffered single crash losses that dominated the risk profile. The positive expectancy was overwhelmingly reliant on a few trades—specifically, removing the five best trades turned the overall result negative.

## Not Eligible for TradeBot Runtime
Due to its parameter fragility, unmitigated tail risk, and failure to beat matched-random controls, this strategy holds `NO_STRUCTURAL_EDGE`. It is unfit for trading, capital allocation, or option translation. No production runtime integration is permitted.

## Reopening Criteria
This hypothesis is formally closed. It may only be reopened if ALL of the following criteria are met:
1. Authoritative frozen tradable-instrument data is provided.
2. Independently verified futures or ETF execution costs are modeled.
3. A predeclared new causal hypothesis that is materially different from threshold tuning is established.
4. A new untouched holdout period is secured.
5. Matched-random controls confirm the signal materially beats random chance.
6. P&L remains positive after removing the five best trades.
7. No single crash loss dominates the risk profile.

Do not reopen merely because a different RSI threshold appears profitable.
