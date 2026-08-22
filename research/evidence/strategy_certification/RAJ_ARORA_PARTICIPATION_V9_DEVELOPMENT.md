# Raj Arora Constituent Participation V9 — Development Verdict

Status: `CLOSED_IN_DEVELOPMENT_NO_FAMILY_ADVANCES`

Research-only. Constituent membership remains an available-basket proxy. Validation and holdout were not accessed.

## Participation construction

For each of the 33 frozen failed-downside-breakout development events and each of the 51 available constituent symbols:

- constituent one-minute volumes were summed over the exact five-minute opening, breakout, and reclaim windows;
- the opening reference was the mean of the first two five-minute constituent volume bars;
- breakout volume expansion = breakout five-minute volume > opening reference;
- reclaim volume expansion = reclaim five-minute volume > breakout five-minute volume;
- aligned reclaim participation = constituent price rose from breakout to reclaim **and** reclaim volume exceeded breakout volume.

All 33 events had 51-symbol coverage. `714` relevant symbol-month Parquets were decoded with `0` errors.

## Feature-state audit

The simple majority states were mostly absent:

```text
median breakout-volume-expansion breadth = 7.84%
range = 0.00% .. 52.94%

median reclaim-volume-expansion breadth = 35.29%
range = 5.88% .. 62.75%

median aligned price+volume reclaim breadth = 25.49%
range = 5.88% .. 62.75%
```

Thus a >50% majority threshold is a stringent structural state, not a commonly occurring property of the base event.

## Results

### Breakout volume expansion

Only `1/33` events had majority constituent breakout-volume expansion. That event lost at the 30-minute horizon.

The other `32/33` events produced:

```text
mean @5bps = +4.0055 bps/trade
mean @7.5bps = +1.5055 bps/trade
one-extra-bar delay = +3.1141 bps/trade
```

but retained the old temporal instability and failed concentration (`top5 ≈96.1%` of total net).

### Reclaim volume expansion

Only `7/33` events had majority reclaim-volume expansion:

```text
30m mean @5bps = +3.2101 bps/trade
30m mean @7.5bps = +0.7101 bps/trade
```

The `26` non-expansion events were also positive, so this state has negligible paired separation (`~0.52 bps`).

### Aligned price + volume reclaim participation

Only `3/33` events had majority aligned reclaim participation. The group is far too sparse and failed the delayed-entry gate.

No event satisfied the dual majority breakout-volume-expansion + aligned-reclaim-participation state.

## Mechanism conclusion

V9 does not support a simple participation-expansion explanation:

> The failed-breakout rebound generally occurs without majority constituent volume expansion relative to the opening reference, and majority reclaim-volume expansion is neither common nor strongly discriminative.

This is useful negative evidence because TradeBot's canonical failed-breakout family uses volume as one supporting input, but the current constituent-basket volume proxy does not show that a simple majority expansion rule explains the observed NIFTY rebound.

One final defensible refinement is an outcome-blind **participation-intensity** split at the feature medians above, analogous to V8. It must be symmetric high/low, contain no optimized P&L threshold, and close the current constituent-proxy search if it does not pass.

```text
V9_FAMILY_ADVANCE_COUNT=0
VALIDATION_ACCESSED=false
HOLDOUT_ACCESSED=false
CERTIFIED_STRATEGY=false
STRUCTURAL_EDGE_CERTIFIED=false
```
