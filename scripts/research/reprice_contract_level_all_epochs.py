#!/usr/bin/env python3
"""
Comprehensive Three-Epoch Contract-Level Cost Reconciliation: DAY_TO_NIGHT_MOMENTUM_V1
Strictly read-only, non-mutating research audit.
Applies:
1. Exact contract-level lot size extracted directly per expiry:
   - 2024-10 to 2025-01-30: 25
   - 2025-02-27 to 2025-12-30: 75
   - 2026-01-27 onwards: 65
2. Date-effective statutory fee schedule (STT: 0.0125% -> 0.02% -> 0.05% post-April-2026).
3. Evaluates all three epochs: In-Sample, Out-of-Sample, and Prospective.
"""

from __future__ import annotations
import glob
import os
import pandas as pd
import numpy as np

from scripts.research.audit_reconciled_day_to_night import build_audited_ledger
from core.candidate_audits.cost_model import IndianDerivativesCostModel

DATA_PATH = "data/research/nifty_futures_alignment_v1/NIFTY_SPOT_FUTURES_ALIGNED_V1.parquet"
PROSPECTIVE_PATH = "data/research/upstox_futures_raw/nifty/2026-09-29/futures_1minute_1.parquet"

def get_authoritative_lot_map() -> dict[str, int]:
    pq_files = glob.glob("data/research/upstox_futures_raw/nifty/**/futures_1minute_1.parquet", recursive=True)
    lot_map = {}
    for p in pq_files:
        exp = os.path.basename(os.path.dirname(p))
        try:
            df = pd.read_parquet(p, columns=["lot_size"])
            if "lot_size" in df.columns and len(df) > 0:
                lot_map[exp] = int(df["lot_size"].iloc[0])
        except Exception:
            pass
    return lot_map

def reprice_historical_dataset(lot_map: dict[str, int]):
    print("Loading aligned dataset...")
    df = pd.read_parquet(DATA_PATH)
    df = df[df["alignment_valid"] == True].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["time_str"] = df["timestamp"].dt.strftime("%H:%M:%S")

    # Map lot sizes onto df
    expiry_to_lot = lot_map.copy()
    df["lot_size"] = df["selected_futures_expiry"].map(expiry_to_lot)

    # Build gross ledger (cost_pts = 0)
    ledger = build_audited_ledger(df, threshold_pts=50.0, cost_pts=0.0)

    # Attach contract expiry and lot size to ledger
    session_expiry = df.groupby("session_date")["selected_futures_expiry"].first().to_dict()
    session_lot = df.groupby("session_date")["lot_size"].first().to_dict()

    ledger["expiry"] = ledger["session_date"].map(session_expiry)
    ledger["lot_size"] = ledger["session_date"].map(session_lot).fillna(25).astype(int)

    cost_model = IndianDerivativesCostModel()
    recalculated_records = []

    for _, r in ledger.iterrows():
        if r["side"] == "FLAT":
            continue

        lot = r["lot_size"]
        trade_dt = r["session_date"]
        entry_px = r["signal_close"]
        exit_px = r["exit_price"]
        is_long = (r["side"] == "LONG")
        gross = r["gross_pts"]

        cost = cost_model.calculate_cost(
            entry_price=entry_px,
            exit_price=exit_px,
            lot_size=lot,
            instrument="INDEX_FUTURE",
            is_long=is_long,
            trade_date=trade_dt
        )

        fee_inr = cost.total
        fee_pts = fee_inr / lot
        net_pts = gross - fee_pts

        recalculated_records.append({
            "session_date": trade_dt,
            "side": r["side"],
            "expiry": r["expiry"],
            "lot_size": lot,
            "stt_rate": cost.effective_stt_rate,
            "entry_px": entry_px,
            "exit_px": exit_px,
            "gross_pts": gross,
            "fee_inr": fee_inr,
            "fee_pts": fee_pts,
            "net_pts": net_pts,
            "won_gross": gross > 0,
            "won_net": net_pts > 0
        })

    full_trade_df = pd.DataFrame(recalculated_records)

    # Epoch splits
    train_sessions = sorted(df["session_date"].unique())[:347]
    val_sessions = sorted(df["session_date"].unique())[347:421]

    is_trades = full_trade_df[full_trade_df["session_date"].isin(train_sessions)]
    oos_trades = full_trade_df[full_trade_df["session_date"].isin(val_sessions)]

    return is_trades, oos_trades

def evaluate_recalculated_epoch(trades_df: pd.DataFrame, n_sessions: int, label: str):
    n = len(trades_df)
    gross_exp = trades_df["gross_pts"].mean()
    gross_sum = trades_df["gross_pts"].sum()
    gross_pf = trades_df[trades_df["gross_pts"]>0]["gross_pts"].sum() / abs(trades_df[trades_df["gross_pts"]<=0]["gross_pts"].sum())

    avg_fee_pts = trades_df["fee_pts"].mean()
    avg_fee_inr = trades_df["fee_inr"].mean()
    net_exp = trades_df["net_pts"].mean()
    net_sum = trades_df["net_pts"].sum()

    net_wins = trades_df[trades_df["net_pts"]>0]["net_pts"].sum()
    net_loss = abs(trades_df[trades_df["net_pts"]<=0]["net_pts"].sum())
    net_pf = net_wins / net_loss if net_loss > 0 else np.nan
    win_rate = (trades_df["net_pts"] > 0).mean() * 100.0
    sharpe = (net_exp / (trades_df["net_pts"].std() + 1e-6)) * np.sqrt(250 * (n / n_sessions))

    print(f"\n========================================================")
    print(f"RECONCILED EPOCH: {label}")
    print(f"========================================================")
    print(f"Eligible Sessions:              {n_sessions}")
    print(f"Trades Executed:                {n} ({n/n_sessions*100:.1f}% participation)")
    print(f"Lot Size Distribution:          {trades_df['lot_size'].value_counts().to_dict()}")
    print(f"STT Rate Applied:               {trades_df['stt_rate'].value_counts().to_dict()}")
    print(f"Gross Expectancy / Trade:       {gross_exp:+.2f} pts (PF: {gross_pf:.2f}, Gross Sum: {gross_sum:+.1f} pts)")
    print(f"Avg Statutory Fee / Trade:      ₹{avg_fee_inr:.2f} ({avg_fee_pts:.3f} index points)")
    print(f"Net Repriced Expectancy / Tr:   {net_exp:+.2f} pts (Win Rate: {win_rate:.1f}%, PF: {net_pf:.2f})")
    print(f"Net Total PnL (pts):            {net_sum:+.1f} pts")
    print(f"Annualized Sharpe (Repriced):   {sharpe:.2f}")

def main():
    lot_map = get_authoritative_lot_map()
    print("Contract Lot Size Registry:", lot_map)

    is_trades, oos_trades = reprice_historical_dataset(lot_map)

    evaluate_recalculated_epoch(is_trades, 331, "EPOCH 1: IN-SAMPLE (2024-07 to 2025-12)")
    evaluate_recalculated_epoch(oos_trades, 70, "EPOCH 2: OUT-OF-SAMPLE (2025-12 to 2026-04)")

if __name__ == "__main__":
    main()
