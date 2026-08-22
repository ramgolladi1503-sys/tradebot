# Raj Arora First-Breakout-Downside V3 — Final Verdict

Status: `CLOSED_IN_DEVELOPMENT_NO_ROBUST_SURVIVOR`

This is the final bounded generation for this external-video-seeded research line. It is research-only, claims no exact replication of Raj Arora's strategy, grants no runtime authority, permits no broker action, and does not certify an edge.

## Frozen V3 mechanism

V3 was frozen before V3 outcomes were inspected and preserved the exact ordering behind the V1 directional asymmetry:

1. build the opening range from the first `10m / 15m`;
2. observe the **first** later completed close outside either opening-range boundary by `3 / 5 / 7 bps`;
3. require that first breakout to be **downside**; if the first breakout is upside, the session produces no signal;
4. require a later completed close back inside the opening range within `1 / 2 / 3` bars;
5. enter bullish on the next completed 5m close;
6. evaluate fixed `15 / 30 / 45 minute` horizons.

Frozen development budget: `54 cells`.

Harder V3 economics and gates:

- base round-trip friction: `5 bps`
- minimum trades: `30`
- one-extra-bar delayed entry must remain positive
- at least `2/3` chronological development thirds positive
- at least `2` positive adjacent parameter neighbors with >=25 trades
- top-five positive-trade contribution <= `80%` of total net
- null controls would run only after the pre-null gates passed

## Data boundary

Replay-source reconciliation remained exact on structural counts:

```text
sessions=493
rows=36849
synthetic_rows=0
fallback_rows=0
mock_rows=0
development_sessions=295
validation_sessions_reserved=98
holdout_sessions_reserved=100
```

Chronological boundaries:

```text
development: 2024-07-09 .. 2025-09-15
validation : 2025-09-16 .. 2026-02-06   UNTOUCHED
holdout    : 2026-02-09 .. 2026-07-08   UNTOUCHED
```

Exact canonical CSV byte equality is still not claimed without the pinned SHA-256:

`6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8`

## V3 result

```text
PRENULL_ELIGIBLE_COUNT=0
VALIDATION_ACCESSED=false
HOLDOUT_ACCESSED=false
```

No cell satisfied the frozen pre-null robustness gates.

### Best V3 cell

The V1-derived center remained the strongest cell:

```text
opening_range=10m
breakout_buffer=5bps
failure_max=2 bars
horizon=30m
first_breakout_must_be_downside=true
trades=33
mean_net_5bps=+3.620837288 bps/trade
one_bar_delayed_entry_mean=+2.866104 bps/trade
positive_chronological_thirds=2/3
positive_adjacent_neighbors=1
 top5_positive_contribution_fraction=1.031151
```

Chronological thirds:

```text
first third : -6.650 bps/trade
middle third: +7.580 bps/trade
last third  : +8.411 bps/trade
```

This is the central reason the family is rejected: the apparent edge is absent in the first development regime and emerges later. That is not a stable two-year opening-auction effect under the frozen definition.

The top-five winning trades contribute approximately `103%` of total net V3 profit, meaning the remaining trades collectively subtract value. This fails the frozen concentration gate.

Only one adjacent parameter neighbor was positive; V3 required at least two. The result is therefore still a parameter island, not a plateau.

### Nearby cells

Examples with >=30 trades at the same 5-bps cost:

```text
10m / 5bps / failure<=2 / 45m: 32 trades, +2.40885 bps/trade
10m / 5bps / failure<=3 / 45m: 44 trades, +0.61157 bps/trade
10m / 5bps / failure<=3 / 30m: 45 trades, +0.49948 bps/trade
15m / 5bps / failure<=3 / 45m: 38 trades, -0.23678 bps/trade
10m / 7bps / failure<=3 / 30m: 30 trades, -0.98863 bps/trade
10m / 5bps / failure<=2 / 15m: 33 trades, -1.52897 bps/trade
```

The positive area does not broaden sufficiently across the declared neighborhood.

## Relationship to V1 and V2

### V1

V1 found a development-only failed-breakout reversal candidate at 2-bps cost:

```text
57 both-direction trades
+3.80997 bps/trade
```

Direction decomposition subsequently showed:

```text
first breakout downside -> bullish reversal:
33 trades, +6.62084 bps/trade @2bps

first breakout upside -> bearish reversal:
24 trades, -0.05497 bps/trade @2bps
```

That decomposition could not be used to rewrite V1, so it seeded later generations.

### V2

V2 tested a broader rule: the first later downside breakout could qualify even if an upside breakout had occurred earlier. V2 produced no robust survivor and was closed.

### V3

V3 returned to the exact V1 first-breakout ordering and raised base friction to 5 bps. The center remained positive, proving the V1 asymmetry was reproducible under the exact ordering, but it still failed stability, neighborhood and concentration requirements.

## Final controlled conclusion

The research line has produced a useful market-behavior observation but not a certifiable strategy:

> When NIFTY's first meaningful break of a short opening range is downward and that break quickly fails, subsequent bullish movement is stronger in parts of the development corpus than the symmetric bearish reversal. However, the effect is regime-dependent, parameter-sensitive and concentrated in a small number of winners.

That is insufficient for strategy certification.

```text
RAJ_ARORA_EXTERNAL_SEED_LINE=EXHAUSTED_AND_CLOSED
V1=INTERESTING_DEVELOPMENT_SEED_NOT_ROBUST
V2=CLOSED_NO_ROBUST_SURVIVOR
V3=CLOSED_NO_ROBUST_SURVIVOR
VALIDATION_ACCESSED=false
HOLDOUT_ACCESSED=false
EXACT_VIDEO_STRATEGY_REPLICATED=false
CERTIFIED_STRATEGY=false
STRUCTURAL_EDGE_CERTIFIED=false
TRADEBOT_INTEGRATION_ALLOWED=false
RUNTIME_AUTHORITY=NONE
BROKER_ACTIONS_PERMITTED=false
FURTHER_PARAMETER_SEARCH=NOT_JUSTIFIED
```

Do not create V4 by changing thresholds, direction filters, holding periods or opening windows against the same development outcome. A future revisit is justified only by genuinely new external information about the speaker's actual rule set or a materially richer certified information set that introduces a new mechanism rather than more price-only tuning.
