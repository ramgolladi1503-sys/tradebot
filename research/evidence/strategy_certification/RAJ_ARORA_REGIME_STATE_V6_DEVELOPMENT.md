# Raj Arora Regime-State V6 — Development Verdict

Status: `CLOSED_IN_DEVELOPMENT_NO_FAMILY_ADVANCES`

Research-only. Validation and holdout remain untouched. No runtime or broker authority.

## Frozen regime search

V6 kept the failed-downside-breakout event fixed and conditioned it only on information known before the current session. Six symmetric ex-ante regime states were frozen: prior-5-session return sign, previous-session body sign, and trailing-20-session realized-volatility above/below an outcome-blind development feature median.

The trailing-20-session realized-volatility development-feature median was `0.0074531629` (about `0.7453%` daily close-to-close standard deviation). No strategy outcomes were used to choose it.

## Results

| Family | 30m trades | Mean @5bps | Mean @7.5bps | +1 bar delay | Positive horizons | Positive thirds | Top-5 / total net | Pair separation | Advance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Prior 5 sessions negative | 17 | +3.110 | +0.610 | +0.857 | 2/3 | 2/3 | 183.2% | -1.055 | NO |
| Prior 5 sessions positive | 16 | +4.164 | +1.664 | +4.876 | 2/3 | 2/3 | 127.6% | +1.055 | NO |
| Previous session bearish | 18 | +2.500 | +0.000 | -0.283 | 2/3 | 2/3 | 173.7% | -2.466 | NO |
| Previous session bullish | 15 | +4.966 | +2.466 | +6.435 | 2/3 | 2/3 | 139.2% | +2.466 | NO |
| Trailing volatility high | 20 | +5.629 | +3.129 | +4.237 | 2/3 | 2/3 | 76.9% | +1.194 | NO |
| Trailing volatility low | 10 | +4.435 | +1.935 | +1.389 | 2/3 | 1/3 | 193.8% | -1.194 | NO |

`FAMILY_ADVANCE_COUNT=0`

## Near-pass: high trailing volatility

`V6_TRAILING_VOL_HIGH` was the first family in this research line to pass support, harder-cost, entry-delay, horizon, chronological-stability, and profit-concentration gates simultaneously:

```text
trades=20
mean @5bps=+5.6287 bps/trade
mean @7.5bps=+3.1287 bps/trade
one-extra-bar delay=+4.2366 bps/trade
positive horizons=2/3
positive chronological thirds=2/3
top5 contribution=76.9%
```

Chronological thirds at the 30-minute horizon:

```text
first third : -0.697 bps/trade (4 trades)
middle third: +7.580 bps/trade (9 trades)
last third  : +6.734 bps/trade (7 trades)
```

However, the frozen paired-control requirement was not met. The high-volatility mean exceeded the low-volatility mean by only `+1.194 bps/trade`, below the predeclared `+2.0 bps` minimum. Low-volatility events were also positive, so volatility does not provide sufficient incremental separation to claim it explains the effect.

No null controls or validation were run because the full pre-null gate did not pass.

## Interpretation

The high-volatility state materially improves distribution quality and reduces the extreme concentration seen in V3-V5, but it is not a strong enough discriminator against its symmetric low-volatility control. Prior trend and prior-session direction also do not explain the recurring temporal instability cleanly.

The next justified expansion must add an independent contemporaneous information source rather than another NIFTY-only state. A constituent-breadth proxy is available in the recovered archive and can test whether the failed NIFTY breakdown is unsupported by the broader stock basket or whether breadth actively reverses with the reclaim.

```text
V6_DEVELOPMENT_COMPLETE=true
V6_FAMILY_ADVANCE_COUNT=0
VALIDATION_ACCESSED=false
HOLDOUT_ACCESSED=false
CERTIFIED_STRATEGY=false
STRUCTURAL_EDGE_CERTIFIED=false
```
