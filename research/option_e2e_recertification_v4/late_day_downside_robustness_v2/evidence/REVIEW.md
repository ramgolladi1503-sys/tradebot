# Late-Day Downside Robustness V2

## Objective

Stress-test the existing late-day bearish option hypothesis using only the already available Kite-derived canonical intents and Upstox expired-option archive. No strategy formula, threshold, production path, or holdout outcome was changed or read.

## Base result reproduced

- Development: 37 trades, PF 1.5719, mean return 2.7298%
- Validation: 13 trades, PF 2.3152, mean return 8.9507%
- Opposite-side validation: 8 trades, PF 0.2525

## Expanded robustness test

A frozen 135-row parameter grid varied:

- maximum strike distance: 50, 100, 150, 200, 300 points
- premium-confirmation lookback: 3, 5, 10 minutes
- minimum entry premium: ₹20, ₹30, ₹50
- holding period: 10, 20, 30 minutes

Entry remained one minute after signal, maximum signal-to-entry lag remained 120 seconds, and friction remained 5 bps per side.

The joint gate required:

- PF above 1 in both development and validation;
- positive mean return in both partitions;
- at least 20 validation trades.

**Qualifying rows: 0 of 135.**

## Concentration controls

- Development PF falls from 1.5719 to 0.9599 after removing the two largest winners.
- Validation PF falls from 2.3152 to 0.6950 after removing the two largest winners.
- The opposite-side control remains negative, which supports directional asymmetry, but does not overcome winner concentration and sample insufficiency.

## Interpretation

The late-day bearish mechanism remains the only promising lead in PR #718, but the current option evidence is not robust enough for certification. The high headline PF is driven by a small number of outsized winners, and no tested parameter neighbourhood satisfies the minimum validation-sample and positive-return gate.

## Verdict

`PROMISING_RESEARCH_HYPOTHESIS_NOT_ROBUST`

Holdout remains sealed.
