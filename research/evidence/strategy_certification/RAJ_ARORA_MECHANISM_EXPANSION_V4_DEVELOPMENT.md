# Raj Arora Mechanism Expansion V4 — Development Verdict

Status: `CLOSED_IN_DEVELOPMENT_NO_FAMILY_ADVANCES`

Research-only. No runtime authority. No broker actions. No exact-video-strategy claim. Validation and holdout remain untouched.

## Frozen boundary

- Sessions: `493`
- Rows: `36,849`
- Development: `295` sessions (`2024-07-09` .. `2025-09-15`)
- Validation reserved: `98` sessions (`2025-09-16` .. `2026-02-06`) — **not accessed**
- Holdout reserved: `100` sessions (`2026-02-09` .. `2026-07-08`) — **not accessed**
- Opening range: fixed `10m`
- First meaningful close breakout: downside first, `5 bps` buffer
- Close-break failure: reclaim inside within `2 x 5m` bars
- Base round-trip cost: `5 bps`
- Diagnostic horizons: `15m / 30m / 45m`
- V4 family count: `5`
- Total frozen development cells: `15`

The development-only feature median used by the predeclared compressed-range family was `30.4645 bps` for the first-10m opening-range width. It was computed without outcome data.

## Results

| Family | 30m trades | Mean @5bps | Mean @7.5bps | +1 bar delay | Positive horizons | Positive thirds | Top-5 / total net | Advance |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Strong reclaim to OR midpoint | 6 | +2.031 | -0.469 | -4.836 | 1/3 | 1/3 | 294.5% | NO |
| Bullish reclaim body | 32 | +3.460 | +0.960 | +2.483 | 2/3 | 2/3 | 111.3% | NO |
| Downside wick sweep + same-bar reclaim | 32 | -6.063 | -8.563 | -9.085 | 0/3 | 0/3 | n/a | NO |
| Gap-down exhaustion + close-break failure | 12 | +0.780 | -1.720 | +7.344 | 2/3 | 2/3 | 706.3% | NO |
| Compressed opening range + close-break failure | 15 | +1.897 | -0.603 | -2.947 | 1/3 | 2/3 | 278.5% | NO |

`FAMILY_ADVANCE_COUNT=0`

## Main finding

The only family that came close was `V4_BULLISH_RECLAIM_BODY`:

```text
30m trades=32
mean @5bps=+3.4601 bps/trade
mean @7.5bps=+0.9601 bps/trade
one-extra-5m-entry-delay=+2.4826 bps/trade
positive horizons=2/3
positive chronological thirds=2/3
```

It still failed the predeclared concentration gate because the five largest winners contributed approximately `111.3%` of total net profit. The remaining trades collectively subtract value. This is not a broad structural distribution.

Chronological 30m means for the bullish-reclaim-body family:

```text
first development third : -6.650 bps/trade (10 trades)
middle development third: +7.432 bps/trade (8 trades)
last development third  : +8.411 bps/trade (14 trades)
```

This repeats the V3 regime-instability problem rather than solving it.

## Negative information gained

The `downside wick sweep + same-bar reclaim` mechanism was decisively negative:

```text
15m: -3.708 bps/trade
30m: -6.063 bps/trade
45m: -12.348 bps/trade
```

So the observed behavior is **not** a generic liquidity-sweep/reclaim effect. It specifically depends on a completed downside close-break followed by later re-entry, which is materially different from an intrabar wick rejection.

Gap-down and compressed-range interpretations were too sparse and failed harder-cost/delay or concentration controls. Strong midpoint reclaim was far too sparse.

## Relationship to canonical TradeBot strategy

TradeBot already contains `failed_breakout_trap_v1`, which uses failed-range re-entry plus regime, volume and option-stall/opposite-option confirmation evidence. V4 does not certify or replace that production-family generator. The current price-only corpus cannot reproduce its option-confirmation mechanism.

## Controlled verdict

```text
V4_DEVELOPMENT_COMPLETE=true
V4_FAMILY_ADVANCE_COUNT=0
VALIDATION_ACCESSED=false
HOLDOUT_ACCESSED=false
CERTIFIED_STRATEGY=false
STRUCTURAL_EDGE_CERTIFIED=false
TRADEBOT_INTEGRATION_ALLOWED=false
RUNTIME_AUTHORITY=NONE
BROKER_ACTIONS_PERMITTED=false
```

Further useful work should add a genuinely independent causal information source or a different structural state variable. Repeatedly changing price thresholds, opening windows, reclaim percentages or holding periods is not justified.
