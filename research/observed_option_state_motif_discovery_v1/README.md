# Observed Option-State Motif Discovery V1

This campaign changes the research direction from mechanism-first to observe-first.

## Objective

Use the preserved historical NIFTY option OHLCV corpus to observe recurring pre-outcome option-state motifs first, freeze promising motifs from an early chronological observation slice, and only then test them on later chronological data.

## Design

The script buckets only pre-outcome state variables, including option side, premium band, DTE band, time-of-day, prior return state, acceleration state, volume state, mirror-wing state, breadth, dispersion, range, surface median, OI participation, and option asymmetry.

The workflow is:

1. Build motif buckets from the earliest research observation slice.
2. Evaluate recurring observed motifs in that observation slice.
3. Freeze only observed motif signatures that pass the observation gate.
4. Validate frozen motifs on later chronological research folds.
5. Open latest holdout only for validation survivors.
6. Apply mirror-side and delayed-entry controls on holdout.

## Guardrails

- No broker, paper, live, provider, order, or production action.
- Historical five-minute candle proxy only.
- Exact next-minute entry and exact five-minute outcome.
- Latest holdout remains sealed unless validation survives.
- One percent friction stress is required for validation.
- Winner concentration trimming is required.

