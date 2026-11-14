# AlphaTrend-Inspired Mechanism Research V1

## Status

`RESEARCH_ONLY`

This package does **not** claim to reproduce AlphaTrendPro. The TradingView implementation is invite-only and does not publish enough internal parameters to support an exact-equivalence claim.

The purpose of this package is to test the published mechanism transparently:

`trend -> confirmed structure -> six-line momentum -> fresh alignment / pullback continuation -> 15-30 minute NIFTY direction`

No option P&L, strike selection, broker action, paper execution, or live execution is authorized by this package.

## Research hypotheses

### H1 — Fresh alignment

A newly established directional trend has better 15–30 minute continuation when:

1. trend state is directional,
2. confirmed swing structure agrees (`HH_HL` or `LH_LL`),
3. six momentum EMAs are correctly stacked,
4. all six momentum EMA slopes agree,
5. trend and momentum alignment are recent enough.

Signal: `signal_full_fresh`.

### H2 — Pullback continuation

An established directional trend has better 15–30 minute continuation when:

1. trend, structure, and momentum remain aligned,
2. price recently overlaps the momentum ribbon plus a bounded ATR buffer,
3. price then re-breaks in the original trend direction,
4. duplicate continuation events obey a cooldown.

Signal: `signal_continuation`.

## Ablations

The engine emits the following event families from the same causal feature set:

- `signal_trend_only`
- `signal_trend_structure`
- `signal_trend_momentum`
- `signal_full_fresh`
- `signal_continuation`

The full mechanism is not interesting unless it improves on its simpler ablations. A positive full-signal result with no incremental improvement over `signal_trend_only` is not evidence for the multi-factor mechanism.

## Transparent substitute definitions

These are research definitions, not proprietary AlphaTrendPro internals.

### Trend

Default fast/slow EMAs are 8/21. Bullish requires fast EMA above slow EMA, positive fast-EMA slope, and close above the slow EMA. Bearish is the inverse.

### Structure

Pivots use left/right confirmation bars. A pivot is written to the feature stream only on the later confirmation bar; it is never backfilled to the earlier pivot timestamp.

- bullish: last swing high > prior swing high **and** last swing low > prior swing low
- bearish: last swing high < prior swing high **and** last swing low < prior swing low
- otherwise: `MIXED`
- sufficiently old pivots: `STALE`

`MIXED`, `STALE`, and insufficient structure map to neutral/no-trade research state.

### Momentum

Six EMA lines are used by default: `3, 5, 8, 13, 21, 34`.

Bullish momentum requires strict fast-to-slow bullish stacking and positive slope on every line. Bearish momentum requires the inverse. Anything else is neutral.

### Pullback continuation

The six momentum EMAs define a ribbon. A recent candle must overlap the ribbon expanded by a small ATR buffer. Continuation then requires a directional re-break plus full current alignment.

## Default configuration

```text
fast_span=8
slow_span=21
momentum_spans=(3,5,8,13,21,34)
slope_lookback=2
atr_span=14
pivot_left=2
pivot_right=2
structure_stale_bars=20
fresh_trend_max_age_bars=34
momentum_recency_bars=3
min_trend_age_bars=5
continuation_cooldown_bars=5
pullback_lookback_bars=3
pullback_buffer_atr=0.20
```

## Predeclared parameter family

Do not perform unconstrained optimization. The first campaign may evaluate only the following mechanism variants before validation:

| ID | Trend EMA | Momentum EMA spans | Pivot L/R | Pullback ATR buffer |
|---|---|---|---|---|
| `AT_M1_BASE` | 8/21 | 3,5,8,13,21,34 | 2/2 | 0.20 |
| `AT_M1_FAST` | 5/13 | 2,3,5,8,13,21 | 1/1 | 0.20 |
| `AT_M1_SLOW` | 13/34 | 5,8,13,21,34,55 | 2/2 | 0.20 |
| `AT_M1_STRUCTURE_FAST` | 8/21 | 3,5,8,13,21,34 | 1/1 | 0.20 |
| `AT_M1_PULLBACK_TIGHT` | 8/21 | 3,5,8,13,21,34 | 2/2 | 0.10 |
| `AT_M1_PULLBACK_WIDE` | 8/21 | 3,5,8,13,21,34 | 2/2 | 0.30 |

If none survives, close the family. Do not invent a larger grid after seeing the results and call that the same hypothesis.

## Outcomes

`add_forward_labels` creates same-session forward outcomes at 5, 10, 15, 20, and 30 bars:

- close-to-close forward return in bps,
- maximum forward high excursion in bps,
- minimum forward low excursion in bps.

Rows without a complete future horizon inside the same session remain `NaN`; the next session cannot satisfy an intraday outcome.

These are **underlying NIFTY directional outcomes**, not option returns.

## Negative controls

`build_negative_controls` provides two deterministic controls:

1. sign inversion — the same event timestamps with direction reversed,
2. same-session time shift — events delayed by a fixed bar count without crossing the session boundary.

For promotion-quality evidence, add a matched placebo control using comparable time-of-day and volatility conditions before final certification.

## First-pass evidence gates

A parameter variant may advance from development to validation only if all of the following are true:

1. at least 100 measured events across the tested development period,
2. both 15-minute and 30-minute mean directional returns are positive,
3. both 15-minute and 30-minute medians are not materially negative,
4. `signal_full_fresh` or `signal_continuation` improves materially over `signal_trend_only`,
5. the sign-inversion control behaves in the opposite direction,
6. the time-shift control does not retain the full effect,
7. performance is not concentrated in one small group of sessions or one short calendar regime,
8. no causality or timestamp test fails.

These are research gates, not a profitability certification.

## Validation and holdout policy

Use completed bars only. Decision time is bar end, not bar start. Reuse the repository's existing timestamp normalization where possible.

Do not consume a historical partition merely because it is named `holdout`. Final certification requires a uniquely identified, contamination-free holdout authority. If that cannot be established, freeze the selected candidate and use a fresh prospective holdout.

Do not inspect final-holdout performance while selecting parameters.

## Option-buying promotion path

Only after a directional candidate survives development, validation, WFA/robustness, controls, and an uncontaminated holdout should it enter the option layer:

`directional signal -> option-chain eligibility -> expiry/strike rule -> executable quotes -> slippage/cost model -> option-path replay -> manual-approval shadow`

A positive NIFTY directional expectancy is necessary but not sufficient for profitable CE/PE buying.
