# MACD Futures Participation Regime V1

Research-only successor campaign. It does **not** modify the frozen canonical MACD candidate or its prospective accumulation contract.

## Question

Does a causal NIFTY futures-minus-spot participation state identify when the already-supported path-dependent MACD signal has stronger signal-specific payoff than matched non-signal origins?

## Frozen H1

```text
basis_chg_15m = (futures_close - spot_close) - lag_15m(futures_close - spot_close)
H1_ACTIVE = basis_chg_15m > +8.50 INR
```

`+8.50` is inherited from the previously frozen HYP_B1 development contract. It is not tuned in this campaign.

If H1 has fewer than 30 distinct active MACD signal sessions, H1 closes as `INSUFFICIENT_SUPPORT` before interpreting H1 outcomes and the pre-registered H2 may be computed:

```text
H2_ACTIVE = basis_chg_15m > 0 AND basis_acceleration_15m > 0
```

No magnitude grid is permitted.

## Reuse of canonical MACD payoffs

This lane intentionally does not rewrite the MACD backtester. It binds the existing canonical matched-placebo artifacts:

- `MACD_MATCHED_PLACEBO_ASSIGNMENTS.csv`
- `MACD_SIGNAL_TRADE_PATH_DECOMPOSITION.csv`
- `MACD_MATCHED_PLACEBO_PAYOFF_LEDGER.csv`

The old exact path-dependent payoff remains authoritative. The new code adds only the causal futures state and retains only matched placebo assignments whose futures state equals the paired signal state.

## Required local command

```bash
PYTHONPATH=. python scripts/run_macd_futures_participation_regime_v1.py \
  --aligned-parquet /Users/madhuram/tradebot/data/research/nifty_futures_alignment_v1/NIFTY_SPOT_FUTURES_ALIGNED_V1.parquet \
  --assignments /Volumes/TradeBotData/<canonical_macd_matched_placebo_root>/MACD_MATCHED_PLACEBO_ASSIGNMENTS.csv \
  --signal-paths /Volumes/TradeBotData/<canonical_macd_matched_placebo_root>/MACD_SIGNAL_TRADE_PATH_DECOMPOSITION.csv \
  --placebo-payoffs /Volumes/TradeBotData/<canonical_macd_matched_placebo_root>/MACD_MATCHED_PLACEBO_PAYOFF_LEDGER.csv \
  --output-root /Volumes/TradeBotData/macd_futures_participation_regime_v1_<UTC>
```

Do not guess `<canonical_macd_matched_placebo_root>`; resolve the latest independently verified 148-trade evidence root and bind its SHA-256s.

## Claim boundary

The minimal runner computes only the frozen primary paired estimand and support gate. It does not issue structural certification. Full chronological folds, negative controls, FDR/global multiplicity, delay sensitivity, independent oracle, deterministic rerun, prospective evidence and execution-cost authority remain required.

```text
STRUCTURAL_EDGE_CERTIFIED=false
EXECUTION_VIABLE=UNKNOWN
BROKER_WRITE_AUTHORITY=false
ORDER_AUTHORITY=false
PAPER_AUTHORIZED=false
LIVE_AUTHORIZED=false
```
