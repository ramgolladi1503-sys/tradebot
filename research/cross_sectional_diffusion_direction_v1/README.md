# Cross-Sectional Diffusion Direction V1

Campaign ID: `HYP_CROSS_SECTIONAL_DIFFUSION_DIRECTION_V1`  
Frozen spec: **V1.2.0**

## Question

When historically valid NIFTY constituents move coherently and their cross-sectional impulse diverges from the NIFTY's own recent move, does NIFTY continue in that direction over the next **15 minutes** strongly enough to survive an explicit round-trip cost assumption?

The 30-minute horizon is secondary diagnostics only. It cannot rescue a failed 15-minute primary result.

This is a **derived executable hypothesis**. It is not presented as the exact formula from any paper or website. External work supplies the mechanism; this campaign explicitly owns and freezes the implementation choices.

## Causal feature definition

For constituent `i` at completed minute `t`:

`r_i,5(t) = ln(C_i(t) / C_i(t-5m))`

For NIFTY:

`r_N,5(t) = ln(C_N(t) / C_N(t-5m))`

Then:

`B_5(t) = sum_i w_i * sign(r_i,5(t))`  — breadth

`I_5(t) = sum_i w_i * r_i,5(t)`  — constituent impulse

`G_5(t) = I_5(t) - r_N,5(t)`  — diffusion/lag gap

All offsets are **exact clock-time offsets**, not row shifts. If `t-5m`, `t+1m`, or the exact horizon bar is absent, another observed row is not substituted.

Historical official weights are used when authoritative. If official historical weights are absent but historical membership is valid, equal weights are an explicit feature choice and are never described as official NIFTY weights.

## Frozen signal family

Only four train-selected threshold pairs exist:

- breadth quantile: `0.80` or `0.90`
- gap quantile: `0.75` or `0.90`

Long:

- `breadth >= train breadth-long threshold`
- `impulse > 0`
- `gap >= train gap-long threshold`

Short is symmetric.

Thresholds are fitted on the training prefix only. Signals are de-overlapped by the primary/secondary horizon in clock time.

## Pre-holdout WFA

The existing REC-MD split is preserved:

- DEV: 297 sessions
- SELECTION: 99 sessions
- HOLDOUT: 100 sessions
- pre-holdout ends: `2026-02-26`
- HOLDOUT begins: `2026-02-27`

V1.2 does **not** evaluate HOLDOUT.

The pre-holdout WFA is:

- expanding training window
- minimum initial training: 126 sessions
- OOS test block: 63 sessions
- step: 63 sessions
- minimum positive-gate OOS folds: 4

This yields four non-overlapping OOS blocks inside the existing DEV+SELECTION population without borrowing the 100-session HOLDOUT.

A positive pre-holdout result is only:

`PRE_HOLDOUT_DIRECTIONAL_SURVIVOR`

It is **not** a certified edge and does not authorize paper/live trading.

## Baseline and falsifier

### Incremental-value baseline

The diffusion signal must beat a frequency-matched **NIFTY 5-minute momentum-only** baseline out of sample. If constituents add no incremental information beyond NIFTY's own recent movement, the hypothesis fails.

### Negative control

The same signal thresholds are applied to constituent features delayed by an exact 30 minutes. If that stale control retains at least 50% of the main estimated effect, the mechanism fails its falsifier gate.

## Execution authority

Preferred execution source:

`data/research/nifty_futures_alignment_v1/NIFTY_SPOT_FUTURES_ALIGNED_V1.parquet`

Expected SHA-256:

`2311981231d3fb847a216c9165ef73c3e7b788ab354d6de493ab1a5edb32e7a9`

The aligned panel already freezes the causal futures roll as:

`NEAREST_UNEXPIRED_EXPIRY_ON_SESSION_START_V1`

No intraday contract switching and no lookahead roll selection are permitted.

The runner directly reads the panel's `spot_open`, `spot_close`, `futures_open`, `futures_close`, and `alignment_valid` fields. In `--aligned-panel` mode, execution authority is granted only when the entire file SHA-256 exactly matches the frozen authority hash above.

Entry is the exact futures open at `t+1 minute`; exit is the exact futures close at `t+horizon`.

Minute candles plus an explicit cost haircut remain an **after-cost candle proxy**, not proof of historical bid/ask fillability, depth, queue position, or market impact.

## Historical constituent authority

A positive pre-holdout verdict requires effective-dated NIFTY membership. Today's NIFTY 50 basket cannot be backfilled into older dates.

Minimum constituent coverage at each event is `0.80`. No synthetic constituent candles, interpolation, or future fill are allowed.

## Pre-holdout survivor gates

The 15-minute primary result must satisfy every gate:

- historical membership marked authoritative
- frozen aligned execution panel authoritative, or equivalent fallback execution authority explicitly supplied
- >= 4 non-overlapping OOS folds
- >= 100 OOS events
- >= 50 OOS sessions
- 95% session-bootstrap lower bound of net return > 0 bps
- >= 60% of OOS folds positive
- no single positive fold > 50% of total positive fold P&L
- 30-minute lagged control estimate < 50% of main estimate
- main estimate > frequency-matched NIFTY momentum-only baseline

Otherwise:

`NO_ROBUST_AFTER_COST_DIRECTIONAL_EDGE`

## Canonical run

```bash
python scripts/run_cross_sectional_diffusion_direction_v1.py \
  --aligned-panel /Users/madhuram/tradebot/data/research/nifty_futures_alignment_v1/NIFTY_SPOT_FUTURES_ALIGNED_V1.parquet \
  --constituents /path/to/HISTORICAL_NIFTY50_1M_PANEL_V5.parquet \
  --membership /path/to/HISTORICAL_NIFTY50_ROSTER_V5.parquet \
  --roundtrip-cost-bps <PREDECLARED_REALISTIC_COST> \
  --membership-authoritative \
  --output runtime/research/cross_sectional_diffusion_direction_v1/pre_holdout_report.json
```

Do not set `--membership-authoritative` unless the roster authority artifact supports the exact membership bytes. Do not invent the cost after seeing results.

Fallback `--index` + `--execution` mode exists for another separately authoritative pair, but the frozen aligned panel is preferred.

## Current status

The campaign implementation is on draft PR #886. It has not been run against the external local `/Volumes/TradeBotData` constituent Parquets from this chat environment, so **no empirical edge is claimed yet**. The remaining empirical action is a local, read-only pre-holdout run against the exact authoritative roster/panel plus the frozen aligned spot/futures panel.
