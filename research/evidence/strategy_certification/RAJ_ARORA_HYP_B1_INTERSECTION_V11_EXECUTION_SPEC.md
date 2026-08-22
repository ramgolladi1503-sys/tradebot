# Raj Arora / HYP_B1 Intersection V11 — Execution Specification

Status: `FROZEN_BEFORE_V11_OUTCOME_ACCESS`

This document fixes implementation details that were not fully specified by the V11 passport. It does not change the strategy family, threshold, search budget, or advancement gates.

## Authorities

- V11 passport: `research/strategy_certification/passports/RAJ_ARORA_HYP_B1_INTERSECTION_V11_FREEZE.json`
- exact canonical NIFTY 5-minute corpus SHA-256: `6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8`
- exact aligned spot/futures panel SHA-256: `2311981231d3fb847a216c9165ef73c3e7b788ab354d6de493ab1a5edb32e7a9`
- HYP_B1 threshold: literal `basis_chg_15m > 8.5000000000000000 INR`
- V11 development end: `2025-09-15`
- validation and holdout outcomes remain forbidden unless all development gates pass.

Any input SHA mismatch is a hard fail-closed condition.

## Frozen base event

For each canonical NIFTY development session:

1. opening range = high/low of the first two completed 5-minute bars;
2. inspect later completed closes in chronological order;
3. the first close outside the range by 5 bps must be below the opening-range low;
4. if the first qualifying close-break is upward, the session is rejected;
5. after a downside first break, a completed close must return inside `[OR low, OR high]` within the next two bars;
6. the reclaim bar is the decision bar;
7. bullish entry is the close of the next completed 5-minute bar;
8. outcomes are evaluated 3/6/9 bars after entry;
9. base cost is 5 bps round trip; 7.5 bps is the declared 30-minute stress cost;
10. the delay test moves entry one additional completed 5-minute bar later and preserves the 30-minute forward horizon.

No wick, body, gap, volatility, breadth, volume, date, weekday, expiry, or other filter is permitted in V11.

## Reclaim-time HYP_B1 alignment

The historical canonical NIFTY cache may serialize the source clock with a constant timezone-text offset. Therefore V11 must not join the two authorities by blindly interpreting the canonical timestamp as an exchange clock.

Instead:

1. compute the reclaim bar's elapsed time from the first canonical 5-minute bar of that session;
2. the end of the completed reclaim bar is `elapsed + 4 minutes` from the first 1-minute row in the aligned futures panel for that session;
3. require exactly one futures-panel row at that target minute;
4. if the minute is missing, exclude the event and report it; never impute or use the nearest minute.

This preserves the frozen bar ordering while avoiding dependence on historical CSV timezone-string serialization.

## Literal HYP_B1 reconstruction

Within each futures-panel session:

```text
raw_basis = futures_close - spot_close
basis_chg_15m = raw_basis.diff(15)
```

The literal pre-existing HYP_B1 state at the completed reclaim bar is:

```text
ACTIVE   : basis_chg_15m > 8.5
INACTIVE : basis_chg_15m <= 8.5
```

No HYP_B1 threshold refit, percentile recomputation, lag search, nearby threshold test, or alternative futures roll is allowed.

## Development gates

The ACTIVE family advances only if every passport gate passes:

- at least 10 evaluable 30-minute trades;
- mean 30-minute net return positive at 5 bps;
- mean 30-minute net return positive at 7.5 bps;
- one-extra-5-minute delayed-entry 30-minute mean remains positive;
- at least 2 of the 3 fixed horizons are positive at 5 bps;
- at least 2 of 3 chronological ACTIVE trade blocks have positive 30-minute mean at 5 bps;
- top-five positive-trade contribution is no more than 80% of total ACTIVE 30-minute net return;
- ACTIVE minus INACTIVE 30-minute mean at 5 bps is at least +2.0 bps.

Null controls execute only if all pre-null gates pass.

## Frozen null definitions

### Randomized-direction control

Use the ACTIVE 30-minute gross underlying returns. For each deterministic draw, independently multiply every gross return by `+1` or `-1` with equal probability, then subtract the same 5-bps round-trip cost. Compare the randomized mean with the observed ACTIVE 30-minute mean.

- draws: `20,000`
- RNG seed: `20260823`
- empirical one-sided p-value includes +1 finite-sample correction
- required p-value: `<= 0.025`

This attacks whether the bullish direction mapping matters beyond unsigned movement magnitude.

### Session-label / pairing control

V11 produces at most one frozen failed-breakout base event per session. Preserve all event outcomes and the observed number of ACTIVE events, randomly reassign which event sessions carry the ACTIVE label without replacement, and recompute:

```text
mean(ACTIVE 30m net) - mean(INACTIVE 30m net)
```

- draws: `20,000`
- RNG seed: `20260824`
- empirical one-sided p-value includes +1 finite-sample correction
- required p-value: `<= 0.025`

This attacks whether the pre-existing HYP_B1 state has incremental separation specifically on the frozen failed-breakout sessions.

## Claim boundary

Even a complete V11 development pass means only:

`INCREMENTAL_MECHANISM_CANDIDATE`

It does not mean certified strategy, execution viability, option profitability, prospective support, live authority, or broker authority.

If any development gate fails, V11 closes in development. Do not create a nearby HYP_B1 threshold, altered reclaim window, different opening range, or relaxed gate to rescue it.
