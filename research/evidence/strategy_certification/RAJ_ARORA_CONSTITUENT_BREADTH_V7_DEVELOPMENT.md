# Raj Arora Constituent-Breadth Proxy V7 — Development Verdict

Status: `CLOSED_IN_DEVELOPMENT_NO_FAMILY_ADVANCES`

Research-only. The constituent archive is treated as an equal-weight available-basket proxy, not proven point-in-time NIFTY membership. Validation and holdout remain untouched. No runtime/broker authority is granted.

## Frozen base event

V7 kept the failed-downside-breakout event unchanged:

- 10-minute NIFTY opening range
- first meaningful completed close-break must be downside by at least 5 bps
- completed close back inside within 2 x 5-minute bars
- bullish entry on the next completed 5-minute close
- 5 bps base / 7.5 bps stress round-trip costs
- 15 / 30 / 45-minute horizons

## Constituent proxy audit

Recovered constituent archive:

- 51 symbols in the available basket proxy
- 2,193 real monthly Parquet files (excluding `__MACOSX` duplicates)
- V7 required at least 30 symbols per event
- all 33 development base events had exactly 51 readable symbols
- 714 relevant symbol-month files were decoded for the event months
- decode errors: `0`
- no missing event coverage after the minimum-coverage gate

The constituent files are 1-minute bars. For a NIFTY five-minute bar timestamped at the bar start, V7 used constituent information through the corresponding fourth minute after that timestamp, so a NIFTY 09:35–09:39 completed bar is compared with constituent closes through 09:39. This avoids one-minute/five-minute look-alignment error.

## Frozen breadth definitions

- `breakout_breadth`: fraction of available symbols whose completed constituent close at the NIFTY breakout bar end is below that symbol's session-open price.
- `reclaim_move_breadth`: fraction whose completed close at the NIFTY reclaim bar end is above its close at the breakout bar end.
- `median_breakout_return`: median available-symbol return from session open to breakout-bar completion.
- weighting: equal-weight available-basket proxy.
- missing symbols: excluded, never imputed.

## Results

### Breakout breadth

Only **1 of 33** events had `breakout_breadth < 50%`.

The other **32 of 33** events had majority-negative constituent breadth at the time of the failed NIFTY downside breakout.

At the 30-minute horizon:

```text
BREADTH_NONCONFIRM:
trades=1
mean @5bps=-6.6453 bps

BREADTH_CONFIRM:
trades=32
mean @5bps=+3.9417 bps
mean @7.5bps=+1.4417 bps
one-extra-bar delay=+3.4861 bps
```

The apparent majority-confirm group still failed the concentration gate: top-five positive trades contributed about `97.7%` of total net return. Its chronological thirds remained approximately `-6.65 / +7.58 / +8.41 bps`, repeating the earlier temporal instability.

### Reclaim breadth

All **33 of 33** base events had `reclaim_move_breadth > 50%`.

Therefore majority-positive constituent movement during the NIFTY break-to-reclaim interval is effectively a property of the base event itself, not a discriminator between strong and weak outcomes.

The 30-minute result is therefore identical to the unfiltered V3 center:

```text
trades=33
mean @5bps=+3.62084 bps
mean @7.5bps=+1.12084 bps
one-extra-bar delay=+2.86610 bps
top5 contribution=103.1%
```

### Median basket direction

Only **1 of 33** events had a non-negative median constituent open-to-breakout return. Thus the median-basket divergence hypothesis is also nearly absent. The basket normally confirms the downside break rather than resisting it.

## Mechanism conclusion

V7 falsifies a simple breadth-nonconfirmation explanation:

> The interesting failed-downside-breakout rebound does **not** usually occur because NIFTY breaks while its constituent basket refuses to participate. The downside break is broadly confirmed across the available stock basket, and the subsequent reclaim is also broadly participated in.

Simple majority breadth therefore adds essentially no useful selection information to this proxy family.

```text
V7_BASE_EVENTS=33
V7_EVENTS_WITH_>=30_SYMBOLS=33
V7_SYMBOL_COVERAGE_PER_EVENT=51
V7_FAMILY_ADVANCE_COUNT=0
VALIDATION_ACCESSED=false
HOLDOUT_ACCESSED=false
POINT_IN_TIME_MEMBERSHIP_PROVEN=false
CERTIFIED_STRATEGY=false
STRUCTURAL_EDGE_CERTIFIED=false
TRADEBOT_INTEGRATION_ALLOWED=false
```

A further breadth test is justified only by **breadth intensity / cross-sectional depth**, not by changing the 50% sign threshold. Such a test must use outcome-blind feature medians and symmetric high/low controls, because the V7 majority states are nearly degenerate.
