# Raj Arora Failed-Breakout Asymmetry V2 — Replay Development

Status: `CLOSED_IN_DEVELOPMENT_NO_ROBUST_SURVIVOR`

This is research-only evidence. Validation and holdout were not accessed. Runtime authority remains `NONE`; broker actions remain forbidden.

## Frozen V2 contract

V2 was frozen before V2 outcomes were inspected. It tested a bullish-only reversal after a failed downside opening-range breakout.

- opening range: first `10m / 15m`
- downside breakout buffer: `3 / 5 / 7 bps`
- return-inside failure deadline: `1 / 2 / 3` completed 5m bars
- entry: next completed 5m close after failure confirmation
- fixed horizon: `15 / 30 / 45 minutes`
- total cells: `54`
- base round-trip friction: `5 bps`
- minimum trades: `30`
- required positive adjacent neighbors: `2`
- required positive chronological thirds: `2 of 3`
- one-extra-bar entry delay must remain positive
- top-five positive-trade contribution must be <= `80%` of total net return
- random-direction and session-pairing nulls would run only after the pre-null robustness gates passed

## Replay-source reconciliation

Recovered replay authority:

- NIFTY underlying Parquets: `493`
- total rows: `36,849`
- normal sessions: `491 x 75 bars`
- special sessions: `2 x 12 bars`
- synthetic rows: `0`
- fallback rows: `0`
- mock rows: `0`
- development: `2024-07-09` through `2025-09-15`, `295 sessions`
- validation reserved untouched: `2025-09-16` through `2026-02-06`, `98 sessions`
- holdout reserved untouched: `2026-02-09` through `2026-07-08`, `100 sessions`

These replay rows reconcile exactly to the certified corpus row/session counts, but exact canonical CSV byte equality is still not claimed without SHA-256 `6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8`.

## Result

`PRENULL_ELIGIBLE_COUNT=0`

No V2 cell satisfied the frozen pre-null robustness gates, so randomized controls were not spent and validation remained locked.

Best positive cell by mean among cells with >=30 development trades:

```text
opening_range=10m
breakout_buffer=5bps
failure_max=2 bars
horizon=30m
trades=39
mean_net_5bps=+2.165885787 bps/trade
win_rate=61.54%
total_net=+84.4695 bps
one_bar_delayed_entry_mean=+1.914921365 bps/trade
positive_chronological_thirds=2/3
positive_adjacent_neighbors=0
top5_positive_contribution_fraction=1.45863
```

Chronological thirds for that cell:

```text
first third : 12 trades, -7.56331 bps/trade
middle third: 10 trades, +5.28888 bps/trade
last third  : 17 trades, +7.19650 bps/trade
```

The cell therefore failed both of the most important structural checks:

1. `PARAMETER_NEIGHBORHOOD_STABILITY=FAIL` — zero qualifying positive adjacent neighbors.
2. `PROFIT_CONCENTRATION=FAIL` — the five largest winners exceed total net profit because losses absorb a large fraction of gross gains.

Nearby examples were not supportive:

```text
10m / 5bps / failure<=3 / 30m: 52 trades, -0.24570 bps/trade
10m / 5bps / failure<=2 / 45m: 38 trades, -0.55693 bps/trade
10m / 7bps / failure<=3 / 30m: 35 trades, -1.21896 bps/trade
15m / 5bps / failure<=2 / 30m: 30 trades, -2.81919 bps/trade
```

## Semantic reconciliation with V1

V2 intentionally tested the first later **downside** breakout even if an upside opening-range breakout had already occurred earlier in the same session.

During reconciliation after the V2 result, V1's earlier bullish-asymmetry diagnostic was confirmed to have a narrower event ordering:

- find the **first opening-range breakout in either direction**;
- require that first breakout to be downside;
- require failure back inside the range;
- then evaluate the bullish reversal.

That exact V1 subset reproduced independently on the replay development segment:

```text
all V1 central failed-breakout events: 57 trades, +3.809970731 bps/trade @2bps
first-breakout-downside bullish subset: 33 trades, +6.620837288 bps/trade @2bps
first-breakout-upside bearish subset: 24 trades, -0.054970784 bps/trade @2bps
```

This distinction was discovered after V2 was frozen and run. V2 is therefore preserved as a legitimate negative generation; its rule is not rewritten after the fact.

## Controlled verdict

```text
V2_DEVELOPMENT_COMPLETE=true
V2_PRENULL_ELIGIBLE=0
VALIDATION_ACCESSED=false
HOLDOUT_ACCESSED=false
CERTIFIED_STRATEGY=false
STRUCTURAL_EDGE_CERTIFIED=false
TRADEBOT_INTEGRATION_ALLOWED=false
RUNTIME_AUTHORITY=NONE
V2_VERDICT=CLOSE_NO_ROBUST_SURVIVOR
```

One final separately frozen generation may test the exact V1 first-breakout ordering. If that family does not produce a broad, friction-tolerant development plateau, this Raj-Arora-seeded line should be closed rather than expanded further.
