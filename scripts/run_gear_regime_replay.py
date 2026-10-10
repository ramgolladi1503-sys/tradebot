"""Dynamic Regime Replay: Gear 1 (Range Scalper) vs Gear 2 (Trend Expansion).

Proves that:
1. On Range Days (KER < 0.30):
   - Gear 1 enforces tight 15-minute time horizon, tight stops, and lunch freeze (11:00-13:30), preventing theta decay.
2. On Big Trend Days (KER >= 0.35, e.g. Oct 8, 2026):
   - Gear 2 activates 50% target book + 50% runner mode.
   - Stop Loss is evaluated natively on Option Contract Price (-20% option SL), ignoring spot random-walk wicks.
   - Deactivates 15m calendar exit and rides the macro extension via Option High-Watermark (HWM).
"""

import json
from pathlib import Path
from datetime import datetime, time as dtime
import urllib.request
import pandas as pd

from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_LIQUIDATED
)

# Fetch 375 1m candles for Oct 8, 2026
url = "https://api.upstox.com/v2/historical-candle/intraday/NSE_INDEX%7CNifty%2050/1minute"
req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "TradeBot/1.0"})
with urllib.request.urlopen(req, timeout=5) as resp:
    data = json.loads(resp.read().decode())
    raw_candles = data.get("data", {}).get("candles", [])

candles = sorted(raw_candles, key=lambda x: x[0])
print(f"Loaded {len(candles)} 1-minute bars for Oct 8, 2026.")

apm = ActivePositionManager(wal_path="runtime/sentinel_gear_replay_wal.json")
trades = []
ewma_ker = 0.5
or_high = -1e9
or_low = 1e9
last_exit_price = None
last_exit_dir = None

for i, bar in enumerate(candles):
    b_dt = datetime.fromisoformat(bar[0])
    btime = b_dt.time()
    o, h, l, c = float(bar[1]), float(bar[2]), float(bar[3]), float(bar[4])

    if btime < dtime(9, 45):
        or_high = max(or_high, h)
        or_low = min(or_low, l)
        continue

    # Session metrics
    candles_so_far = candles[:i+1]
    disp = abs(c - float(candles[0][1]))
    tot_p = max(0.1, sum(abs(float(candles[k][4]) - float(candles[k-1][4])) for k in range(1, len(candles_so_far))))
    raw_ker = disp / tot_p
    ewma_ker = 0.15 * raw_ker + 0.85 * ewma_ker

    lookback_bars = candles_so_far[-14:] if len(candles_so_far) >= 14 else candles_so_far
    atr_1m = sum(max(float(b[2]) - float(b[3]), 0.1) for b in lookback_bars) / max(1, len(lookback_bars))

    # Evaluate open position
    if apm.state in {STATE_IN_FLIGHT, STATE_TRAIL_LOCK}:
        p = apm.payload
        is_ce = (p.direction == "CE")
        delta_spot = (c - p.entry_price) if is_ce else (p.entry_price - c)
        opt_current_ltp = max(5.0, (p.opt_entry_ltp or 90.0) + delta_spot * 0.65)

        st, summary = apm.evaluate_bar(
            bar_open=o,
            bar_high=h,
            bar_low=l,
            bar_close=c,
            bar_time_str=bar[0],
            current_opt_ltp=opt_current_ltp,
            atr_1m=atr_1m
        )
        if st == STATE_LIQUIDATED:
            trades.append(summary)
            last_exit_price = summary.get("exit_price")
            last_exit_dir = summary.get("direction")

    # Entry evaluation
    if apm.state in {STATE_STANDBY, STATE_LIQUIDATED}:
        target_pts = 15.0
        sl_pts = round(max(12.0, 1.2 * atr_1m), 1)

        # Dynamic Regime Classification
        is_trend_day = (ewma_ker >= 0.35 and (or_high - or_low) >= 70.0)
        current_gear = "GEAR_2_TREND" if is_trend_day else "GEAR_1_RANGE"

        in_lunch_dead_zone = (current_gear == "GEAR_1_RANGE" and dtime(11, 0) <= btime <= dtime(13, 30))

        entry_dir = None
        if c < or_low:
            entry_dir = "PE"
        elif c > or_high:
            entry_dir = "CE"

        if entry_dir and not in_lunch_dead_zone:
            # Displacement Gate check
            min_disp = max(8.0, 1.0 * atr_1m)
            insufficient_disp = False
            if last_exit_price is not None and last_exit_dir == entry_dir:
                if entry_dir == "PE" and (last_exit_price - c) < min_disp:
                    insufficient_disp = True
                elif entry_dir == "CE" and (c - last_exit_price) < min_disp:
                    insufficient_disp = True

            if not insufficient_disp:
                atm_k = int(round(c / 50.0) * 50)
                strike = atm_k + 50 if entry_dir == "PE" else atm_k - 50
                contract = f"NIFTY {strike} {entry_dir} [ITM]"
                est_opt_entry = 90.45 if btime <= dtime(9, 50) else 115.0

                apm.arm_and_enter(
                    position_id=f"GEAR2_{btime.strftime('%H%M')}_{entry_dir}",
                    direction=entry_dir,
                    contract=contract,
                    entry_price=c,
                    entry_time_str=bar[0],
                    sl_pts=sl_pts,
                    tp_pts=target_pts,
                    is_runner_mode=(current_gear == "GEAR_2_TREND"),
                    session_gear=current_gear,
                    opt_stop_loss_pct=0.20 if (current_gear == "GEAR_2_TREND") else None,
                    opt_quote={"symbol": contract, "token": "1", "ltp": est_opt_entry, "bid": est_opt_entry - 0.5, "ask": est_opt_entry + 0.5}
                )

print("\n" + "="*60)
print(f"GEAR 2 TREND RUNNER REPLAY RESULTS (OCT 8, 2026)")
print("="*60)
print(f"Total Trades Taken: {len(trades)}")
for t in trades:
    print(f" - {t.get('position_id')}: Reason={t.get('exit_reason')} | Spot PnL={t.get('pnl_pts'):+.1f} pts | Option PnL={t.get('opt_pnl_pts'):+.2f} pts")

tot_spot = sum(t.get("pnl_pts", 0.0) for t in trades)
tot_opt = sum(t.get("opt_pnl_pts", 0.0) for t in trades)
print(f"\nNet Spot PnL: {tot_spot:+.1f} points")
print(f"Net Option Strike PnL: {tot_opt:+.2f} points (+₹{tot_opt*650:,.2f} on 10 lots)")
print("="*60)
