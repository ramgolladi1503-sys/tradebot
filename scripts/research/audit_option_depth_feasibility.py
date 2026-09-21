#!/usr/bin/env python3
"""
Option Depth Feasibility Audit: DAY_TO_NIGHT_MOMENTUM_V2 Across 7 Full-Depth Sessions.
Evaluates:
1. Signal: Frozen NIFTY futures Rday at 15:25 (|Rday| > 50 pts).
2. Spot-ATM Strike Reference: NIFTY 50 Spot close at 15:25 (nearest 50-pt grid).
3. Expiry: Nearest expiry live through next-morning 09:16 exit (Tuesday weekly cycle).
4. Observable Live Market Depth: Real bids, asks, and spreads from Upstox stitched tick captures.
5. Statutory Charges: 0.15% STT on option premium sales + NSE circular FA73061 (0.035%) + SEBI + Stamp + Brokerage + GST.
"""

from __future__ import annotations
import datetime
import glob
import os
import pyarrow.dataset as ds
import pandas as pd
import numpy as np
from core.candidate_audits.cost_model import IndianDerivativesCostModel

CAPTURE_DIR = "/Volumes/TradeBotData/live market capture"
FUTURES_SEP_PATH = "data/research/upstox_futures_raw/nifty/2026-09-29/futures_1minute_1.parquet"

def run_feasibility_audit():
    print("=" * 80)
    print("OPTION DEPTH FEASIBILITY AUDIT: DAY_TO_NIGHT_MOMENTUM_V2")
    print("=" * 80)

    # 1. Load prospective futures to identify signals on capture dates
    fut_df = pd.read_parquet(FUTURES_SEP_PATH)
    fut_df["timestamp"] = pd.to_datetime(fut_df["timestamp"])
    fut_df["date_str"] = fut_df["timestamp"].dt.strftime("%Y-%m-%d")
    fut_df["time_str"] = fut_df["timestamp"].dt.strftime("%H:%M:%S")

    # Available capture dates
    capture_dates = ["2026-09-09", "2026-09-10", "2026-09-11", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
    print(f"Auditing across {len(capture_dates)} live market capture sessions...")

    cost_model = IndianDerivativesCostModel()
    lot_size = 65

    results = []

    for i in range(len(capture_dates) - 1):
        d_curr = capture_dates[i]
        d_next = capture_dates[i + 1]

        # Check futures signal on d_curr
        cfut = fut_df[fut_df["date_str"] == d_curr]
        b_0915 = cfut[cfut["time_str"] == "09:15:00"]
        b_1525 = cfut[cfut["time_str"] == "15:25:00"]

        if b_0915.empty or b_1525.empty:
            continue

        day_open = float(b_0915.iloc[0]["open"])
        signal_close = float(b_1525.iloc[0]["close"])
        r_day = signal_close - day_open

        if r_day > 50.0:
            side = "LONG"
            opt_type = "CE"
        elif r_day < -50.0:
            side = "SHORT"
            opt_type = "PE"
        else:
            side = "FLAT"
            opt_type = "NONE"

        print(f"\nSession {d_curr} -> {d_next}:")
        print(f"  Futures 09:15 Open = {day_open:.1f} | 15:25 Close = {signal_close:.1f} | Rday = {r_day:+.1f} pts | Side = {side}")

        if side == "FLAT":
            print("  Signal is FLAT (|Rday| <= 50 pts). No trade.")
            continue

        # 2. Get NIFTY Spot close at 15:25
        spot_pq = os.path.join(CAPTURE_DIR, d_curr, f"indices_1m_{d_curr.replace('-', '')}.parquet")
        if not os.path.exists(spot_pq):
            print(f"  Missing spot parquet for {d_curr}. Fail closed.")
            continue

        s_df = pd.read_parquet(spot_pq)
        nifty_spot = s_df[s_df["symbol"] == "NIFTY 50"]
        b_spot_1525 = nifty_spot[nifty_spot["timestamp"].astype(str).str.contains("15:25")]
        if b_spot_1525.empty:
            print("  Missing 15:25 spot bar. Fail closed.")
            continue

        spot_close_1525 = float(b_spot_1525.iloc[0]["close"])
        # Deterministic Spot-ATM strike formula
        atm_strike = int(round(spot_close_1525 / 50.0) * 50)
        print(f"  NIFTY Spot 15:25 = {spot_close_1525:.2f} -> Spot-ATM Strike = {atm_strike} {opt_type}")

        # 3. Locate Option Contract in Tick Dataset
        tick_pq_curr = os.path.join(CAPTURE_DIR, d_curr, f"upstox_full_ticks_{d_curr.replace('-', '')}_stitched.parquet")
        tick_pq_next = os.path.join(CAPTURE_DIR, d_next, f"upstox_full_ticks_{d_next.replace('-', '')}_stitched.parquet")

        if not os.path.exists(tick_pq_curr) or not os.path.exists(tick_pq_next):
            print("  Tick parquet missing for session boundary. Fail closed.")
            continue

        # Target symbol (nearest Tuesday weekly expiry live through next exit)
        # In Sep 2026 capture, weekly expiry is 22 SEP 26
        target_symbol = f"NIFTY {atm_strike} {opt_type} 22 SEP 26"
        print(f"  Target Option Contract: '{target_symbol}'")

        # Query Entry Ticks around 15:26:00
        dt_curr_1526 = datetime.datetime.strptime(f"{d_curr} 15:26:00", "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        )
        ts_curr_1526 = dt_curr_1526.timestamp()

        curr_ds = ds.dataset(tick_pq_curr, format="parquet")
        scanner_entry = curr_ds.scanner(
            filter=(ds.field("symbol") == target_symbol) & (ds.field("ts") >= ts_curr_1526) & (ds.field("ts") <= ts_curr_1526 + 15)
        )
        entry_ticks = scanner_entry.to_table().to_pandas()

        if entry_ticks.empty:
            print(f"  NO ENTRY TICKS FOUND for '{target_symbol}' at 15:26. Fail closed.")
            continue

        # First causally eligible quote after 15:26:00.000
        first_entry = entry_ticks.iloc[0]
        entry_bid = float(first_entry["bid"])
        entry_ask = float(first_entry["ask"])
        entry_spread = entry_ask - entry_bid
        entry_fill = entry_ask  # Long option buys at Ask

        # Query Exit Ticks around next day 09:16:00
        dt_next_0916 = datetime.datetime.strptime(f"{d_next} 09:16:00", "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        )
        ts_next_0916 = dt_next_0916.timestamp()

        next_ds = ds.dataset(tick_pq_next, format="parquet")
        scanner_exit = next_ds.scanner(
            filter=(ds.field("symbol") == target_symbol) & (ds.field("ts") >= ts_next_0916) & (ds.field("ts") <= ts_next_0916 + 15)
        )
        exit_ticks = scanner_exit.to_table().to_pandas()

        if exit_ticks.empty:
            print(f"  NO EXIT TICKS FOUND for '{target_symbol}' at 09:16 next day. Fail closed.")
            continue

        first_exit = exit_ticks.iloc[0]
        exit_bid = float(first_exit["bid"])
        exit_ask = float(first_exit["ask"])
        exit_spread = exit_ask - exit_bid
        exit_fill = exit_bid  # Long option sells at Bid

        # PnL & Fee Calculation
        gross_pts = exit_fill - entry_fill
        gross_pnl_inr = gross_pts * lot_size
        capital_outlay_inr = entry_fill * lot_size

        # True 2026 Statutory Schedule
        cost_breakdown = cost_model.calculate_cost(
            entry_price=entry_fill,
            exit_price=exit_fill,
            lot_size=lot_size,
            instrument="INDEX_OPTION_BUY",
            is_long=True,
            trade_date=d_curr,
            legs_count=2
        )
        total_fee_inr = cost_breakdown.total
        net_pnl_inr = gross_pnl_inr - total_fee_inr
        ret_on_capital = (net_pnl_inr / capital_outlay_inr) * 100.0

        print(f"  ENTRY @ {d_curr} 15:26:00: Bid = {entry_bid:.2f} | Ask = {entry_ask:.2f} | Fill = {entry_fill:.2f} | Spread = {entry_spread:.2f} pts")
        print(f"  EXIT  @ {d_next} 09:16:00: Bid = {exit_bid:.2f} | Ask = {exit_ask:.2f} | Fill = {exit_fill:.2f} | Spread = {exit_spread:.2f} pts")
        print(f"  GROSS OPTION PnL: {gross_pts:+.2f} premium pts (₹{gross_pnl_inr:+.2f})")
        print(f"  STATUTORY FEES:   ₹{total_fee_inr:.2f} (STT ₹{cost_breakdown.stt:.2f} @ 0.15% on sell premium)")
        print(f"  NET REALIZED PnL: ₹{net_pnl_inr:+.2f} | Return on Capital = {ret_on_capital:+.2f}%")

        results.append({
            "session": d_curr,
            "next_session": d_next,
            "side": side,
            "contract": target_symbol,
            "entry_fill": entry_fill,
            "exit_fill": exit_fill,
            "entry_spread": entry_spread,
            "exit_spread": exit_spread,
            "gross_pts": gross_pts,
            "gross_pnl_inr": gross_pnl_inr,
            "statutory_fee_inr": total_fee_inr,
            "net_pnl_inr": net_pnl_inr,
            "capital_outlay_inr": capital_outlay_inr,
            "return_on_capital_pct": ret_on_capital
        })

    rdf = pd.DataFrame(results)
    if not rdf.empty:
        print("\n" + "=" * 80)
        print("SUMMARY OF OBSERVED OPTION TRANSLATION TRADES")
        print("=" * 80)
        print(rdf[["session", "side", "contract", "entry_spread", "exit_spread", "gross_pts", "statutory_fee_inr", "net_pnl_inr", "return_on_capital_pct"]].to_string(index=False))

if __name__ == "__main__":
    run_feasibility_audit()
