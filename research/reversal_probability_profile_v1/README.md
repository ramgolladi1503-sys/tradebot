# Reversal Probability Profile — NIFTY Structure V1

Research-only, causal NIFTY 1-minute campaign derived from the market-structure mechanism described by AlgoAlpha's TradingView indicator **Reversal Probability Profile**:

https://www.tradingview.com/script/ZWLdxZtM-Reversal-Probability-Profile-AlgoAlpha/

## What is being tested

The source concept counts confirmed pivot highs/lows across price bins, smooths nearby bins, and normalizes each bin relative to the densest reversal bin. The source's displayed percentage is therefore **relative reversal density**, not a calibrated probability that the next price move will reverse.

This campaign does not copy the indicator as a trade signal. It tests two economically distinct behaviors around high-density structure:

1. **Rejection / reversal** — price approaches a high-density support/resistance zone, touches it, and closes back away from the zone.
2. **Acceptance / breakout** — price approaches a high-density zone with aligned momentum and closes materially through it.

The four pre-registered candidates are only density 0.65/0.80 crossed with reversal/breakout mode. No large threshold grid is searched.

## Non-negotiable causality rule

A pivot centered at bar `t` with `pivot_right=5` does **not** exist for research purposes until bar `t+5` has closed. The profile can consume the pivot only at that confirmation time. Backdating it to the center bar would be look-ahead bias.

All profile features, ATR, momentum, support/resistance zones, and event decisions use information available at or before the decision bar close.

For a breakout event, the crossing bar is tested against the **prior bar's already-known support/resistance zone**, not a same-bar zone re-selected after price has already crossed it. This avoids a self-referential breakout definition.

## Execution/outcome mapping

- Decision: event bar close.
- Entry: next exact 1-minute bar open, same session.
- Primary outcome: 15-minute close from decision time.
- Diagnostics: 20-minute and 30-minute closes.
- Fixed research cost proxy: 5 bps round trip by default.
- Events are de-overlapped by the primary horizon.

This is an underlying-direction experiment. It does not infer CE/PE premium P&L from NIFTY OHLC.

## Controls

The campaign compares OOS event returns against:

- **same-event momentum baseline** — use the sign of the already-known 5-minute momentum at the exact same event timestamps;
- **+30 minute shifted-time negative control** — preserve the event's signal direction but move the decision clock 30 minutes later within the same session and apply the same next-open/15-minute outcome rule.

A positive verdict requires incremental value versus both controls.

## Walk-forward protocol

Default rolling WFA:

- 189 training sessions
- 63 OOS sessions
- 63-session step
- train-only selection among the four frozen candidates
- minimum 4 OOS folds
- minimum 100 OOS events and 50 OOS sessions
- session bootstrap 95% CI lower bound after cost must be > 0
- at least 60% positive folds
- gross directional hit rate >= 52%
- >= 0.50 bps incremental value versus same-event momentum
- >= 0.50 bps incremental value versus the shifted-time control
- no single fold may contribute > 60% of positive fold P&L

The strongest possible V1 verdict is `ROBUST_DIRECTIONAL_EDGE_AFTER_COST_PROXY`. That is not exact fillability, option profitability, or live-trading certification.

## Input contract

The generic runner accepts CSV or Parquet with:

```text
timestamp, open, high, low, close
```

It also accepts the aligned-corpus aliases:

```text
timestamp, spot_open, spot_high, spot_low, spot_close
```

Timestamps are normalized to `Asia/Kolkata`; only 09:15–15:30 bars are admitted.

## Verified NIFTY authority binding

`verified_data_binding.json` pins the two historical 1-minute NIFTY authorities already established by TradeBot research evidence:

```text
UPSTOX_NIFTY_SPOT_REPAIRED_V1
sha256=0d615f7e490735f0c065338f6fc7cd15c4d3997a2a22f162573c9c5eefaf6d1e
reported_sessions=497

NIFTY_SPOT_FUTURES_ALIGNED_V1
sha256=2311981231d3fb847a216c9165ef73c3e7b788ab354d6de493ab1a5edb32e7a9
reported_sessions=497
```

The verified runner fails closed unless the actual file bytes match one of those exact hashes. A matching filename, row count, or reconstructed equivalent is not accepted as authority.

Preferred command on the TradeBot machine:

```bash
cd /Users/madhuram/tradebot
PYTHONPATH=. python scripts/run_rpp_verified_nifty_v1.py
```

It checks the historical repo paths and common `/Volumes/TradeBotData` externalized paths automatically. An explicit candidate is allowed but must still match an accepted SHA:

```bash
PYTHONPATH=. python scripts/run_rpp_verified_nifty_v1.py \
  --input /exact/path/to/NIFTY_SPOT_FUTURES_ALIGNED_V1.parquet \
  --output-dir research/evidence/reversal_probability_profile_v1 \
  --cost-bps 5
```

## Generic run

For engineering tests or explicitly unbound research data:

```bash
PYTHONPATH=. python scripts/run_reversal_probability_profile_v1.py \
  --input /path/to/nifty_1m.csv \
  --output-dir /path/to/rpp_v1_results \
  --cost-bps 5
```

Outputs:

```text
report.json
causal_profile_features.parquet
```

If no Parquet engine is installed, the feature artifact falls back to `causal_profile_features.csv` and `report.json` records that fact explicitly.

## Safety / claim boundary

Research only. No broker calls, order paths, paper trading, live execution, strike selection, or option-P&L claims are authorized by this campaign. Holdout remains untouched by V1 unless a separate explicit holdout protocol is opened after the WFA result warrants it.
