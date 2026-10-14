"""Causal 30-Day Walk-Forward Verification (WFV) Audit Engine for SENSEX.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False

Replays SENSEX minute-by-minute across 30 consecutive trading sessions (Aug 31 - Oct 13, 2026).
Evaluates:
1. Dynamic 09:15-09:45 Opening Range Calibration per session.
2. Brownian Diffusion Energy Gate.
3. Volatility-scaled stops and displacement gates.
4. Active Position Manager (APM) with conservative intrabar resolution (SL wins if touched in same bar).
5. Dynamic 0-DTE theta hold horizon.
6. Evaluates rolling 10-day window stability to confirm no degradation over time.
"""

import json
import math
from pathlib import Path
from datetime import datetime, time as dtime
import numpy as np
import pandas as pd
from core.asset_profile_registry import get_asset_profile
from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_LIQUIDATED,
)


def run_30day_wfa():
    profile = get_asset_profile("SENSEX")
    master_pq = "/Volumes/TradeBot/historical/sensex/sensex_1minute_2022_2026.parquet"
    if not Path(master_pq).exists():
        print(f"Error: {master_pq} not found.")
        return

    df = pd.read_parquet(master_pq)
    df["date"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d")
    all_dates = sorted(df["date"].unique())
    wfa_dates = all_dates[-30:]

    print(f"🚀 [SENSEX 30-DAY WFV ENGINE] Starting audit across {len(wfa_dates)} sessions: {wfa_dates[0]} to {wfa_dates[-1]}")

    results = []
    daily_stats = {}

    for dt_str in wfa_dates:
        day_bars = df[df["date"] == dt_str].sort_values("timestamp").reset_index(drop=True)
        if len(day_bars) < 60:
            continue

        wal_dummy = f"/tmp/sentinel_wfa_wal_{dt_str}.json"
        apm = ActivePositionManager(wal_path=wal_dummy, profile=profile)

        or_high = -1e9
        or_low = 1e9
        last_exit_price = None
        last_exit_direction = None

        trades_today = []

        for idx, row in day_bars.iterrows():
            ts_str = str(row["timestamp"])
            bdt = pd.to_datetime(ts_str)
            btime = bdt.time()
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])

            # Realized ATR_1m across up to 14 preceding bars
            start_i = max(0, idx - 14)
            lookback = day_bars.iloc[start_i:idx+1]
            atr_1m = float((lookback["high"] - lookback["low"]).mean()) if len(lookback) > 0 else 20.0

            # 1. 09:15 - 09:45 Opening Shock Range
            if btime < dtime(9, 45):
                or_high = max(or_high, h)
                or_low = min(or_low, l)
                continue

            # 2. Evaluate In-Flight Position
            if apm.state in {STATE_IN_FLIGHT, STATE_TRAIL_LOCK}:
                state, summary = apm.evaluate_bar(
                    bar_open=o, bar_high=h, bar_low=l, bar_close=c,
                    bar_time_str=ts_str, atr_1m=atr_1m
                )
                if state == STATE_LIQUIDATED and summary:
                    last_exit_price = summary.get("exit_price")
                    last_exit_direction = summary.get("direction")
                    trades_today.append(summary)
                    results.append(summary)
                continue

            # 3. Setup Detection
            target_pts = profile.target_scalp_pts
            sl_pts = round(max(profile.initial_sl_pts, 1.2 * atr_1m), 1)

            entry_dir = None
            if c > or_high:
                entry_dir = "CE"
            elif c < or_low:
                entry_dir = "PE"

            if not entry_dir:
                continue

            # 4. Brownian Energy Gate
            can_enter, e_diff, req = apm.check_session_energy_gate(
                current_time=btime,
                target_pts=target_pts,
                atr_1m=atr_1m,
                trade_horizon_mins=15
            )
            if not can_enter:
                continue

            # 5. Displacement Gate: Outside single-bar noise envelope
            base_disp = 30.0
            if last_exit_price is not None and last_exit_direction == entry_dir:
                min_disp = max(base_disp, 1.2 * atr_1m)
                if entry_dir == "PE" and (last_exit_price - c) < min_disp:
                    continue
                elif entry_dir == "CE" and (c - last_exit_price) < min_disp:
                    continue

            # 6. Execute Paper Entry
            pos_id = f"TRADE_{dt_str}_{btime.strftime('%H%M')}_{entry_dir}"
            contract = f"SENSEX {entry_dir} [ITM]"
            apm.arm_and_enter(
                position_id=pos_id,
                direction=entry_dir,
                contract=contract,
                entry_price=c,
                entry_time_str=ts_str,
                sl_pts=sl_pts,
                tp_pts=target_pts,
                session_gear="GEAR_1_RANGE"
            )

        daily_pts = sum(float(t.get("pnl_pts", 0.0)) for t in trades_today)
        daily_stats[dt_str] = {
            "trades": len(trades_today),
            "pnl_pts": round(daily_pts, 1),
            "wins": sum(1 for t in trades_today if float(t.get("pnl_pts", 0.0)) > 0),
        }
        Path(wal_dummy).unlink(missing_ok=True)

    # Compile Overall WFA Performance
    df_res = pd.DataFrame(results)
    total_trades = len(df_res)
    if total_trades == 0:
        print("Zero trades triggered in WFA window.")
        return

    wins = df_res[df_res["pnl_pts"] > 0]
    losses = df_res[df_res["pnl_pts"] <= 0]
    win_rate = (len(wins) / total_trades) * 100.0
    net_pts = df_res["pnl_pts"].sum()
    gross_win = wins["pnl_pts"].sum()
    gross_loss = abs(losses["pnl_pts"].sum())
    profit_factor = round(gross_win / max(1.0, gross_loss), 2)
    avg_win = round(wins["pnl_pts"].mean(), 1) if len(wins) > 0 else 0.0
    avg_loss = round(losses["pnl_pts"].mean(), 1) if len(losses) > 0 else 0.0

    print("\n=======================================================")
    print("📊 SENSEX 30-DAY CAUSAL WALK-FORWARD VERIFICATION REPORT")
    print("=======================================================")
    print(f"Total Trading Sessions: {len(wfa_dates)}")
    print(f"Total Executed Trades:  {total_trades}")
    print(f"Win Rate:               {win_rate:.1f}% ({len(wins)} W / {len(losses)} L)")
    print(f"Net Cumulative Points:  {net_pts:+.1f} pts")
    print(f"Profit Factor:          {profit_factor}")
    print(f"Average Win:            +{avg_win} pts")
    print(f"Average Loss:           {avg_loss} pts")

    # Rolling 10-day stability slices
    s1 = wfa_dates[:10]
    s2 = wfa_dates[10:20]
    s3 = wfa_dates[20:]
    for name, s_dates in [("Slice 1 (Aug 31 - Sep 11)", s1), ("Slice 2 (Sep 15 - Sep 28)", s2), ("Slice 3 (Sep 29 - Oct 13)", s3)]:
        s_pnl = sum(daily_stats.get(d, {}).get("pnl_pts", 0.0) for d in s_dates)
        s_tr = sum(daily_stats.get(d, {}).get("trades", 0) for d in s_dates)
        s_w = sum(daily_stats.get(d, {}).get("wins", 0) for d in s_dates)
        s_wr = (s_w / max(1, s_tr)) * 100.0
        print(f"   🔹 {name}: {s_tr} trades | {s_wr:.1f}% WR | {s_pnl:+.1f} net pts")

    report_payload = {
        "audit_name": "SENSEX_30_DAY_WALK_FORWARD_VERIFICATION",
        "date_range": f"{wfa_dates[0]} to {wfa_dates[-1]}",
        "total_sessions": len(wfa_dates),
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "net_cumulative_pts": round(float(net_pts), 1),
        "profit_factor": profit_factor,
        "avg_win_pts": avg_win,
        "avg_loss_pts": avg_loss,
        "daily_stats": daily_stats
    }
    out_json = Path("/private/tmp/tradebot-sensex-engine/artifacts/sensex_30day_wfv_report.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w") as f:
        json.dump(report_payload, f, indent=2)
    print(f"\n✅ Audit Report Saved: {out_json}")


if __name__ == "__main__":
    run_30day_wfa()
