# Reversal Trap Filter Optimization V2

## Verdict

`NO_ROBUST_FILTERED_EDGE`

The phrase “perfect parameters without overfitting” is internally contradictory if the search continues until a profitable result appears. This study therefore used a bounded two-stage search and kept the final 20% of sessions locked until after one configuration had been selected.

## Search contract

Stage 1 tested 4,752 combinations of:

- directional RSI thresholds
- intraday start and end windows
- long-only, short-only, or both sides

Stage 2 expanded the 25 strongest development candidates into 500 combinations of:

- weekday filters
- maximum trades per session

Selection used four chronological development folds. Every parameter was fixed before opening the final 20% holdout.

## Best development configuration

- Long RSI maximum: 20
- Short RSI minimum: 55
- Trading window: 09:15–13:30
- Direction: both
- Weekdays: Monday through Thursday
- Maximum trades per session: 2

This was only the least-bad configuration. It was negative in all four development folds:

- -4.6006 bps/trade
- -4.0552 bps/trade
- -3.1618 bps/trade
- -2.5327 bps/trade

Development CV score: `-4.0068 bps/trade`.

## Locked holdout

- Trades: 137
- Gross expectancy: +0.7346 bps/trade
- Net expectancy after 5 bps: -4.2654 bps/trade
- 95% clustered bootstrap interval: [-6.0236, -2.5876] bps/trade
- Win rate: 46.72%
- Profit factor: 0.3312
- Positive months: 17.39%

The first half of the holdout lost -5.8189 bps/trade net. The second half lost -3.0185 bps/trade net.

## Direct-band-fade ablation

Using the identical filters on direct outside-band fading produced:

- Gross expectancy: +0.7727 bps/trade
- Net expectancy after 5 bps: -4.2273 bps/trade

The multi-bar “trap” sequence underperformed the simpler direct fade by `-0.0381 bps/trade`.

## Acceptance result

Failed:

- positive development CV score
- at least 75% positive development folds
- positive holdout expectancy after costs
- positive lower confidence bound
- minimum 200 holdout trades
- positive expectancy in both holdout halves
- at least 60% positive months
- at least 0.5 bps uplift over direct fading

The only passed condition was positive gross holdout expectancy before costs. It was too small to be executable and was not unique to the trap sequence.

## Decision

Do not continue searching this family until a positive backtest appears. That would be data mining, not research.

Do not integrate the indicator, its RSI percentages, or the filtered configuration into TradeBot. The correct research verdict remains rejection pending a broker-data confirmation run.

Evidence semantic SHA-256: `879ae7393ee056701915fef969b57a16d1401b804fef46d7a2c277b91f09d1ed`
