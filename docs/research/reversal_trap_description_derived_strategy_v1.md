# Reversal Trap Description-Derived Strategy V1

## Status

`DESCRIPTION_DERIVED_CONTRACT`

This contract is derived only from the published TradingView description for **Reversal Trap Probability Bands [BigBeluga]**. It is not claimed to be a byte-for-byte Pine port.

The purpose of this document is to remove hidden assumptions before the next backtest.

## Source-supported mechanics

The publication explicitly supports the following:

- `envelope_len` default: 55.
- Basis: exponential moving average using `envelope_len`.
- Upper and lower volatility bands:
  - `upper_band = basis + multiplier * vola`
  - `lower_band = basis - multiplier * vola`
- `vola` is an ATR-based volatility measure.
- `trap_window` default: 10 candles.
- A reversal trap requires price to break outside an envelope and subsequently close back inside before the trap window expires.
- RSI is bucketed into eleven groups:
  - `rsi_bucket = clamp(round(rsi / 10), 0, 10)`
- Bullish stop:
  - `lowest(low, 2) - atr`
- Bearish stop:
  - `highest(high, 2) + atr`
- Target is anchored to the basis line.
- Historical per-bucket totals and wins are accumulated in persistent arrays.

## Canonical trading interpretation

### Indicators

For each completed candle `t`:

```text
basis[t] = EMA(close, envelope_len)
atr[t]   = Wilder ATR(high, low, close, atr_len)
upper[t] = basis[t] + multiplier * atr[t]
lower[t] = basis[t] - multiplier * atr[t]
rsi[t]   = RSI(close, 14)
bucket[t] = clamp(round(rsi[t] / 10), 0, 10)
```

The description does not publish `atr_len` or the default `multiplier`. They must remain explicit research parameters rather than silently hard-coded facts.

### Bullish trap state

1. Arm a bullish trap when a completed candle closes below `lower`.
2. Record the first outside candle as `outside_start`.
3. While armed:
   - remain armed while the close stays below `lower`;
   - invalidate when more than `trap_window` completed candles have elapsed since `outside_start`;
   - trigger when a completed candle closes back inside the full envelope:
     `lower <= close <= upper`.
4. Signal direction: `LONG`.

### Bearish trap state

1. Arm a bearish trap when a completed candle closes above `upper`.
2. Record the first outside candle as `outside_start`.
3. While armed:
   - remain armed while the close stays above `upper`;
   - invalidate when more than `trap_window` completed candles have elapsed since `outside_start`;
   - trigger when a completed candle closes back inside the full envelope.
4. Signal direction: `SHORT`.

### Entry

Primary causal execution:

- Enter at the immediate next candle open after the re-entry signal.
- Reject the trade if the next candle belongs to a different trading session.
- Reject a long if entry is already at or above the target.
- Reject a short if entry is already at or below the target.

A signal-close fill may be reported only as a non-executable diagnostic upper bound.

### Target

Freeze the target at the signal-time basis value:

```text
long_target  = basis[signal_bar]
short_target = basis[signal_bar]
```

This is the most defensible interpretation of a dashed projected target anchored to the basis. A dynamic moving-basis exit must be tested only as a separate ablation.

### Stop

At the completed signal candle:

```text
long_stop  = lowest(low, 2)  - atr[signal_bar]
short_stop = highest(high, 2) + atr[signal_bar]
```

The stop is frozen before entry.

### Exit

- Exit when target is reached.
- Exit when stop is reached.
- If target and stop occur within the same OHLC candle, assume stop first.
- The description does not specify a time stop. Therefore the canonical strategy has no arbitrary 30-minute exit.
- For an intraday TradeBot study, unresolved positions are force-closed at the final tradable candle of the session.
- Positions never cross sessions.

### Position overlap

- One active position per symbol at a time.
- Ignore new traps while a position is active.
- This is an execution constraint, not a claim about the indicator's internal drawing engine.

## Historical RSI probability engine

Maintain independent arrays for bullish and bearish signals:

```text
bull_total[0..10]
bull_wins[0..10]
bear_total[0..10]
bear_wins[0..10]
```

At signal time:

1. Read the probability using only previously resolved trades in that direction and RSI bucket.
2. Do not use the current signal's future outcome in its displayed probability.
3. Start tracking the trade.
4. Increment `total[bucket]` once per valid signal.
5. Increment `wins[bucket]` only if target is reached before stop.
6. Treat session-end unresolved exits as non-wins for the indicator-style win-rate audit, while reporting their PnL separately for trading expectancy.

Probability:

```text
probability = wins[bucket] / total[bucket]
```

The publication does not specify a minimum sample threshold or an entry cutoff. Therefore:

- probability is diagnostic in the baseline;
- no baseline trade may be rejected because of its displayed percentage;
- any minimum-sample or probability threshold must be selected exclusively inside development data and verified on untouched holdout data.

## Canonical defaults and unresolved parameters

Source-supported defaults:

- `envelope_len = 55`
- `trap_window = 10`
- `rsi_len = 14` is inferred from standard RSI usage, not explicitly published.

Unresolved and therefore searchable only through bounded walk-forward research:

- `atr_len`
- `multiplier`

Initial bounded grid:

- `atr_len`: 7, 14, 21, 34, 55
- `multiplier`: 1.0, 1.5, 2.0, 2.5, 3.0

Robustness neighbours, not free optimization:

- `envelope_len`: 34, 55, 89
- `trap_window`: 5, 10, 15

No parameter may be changed after the final holdout is opened.

## Required ablations

The next study must compare:

1. Description-derived trap state vs direct outside-band fade.
2. Frozen basis target vs dynamic basis target.
3. First-outside-candle trap timing vs most-recent-outside-candle timing.
4. Close-outside excursion vs wick-outside/close-inside rejection.
5. No time stop vs fixed holding-period exits.
6. RSI probability as diagnostic vs probability-filtered entries.

## Acceptance standard

A candidate is not accepted merely because one parameter set is positive.

It must show:

- positive development walk-forward expectancy after costs;
- positive untouched holdout expectancy after costs;
- positive lower clustered-bootstrap confidence bound;
- positive performance in both holdout halves;
- acceptable month and regime stability;
- material uplift over direct fading;
- robustness across neighbouring ATR and multiplier values;
- sufficient trade count;
- no look-ahead, same-bar optimism, or post-holdout tuning.

## Corrections relative to the invalidated replica

The earlier replica included assumptions not supported by the description:

- fixed `atr_len = 14`;
- fixed `multiplier = 2.0`;
- arbitrary 30-minute time stop;
- treating the probability engine as though its exact accounting semantics were known.

Those results remain evidence only against that replica. They are not a verdict on this description-derived contract.

## Authority

Research only.

- No strategy-registry entry.
- No ranking authority.
- No paper-trading authority.
- No live-trading authority.
