# Raj Arora Structural-State V5 — Development Verdict

Status: `CLOSED_IN_DEVELOPMENT_NO_FAMILY_ADVANCES`

Research-only. Validation and holdout remain untouched. Runtime authority remains `NONE`; broker actions remain forbidden.

## Frozen search

V5 kept the exact V3/V4 base event fixed: 10-minute opening range, first completed close-break must be downside by at least 5 bps, re-entry inside within two completed 5-minute bars, bullish entry on the next completed 5-minute close, 5-bps base round-trip cost, 7.5-bps stress cost, and 15/30/45-minute horizons.

No numeric threshold grid was searched. Six discrete structural states were frozen before V5 outcome access.

## Results

| Family | 30m trades | Mean @5bps | Mean @7.5bps | +1 bar delay | Positive horizons | Positive thirds | Top-5 / total net | Advance |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Higher-low reclaim | 16 | +3.751 | +1.251 | +2.992 | 2/3 | 2/3 | 157.8% | NO |
| Bullish engulfing reclaim | 10 | -0.549 | -3.049 | +0.558 | 0/3 | 2/3 | n/a | NO |
| Opening-up context | 6 | -1.510 | -4.010 | -0.116 | 1/3 | 2/3 | n/a | NO |
| Opening-down context | 27 | +4.761 | +2.261 | +3.554 | 2/3 | 2/3 | 92.2% | NO |
| Early failure | 16 | +5.052 | +2.552 | +4.378 | 3/3 | 2/3 | 113.1% | NO |
| Late failure | 17 | +2.274 | -0.226 | +1.354 | 2/3 | 2/3 | 234.1% | NO |

`FAMILY_ADVANCE_COUNT=0`

## Strongest supported observations

### Opening-down context

The most substantial V5 subset was the symmetric `V5_OPENING_DOWN_CONTEXT` state:

```text
30m trades=27
mean @5bps=+4.7609 bps/trade
mean @7.5bps=+2.2609 bps/trade
one-extra-bar delay=+3.5542 bps/trade
positive horizons=2/3
positive chronological thirds=2/3
top5 positive contribution=92.2%
```

Chronological thirds:

```text
first third : -4.685 bps/trade (7 trades)
middle third: +6.723 bps/trade (7 trades)
last third  : +8.791 bps/trade (13 trades)
```

It fails the predeclared concentration gate and repeats the same early-development weakness seen in V3/V4.

### Early failure

`V5_EARLY_FAILURE` was stronger across horizons but too sparse:

```text
30m trades=16
mean @5bps=+5.0516 bps/trade
mean @7.5bps=+2.5516 bps/trade
one-extra-bar delay=+4.3782 bps/trade
positive horizons=3/3
first third=-9.804 bps/trade
middle third=+8.995 bps/trade
last third=+11.012 bps/trade
top5 positive contribution=113.1%
```

This is interesting descriptive behavior, not an admissible candidate.

## Negative information

- Classic bullish-engulfing reclaim is not the mechanism.
- Opening-up context is weak and sparse.
- Higher-low structure improves the later-period behavior but still has insufficient support and severe concentration.
- Late failures do not survive the harder 7.5-bps cost.

## Controlled conclusion

The recurring pattern across V3, V4 and V5 is now clear: the apparent failed-downside-breakout rebound effect is materially stronger in later development regimes than in the earliest development regime. More event-threshold tuning is not justified.

The next defensible test is an ex-ante regime-state family using only information available before each session: prior multi-session direction, prior-session direction, and trailing realized-volatility state. These are intended to test whether the temporal instability has a causal observable state representation rather than a hidden date cutoff.

```text
V5_DEVELOPMENT_COMPLETE=true
V5_FAMILY_ADVANCE_COUNT=0
VALIDATION_ACCESSED=false
HOLDOUT_ACCESSED=false
CERTIFIED_STRATEGY=false
STRUCTURAL_EDGE_CERTIFIED=false
TRADEBOT_INTEGRATION_ALLOWED=false
```
