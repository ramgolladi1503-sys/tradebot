# Causal Market-State Representation V1 — Empirical Result

## Verdict

`MARKET_STATE_REPRESENTATION_PARTIALLY_VALID`

This is an underlying-behaviour result, not a certified option strategy.

## Dataset and split

- Instrument: NIFTY underlying, one-minute sessions
- Period: 2023-01-02 through 2024-06-28
- Rows: 137,250
- Sessions: 366
- Chronological split: 219 train / 73 validation / 74 holdout sessions
- Causal prefix and session-boundary tests: passed

## Incremental representation result

The full 20-feature causal state representation beat the five-feature baseline on both validation and holdout for predicting the magnitude of the next 15-minute move.

Validation, future absolute 15-minute return:

- baseline correlation: 0.07525
- full-state correlation: 0.11158
- baseline MAE: 0.00053253
- full-state MAE: 0.00052804

Holdout, future absolute 15-minute return:

- baseline correlation: 0.16028
- full-state correlation: 0.17541
- baseline MAE: 0.00065321
- full-state MAE: 0.00065138

The representation did not add reliable directional-return prediction. Its useful information is primarily about upcoming expansion magnitude.

## Stable discovered pattern

The strongest repeated pattern is:

> A sufficiently strong downside impulse is followed by a materially larger next-15-minute absolute move.

Frozen train-derived thresholds and untouched evaluation results:

### Medium-horizon downside impulse

Condition:

`trend_return_medium <= -0.0011372007658609683`

Validation:

- rows: 2,762
- future absolute 15-minute return lift over unconditional baseline: +0.00034357

Holdout:

- rows: 3,226
- lift: +0.00064621

### Negative medium slope

Condition:

`trend_slope_medium <= -0.00008454476947876878`

Validation:

- rows: 2,844
- lift: +0.00033502

Holdout:

- rows: 3,371
- lift: +0.00063925

### Short-horizon downside impulse

Condition:

`trend_return_short <= -0.0006411951240074875`

Validation:

- rows: 2,946
- lift: +0.00029823

Holdout:

- rows: 3,480
- lift: +0.00052262

## Interpretation

The breakthrough is not "buy puts after every decline." The validated information is that downside impulse states identify an elevated-expansion regime. Direction, exact option contract selection, entry timing, spread, slippage, and post-entry path remain unvalidated.

The next candidate research lane is a buy-only expansion strategy conditioned on this state, with direction decided by a separate causal continuation/reversal discriminator and certified using exact executable option contracts.

## Current boundary

Do not promote this result to production or claim profitability. It is useful causal evidence that narrows strategy discovery to a specific market regime and removes the need to search indiscriminately across all minutes.
