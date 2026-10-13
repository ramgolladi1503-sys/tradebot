# VWAP Failed Discovery → Return to Value — Hypothesis V1

## Stage

`HYPOTHESIS_FROZEN`

This package is deliberately **not a strategy**. It asks whether one market phenomenon exists strongly enough to deserve later strategy design.

Safety boundary:

- read_only=true
- broker_api_called=false
- is_order_action=false
- option_data_used=false
- allowed_for_strategy_design=false until robust support
- allowed_for_runtime_wiring=false
- allowed_for_live_execution=false

## Research question

After NIFTY futures establishes accepted price discovery outside a causal, volume-weighted VWAP band and then fails back inside value while still remaining on the same side of VWAP, does price rotate to the frozen signal-time VWAP more often than comparable non-event states?

### H0

After conditioning on time of day and volatility, failed discovery has no greater probability than matched controls of reaching signal-time VWAP before re-breaking the failed discovery extreme, and no positive directional-return uplift.

### H1

After conditioning on time of day and volatility, failed discovery has a materially greater probability than matched controls of reaching signal-time VWAP before re-breaking the failed discovery extreme, with positive directional-return uplift.

## Why futures, not NIFTY spot VWAP

The hypothesis requires traded-volume truth. Index spot has no authoritative exchange-traded volume suitable for session VWAP. Therefore V1 requires active NIFTY futures 1-minute OHLCV with finite strictly positive traded volume. Unit-weight or synthetic-volume VWAP is rejected.

## Frozen detector

For each completed 1-minute futures bar:

```text
TP_t      = (H_t + L_t + C_t) / 3
VWAP_t    = Σ(TP_i × V_i) / Σ(V_i)
σ_t       = sqrt(Σ(V_i × TP_i²)/Σ(V_i) - VWAP_t²)
z_t       = (C_t - VWAP_t) / σ_t
ER_t      = |C_t - C_t-L| / Σ|ΔC|
Slope_t   = (VWAP_t - VWAP_t-L) / ATR14_t
```

Accepted upside discovery requires:

```text
at least 4 of the last 5 closes at z >= +1.0
AND ER10 >= 0.55
AND VWAP slope over 10 bars >= +0.05 ATR
```

Accepted downside discovery is symmetric.

A failed discovery event requires an accepted discovery in the previous 8 bars and then a completed bar that has re-entered to:

```text
0 < z <= +0.75      after upside discovery
-0.75 <= z < 0      after downside discovery
```

The failure bar must remain on the same side of VWAP. That matters because touching VWAP is the primary outcome and cannot already have happened at event formation.

One accepted discovery episode can emit at most one failure event.

## Primary endpoint

Within 30 minutes after the event:

```text
SUCCESS = frozen signal-time VWAP is touched
          before the frozen discovery extreme is re-broken
```

If both target and invalidation can have occurred inside the same 1-minute bar, V1 counts **invalidation first**. This is intentionally adverse.

The primary statistic is:

```text
Risk Difference = P(success | failed discovery)
                - P(success | matched non-event control)
```

The frozen minimum effect required for support is +5 percentage points, with at least 100 matched DEV events.

## Secondary endpoints

Measured at 1, 3, 5, 10, 15 and 30 minutes:

- directional return toward VWAP in bps;
- maximum favorable excursion;
- maximum adverse excursion;
- time to VWAP.

These are research outcomes, not trade P&L.

## Matched controls

A control must:

1. not be a failed-discovery event;
2. occupy the same same-side re-entry zone (`0 < |z| <= 0.75`);
3. have no accepted discovery in the prior 8 bars;
4. imply the same expected rotation direction;
5. be in the same 30-minute time-of-day bucket;
6. be in the same ATR14/close volatility bucket;
7. be from a different trading date;
8. not be reused.

Tie-break is deterministic: minimum ATR/close distance, then minimum absolute-z distance, then earliest timestamp.

This design asks whether **the failed-discovery history itself** adds information beyond merely being near VWAP on the same side.

## Validation order

The order is strict:

```text
1. DEV event support and primary endpoint
2. matched-control comparison
3. negative controls
4. small parameter-neighborhood robustness
5. month / volatility / time-of-day concentration checks
6. walk-forward OOS
7. independent oracle reproduction
8. untouched holdout
```

The holdout may not be used to alter the V1 formula. Any rewrite after outcome access creates V2 and requires a new untouched holdout boundary.

## Verdicts

`REJECTED`
: Sufficient DEV support exists but the frozen primary/secondary effect fails.

`INCONCLUSIVE`
: There is not enough valid event/control support to make a defensible claim.

`SUPPORTED`
: DEV shows the frozen effect, but one or more robustness/OOS/oracle/holdout gates remain unproven.

`ROBUSTLY_SUPPORTED`
: DEV, negative controls, robustness, OOS, independent oracle and untouched holdout all pass under the frozen contract.

Only `ROBUSTLY_SUPPORTED` may open a **new, separately versioned strategy-design candidate**.

## Explicitly forbidden in this stage

No code or analysis in H1 V1 may optimize or decide:

- CE/PE selection;
- strike or DTE;
- option bid/ask fills;
- entry timing as a trade;
- stop-loss;
- profit target;
- position sizing;
- risk percentage;
- capital allocation;
- paper/live promotion.

Those are strategy/commercialization questions and are intentionally downstream.

## What happens if H1 survives

A new candidate such as `VWAP_FAILED_DISCOVERY_RTV_STRATEGY_V1` may then ask how to monetize the supported effect. That strategy must undergo its own executable-option replay, costs, slippage, paper validation and commercialization gates.

If H1 fails, there is no strategy-design phase. The negative result is preserved.
