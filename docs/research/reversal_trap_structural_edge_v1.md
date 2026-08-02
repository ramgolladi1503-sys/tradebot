# Reversal Trap Structural Edge V1

## Objective

Falsify or support the published mechanism behind TradingView's **Reversal Trap Probability Bands [BigBeluga]** on the repository's historical intraday candle corpus.

The study is deliberately not a visual indicator port and does not treat the displayed RSI percentage as a calibrated probability.

## Published mechanism used

- EMA basis, published default length 55.
- ATR volatility envelope.
- An excursion closes outside an envelope.
- Price closes back inside within a maximum of ten candles.
- Entry occurs at the next bar open.
- Target is the signal-time EMA basis, frozen at signal time.
- Stop is beyond the two-bar extreme plus one ATR.

The TradingView page parser did not expose the complete Pine source or the exact default envelope multiplier. Therefore, the canonical research assumption uses `2.0 * ATR`, while `1.5`, `2.0`, and `2.5` are reported as neighbouring robustness checks. This is not claimed to be a byte-for-byte Pine reproduction.

## Integrity contract

- Signals use completed candles only.
- Entry is strictly the immediate next bar open.
- Targets and stops are frozen before entry.
- If stop and target are touched in the same candle, the stop is assumed first.
- Trades do not cross sessions.
- Only one active trade per symbol is allowed.
- Chronological 60/20/20 train, validation, and test session splits are fixed before evaluating results.
- The canonical result includes a five-basis-point round-trip cost stress.
- Session-block bootstrap confidence intervals are used for test expectancy.

## Structural-edge test

A structural-edge verdict requires all of the following:

1. Positive validation expectancy.
2. Positive test expectancy after five basis points of costs.
3. Positive lower bound of the 95% session-bootstrap confidence interval.
4. At least one basis point of test uplift over direct outside-band fading.
5. Positive expectancy in at least 60% of chronological test chunks.
6. Positive test expectancy in at least half of neighbouring parameter combinations.
7. At least 200 total trades, 50 test trades, and 30 sessions.

Anything weaker is classified as fragile, negative, or data-blocked.

## RSI probability audit

The RSI bucket model is fitted only on the train split with Laplace smoothing and evaluated on the test split using Brier score. It must outperform a constant train-base-rate forecast out of sample before it can be said to add information.

## Outputs

The runner writes:

- `dataset_inventory.csv`
- `canonical_trap_trades.csv`
- `canonical_direct_band_fade_trades.csv`
- `robustness_matrix.csv`
- `summary.json`
- `report.md`

No paper-trading or live-execution authority is introduced.
