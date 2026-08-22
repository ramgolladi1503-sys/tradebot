# Raj Arora Seed Line — Independent Reversal-Trap Prior-Evidence Reconciliation

Status: `ADVERSE_INDEPENDENT_PRIOR_EVIDENCE`

This reconciliation was performed after closing V10. It does not authorize additional parameter search and does not access the current 98-session validation or 100-session holdout.

## Independent older evidence recovered from the user's archived research bundles

Three August 2, 2026 evidence bundles predate the current Raj-Arora-seeded V1-V10 sweep:

1. `reversal-trap-public-proxy-evidence.zip`
2. `reversal-trap-description-derived-v2-evidence.zip`
3. `reversal-trap-filter-optimization-v2-evidence.zip`

These are not exact replications of the V1-V10 opening-range event. Their signal geometry is primarily EMA/ATR-envelope reversal/trap logic, including wick rejection and re-entry families. They are therefore broad-family prior evidence rather than exact-candidate evidence.

## Public proxy study

Dataset:

```text
rows=851,076
sessions=2,270
start=2015-01-09 09:15
end=2024-03-26 15:29
cost=5 bps
```

Reported verdict:

`PRELIMINARY_NO_STRUCTURAL_EDGE`

Canonical one-minute test result:

```text
trades=5,765
net expectancy=-5.1372 bps/trade
95% bootstrap CI=[-5.3158, -4.9402]
direct-fade uplift=-0.1581 bps
robustness-positive fraction=0%
positive test chunks=0%
```

The study met minimum trade/session-support gates but failed every profitability/stability gate.

## Description-derived V2

The second independent experiment evaluated `225` predeclared candidate interpretations across nine families, including canonical/recent-outside/dynamic-target/recent-dynamic/wick-rejection/time-stop/direct-fade variants.

Dataset remained the same `851,076` rows / `2,270` sessions. Development used 80% of sessions with four development folds and held the final 20% unopened unless a candidate survived.

Result:

```text
candidate_count=225
development_survivors=0
holdout_opened=false
```

Best development candidate:

```text
family=wick_rejection
ATR length=7
multiplier=3.0
trades=21,375
gross expectancy=-0.0204 bps/trade
net expectancy after 5bps=-5.0204 bps/trade
folds=[-4.8820, -4.9908, -5.1165, -5.0825]
positive_fold_fraction=0
neighbor_positive_fraction=0
uplift_over_direct_fade=-0.2199 bps/trade
```

The locked holdout correctly remained unopened.

## Filter-optimization V2

A separate archived search attempted to rescue reversal-trap behavior using filters.

Search pressure:

```text
stage1 configurations=4,752
stage2 configurations=500
winner selected without holdout=true
```

Even the selected development winner had negative cross-validation:

```text
CV score=-4.0068 bps/trade
folds=[-4.6006, -4.0552, -3.1618, -2.5327]
positive development fold fraction=0
```

Locked holdout:

```text
trades=137
gross expectancy=+0.7346 bps/trade
net expectancy after 5bps=-4.2654 bps/trade
95% CI=[-6.0236, -2.5876]
first half=-5.8189 bps/trade
second half=-3.0185 bps/trade
positive months=17.4%
direct-fade net=-4.2273 bps/trade
trap uplift over direct=-0.0381 bps/trade
```

Reported verdict:

`NO_ROBUST_FILTERED_EDGE`

## Relationship to current V1-V10

The current externally seeded line uses different geometry: short opening range, first downside close-break, rapid re-entry, bullish next-bar entry, and fixed forward horizons. Therefore the older experiments cannot directly invalidate the current event definition.

They do, however, provide strong **adverse prior evidence** against the proposition that generic reversal/trap geometry becomes robust through additional filters or nearby rule variations.

This matters because V1-V10 already show the same warning pattern on the newer 2024-2025 development corpus:

- strong-looking local subsets;
- weak early-period stability;
- parameter/state islands;
- high winner concentration;
- no full frozen development robustness pass;
- no authorized validation access.

## Controlled conclusion

```text
OLDER_REVERSAL_TRAP_PRIOR=STRONGLY_NEGATIVE
OLDER_DATA=2015_TO_2024_MARCH
OLDER_SESSIONS=2270
OLDER_FILTER_SEARCH=FAILED_LOCKED_HOLDOUT
CURRENT_V1_TO_V10=NO_FULL_DEVELOPMENT_ROBUSTNESS_PASS
CURRENT_VALIDATION_ACCESSED=false
CURRENT_HOLDOUT_ACCESSED=false
MORE_SAME_INFORMATION_FILTERING=NOT_JUSTIFIED
```

The only justified continuation is with a materially richer causal information set that the production failed-breakout mechanism actually expects: synchronized futures/ETF context and/or real historical option confirmation. The current NIFTY + constituent proxy should not be sliced further.
