# Raj Arora Breadth-Intensity V8 — Development Verdict

Status: `CLOSED_IN_DEVELOPMENT_NO_FAMILY_ADVANCES`

Research-only. The constituent set remains an available-basket proxy rather than proven point-in-time NIFTY membership. Validation and holdout remain untouched.

## Outcome-blind thresholds

V8 used only medians of V7 breadth **features**, computed without post-entry strategy returns:

```text
breakout_breadth_median = 0.6862745098
reclaim_move_breadth_median = 0.7647058824
median_breakout_return_median = -0.0032526882
```

No additional NIFTY threshold or holding-period search was performed.

## Results

| Family | 30m N | Mean @5bps | Mean @7.5bps | +1 bar delay | Pair separation | Top-5 / total net | Advance |
|---|---:|---:|---:|---:|---:|---:|---|
| Break breadth high | 20 | +2.185 | -0.315 | +4.529 | -3.646 | 222.5% | NO |
| Break breadth low | 13 | +5.830 | +3.330 | +0.436 | +3.646 | 110.9% | NO |
| Reclaim breadth high | 19 | +3.179 | +0.679 | +1.880 | -1.042 | 181.5% | NO |
| Reclaim breadth low | 14 | +4.221 | +1.721 | +4.135 | +1.042 | 106.5% | NO |
| Break depth shallow | 17 | +0.629 | -1.871 | -3.456 | -6.170 | 789.9% | NO |
| Break depth deep | 16 | **+6.799** | **+4.299** | **+10.031** | **+6.170** | **89.5%** | NO |
| Dual high participation | 15 | +1.938 | -0.562 | +4.648 | n/a | 334.4% | NO |

`FAMILY_ADVANCE_COUNT=0`

## Strongest observation: deep basket selloff

The `V8_BREAK_DEPTH_DEEP` subset is the strongest breadth result so far:

```text
trades=16
mean @5bps=+6.7992 bps/trade
mean @7.5bps=+4.2992 bps/trade
one-extra-5m-entry-delay=+10.0307 bps/trade
paired shallow-control separation=+6.1698 bps/trade
positive horizons=2/3
chronological blocks≈[-0.404, +5.455, +9.798] bps/trade
```

It still fails the frozen concentration gate:

```text
top5_positive_contribution_fraction=0.8951
required<=0.80
```

The first chronological development block is also still slightly negative. V8 therefore does not advance and no null/validation access is authorized.

## Interpretation

A failed NIFTY downside break appears more favorable when the constituent basket has sold off **more deeply**, not when breadth refuses to confirm the break. That supports an exhaustion/reversal interpretation more than a breadth-divergence interpretation.

However, V8 still does not establish a broad, stable distribution of edge. The concentration gate is intentionally not relaxed after seeing this near-pass.

The next justified independent mechanism is participation/volume, which is also closer to TradeBot's canonical `failed_breakout_trap_v1` contract. A volume test must be frozen before constituent-volume outcomes are read and should use relational/sign rules rather than optimized numeric cutoffs.

```text
V8_DEVELOPMENT_COMPLETE=true
V8_FAMILY_ADVANCE_COUNT=0
VALIDATION_ACCESSED=false
HOLDOUT_ACCESSED=false
POINT_IN_TIME_MEMBERSHIP_PROVEN=false
CERTIFIED_STRATEGY=false
STRUCTURAL_EDGE_CERTIFIED=false
```
