# Objective Weekly Bearish Structure V1

Status: **RESEARCH-ONLY IMPLEMENTATION CANDIDATE — NOT EDGE CERTIFICATION**

## Why this exists

A TradingView Elliott Wave post proposed that NIFTY may have completed a large
top and entered a multi-year bearish phase. The discretionary wave labels are
not suitable for TradeBot certification because multiple valid Elliott counts
can often be applied to the same chart.

This experiment keeps only the falsifiable market-structure claim.

## Frozen V1 hypothesis

A bearish weekly regime-transition candidate exists only after all of the
following are observable from completed weekly bars:

1. five **confirmed** alternating pivots ending `H-L-H-L-H`;
2. pivot-leg magnitudes contract rather than expand;
3. the second reaction low is above the first reaction low;
4. the final high is near or above the previous high;
5. optional bearish oscillator divergence is recorded as evidence, never
   required retroactively;
6. a later completed weekly close breaks below the last reaction low.

The signal timestamp is the breakdown week, not the final-high week. Pivot
confirmation requires right-side bars. This prevents the detector from using
future information while pretending the pattern was known earlier.

## Explicit non-goals

This is **not**:

- an Elliott Wave labeller;
- evidence that NIFTY has entered a multi-year bear market;
- a strategy;
- an option-entry rule;
- an execution filter;
- a broker/order integration;
- a new truth engine.

It has `broker_write_authority=false` and `order_authority=false`.

## Research sequence

Use this feature only as a descriptive regime covariate.

### Experiment A — forward index returns

For every historical signal, bind outcomes at fixed horizons:

- 1 week;
- 4 weeks;
- 12 weeks;
- 26 weeks;
- 52 weeks.

Compare with unconditional NIFTY forward returns and matched control weeks.
Report sample count, mean/median return, downside frequency, bootstrap
confidence intervals and the full list of event dates. Do not certify on a
single current episode.

### Experiment B — existing strategy interaction

Without changing any strategy rules, compare existing bearish option-buying
strategy outcomes when:

- structure state is confirmed;
- structure state is absent.

This is an interaction/regime test, not permission to tune thresholds until a
survivor appears.

### Experiment C — placebo and robustness

At minimum:

- shift signal timestamps by +/- 4 and +/- 8 weeks;
- vary pivot confirmation window in a predeclared small grid;
- remove oscillator divergence;
- test non-overlapping events;
- compare against simpler baselines such as moving-average/downtrend and
  drawdown regimes.

The structural detector is useful only if it adds information beyond those
simpler regimes.

## Acceptance boundary

A useful research result requires repeated historical events and out-of-sample
stability. A visually convincing match to the current 2026 decline is
insufficient.

Possible dispositions:

- `NO_PREDICTIVE_VALUE`
- `REDUNDANT_WITH_SIMPLE_BEAR_REGIME`
- `CONDITIONAL_SIGNAL_REQUIRES_MORE_EVIDENCE`
- `RESEARCH_SURVIVOR_NOT_CERTIFIED`

No V1 outcome is allowed to imply a certified edge or live-trading authority.
