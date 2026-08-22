# Raj Arora Participation-Intensity V10 — Development Verdict

Status: `CLOSED_IN_DEVELOPMENT_NO_FAMILY_ADVANCES`

Research-only. Constituent membership remains an available-basket proxy. Validation and holdout remain untouched.

## Outcome-blind feature thresholds

V10 used only medians of V9 constituent-participation features, not post-entry P&L optimization:

```text
breakout_volume_expansion_breadth_median = 0.0784313725
reclaim_volume_expansion_breadth_median = 0.3529411765
aligned_reclaim_participation_breadth_median = 0.2549019608
```

Six symmetric high/low families were frozen before V10 outcome access.

## Results

| Family | 30m N | Mean @5bps | Mean @7.5bps | +1 bar delay | Pair separation | Top-5 / total net | Advance |
|---|---:|---:|---:|---:|---:|---:|---|
| Break-volume intensity high | 20 | +3.865 | +1.365 | +1.454 | +0.619 | 120.0% | NO |
| Break-volume intensity low | 13 | +3.246 | +0.746 | +4.930 | -0.619 | 198.7% | NO |
| Reclaim-volume intensity high | 21 | +3.551 | +1.051 | +1.669 | -0.191 | 156.0% | NO |
| Reclaim-volume intensity low | 12 | +3.743 | +1.243 | +5.152 | +0.191 | 122.0% | NO |
| Aligned participation high | 21 | +1.618 | -0.882 | +0.337 | -5.508 | 276.9% | NO |
| Aligned participation low | 12 | **+7.126** | **+4.626** | **+7.082** | **+5.508** | **102.7%** | NO |

`FAMILY_ADVANCE_COUNT=0`

## Strongest V10 observation

The low-aligned-participation subset is numerically strong:

```text
trades=12
15m mean @5bps=+1.662
30m mean @5bps=+7.126
45m mean @5bps=+8.021
30m mean @7.5bps=+4.626
one-extra-5m delay=+7.082
chronological block means≈[+1.537, +12.846, +7.094]
paired high-alignment separation=+5.508 bps
```

It does **not** advance because:

- frozen minimum support was 15 trades; observed support is 12;
- top-five positive trades contribute approximately `102.7%` of total net return, failing the <=80% concentration gate.

The support or concentration gates are not relaxed after seeing this result.

## Current-information-set verdict

V7-V10 have now tested, without validation access:

- simple constituent breadth confirmation/nonconfirmation;
- breadth intensity and basket break depth;
- simple constituent volume expansion;
- volume-participation intensity;
- price+volume aligned reclaim participation.

No family passed all frozen development robustness gates. The NIFTY + available constituent-basket proxy search is therefore closed.

```text
V10_DEVELOPMENT_COMPLETE=true
V10_FAMILY_ADVANCE_COUNT=0
CURRENT_NIFTY_PLUS_CONSTITUENT_PROXY_SEARCH=CLOSED
VALIDATION_ACCESSED=false
HOLDOUT_ACCESSED=false
CERTIFIED_STRATEGY=false
STRUCTURAL_EDGE_CERTIFIED=false
```

Further work requires a materially richer information set such as the documented synchronized NIFTY-futures layer, NIFTYBEES, or actual historical option confirmation. More slicing of the same 33 NIFTY failed-breakout events is not justified.
