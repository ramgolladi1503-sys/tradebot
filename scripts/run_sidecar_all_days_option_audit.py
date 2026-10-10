"""Gated Option Strike Scalp Audit across All Live Capture Sessions.

Enforces the 3 Rules from our chat:
1. Max 4 high-conviction trades per day (No over-trading churn).
2. Consecutive Loss Circuit Breaker: If 2 consecutive scalps hit stop loss, STAND ASIDE in 100% cash.
3. Midday Profit Lock Cutoff: Stand aside after 12:45 PM.
"""

import glob
import json
from pathlib import Path
import pandas as pd
import numpy as np

CAPTURE_BASE_DIR = Path("/Volumes/TradeBotData/live market capture")
MATRIX_PATH = Path("artifacts/calibrated_regime_matrix.json")

with open(MATRIX_PATH) as f:
    calib = json.load(f)

target_pts = calib['RANGE']['optimal_target_pts'] # 21.0 pts spot -> 10.5 pts option
sl_pts = calib['RANGE']['optimal_stop_loss_pts']     # 15.0 pts spot -> 7.5 pts option

def evaluate_day(date_dir: Path):
    date_str = date_dir.name
    ind_p = date_dir / f"indices_1m_{date_str.replace('-', '')}.parquet"
    if not ind_p.exists():
        return None

    df_raw = pd.read_parquet(ind_p)
    df = df_raw[df_raw['symbol'] == 'NIFTY 50'].copy()
    if df.empty or len(df) < 30:
        return None

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    # Intraday VWAP & Bands
    cum_pv = 0.0
    cum_vol = 0.0
    vwaps = []
    for _, r in df.iterrows():
        v = r['volume'] if ('volume' in r and r['volume'] > 0) else 1.0
        typ = (r['high'] + r['low'] + r['close']) / 3.0
        cum_pv += typ * v
        cum_vol += v
        vwaps.append(cum_pv / cum_vol)
    df['vwap'] = vwaps

    df['std20'] = df['close'].rolling(20, min_periods=1).std()
    df['bb_upper'] = df['vwap'] + 1.5 * df['std20']
    df['bb_lower'] = df['vwap'] - 1.5 * df['std20']

    trades = []
    daily_opt_pnl = 0.0
    active_pos = None
    consecutive_losses = 0

    for i in range(15, len(df)):
        curr_bar = df.iloc[i]
        ts_str = curr_bar['timestamp'].strftime('%H:%M')

        # Position Management
        if active_pos:
            pos = active_pos
            exit_spot = None
            reason = None

            if pos['action'] == 'BUY_CE':
                if curr_bar['high'] >= pos['entry_spot'] + 6.0 and not pos['trailed']:
                    pos['sl_spot'] = pos['entry_spot']
                    pos['trailed'] = True

                if curr_bar['low'] <= pos['sl_spot']:
                    exit_spot = pos['sl_spot']
                    reason = 'TRAILING_SHIELD' if pos['trailed'] else 'STOP_LOSS'
                elif curr_bar['high'] >= pos['target_spot']:
                    exit_spot = pos['target_spot']
                    reason = 'LOCKED_PROFIT'
                elif (i - pos['entry_idx']) >= 12 or i >= len(df) - 2:
                    exit_spot = curr_bar['close']
                    reason = 'TIME_TIMEOUT'

            elif pos['action'] == 'BUY_PE':
                if curr_bar['low'] <= pos['entry_spot'] - 6.0 and not pos['trailed']:
                    pos['sl_spot'] = pos['entry_spot']
                    pos['trailed'] = True

                if curr_bar['high'] >= pos['sl_spot']:
                    exit_spot = pos['sl_spot']
                    reason = 'TRAILING_SHIELD' if pos['trailed'] else 'STOP_LOSS'
                elif curr_bar['low'] <= pos['target_spot']:
                    exit_spot = pos['target_spot']
                    reason = 'LOCKED_PROFIT'
                elif (i - pos['entry_idx']) >= 12 or i >= len(df) - 2:
                    exit_spot = curr_bar['close']
                    reason = 'TIME_TIMEOUT'

            if exit_spot is not None:
                spot_delta = (exit_spot - pos['entry_spot']) if pos['action'] == 'BUY_CE' else (pos['entry_spot'] - exit_spot)
                opt_pnl = round(spot_delta * 0.50 - 1.0, 1) # Delta 0.50 with 1 pt slippage
                daily_opt_pnl += opt_pnl
                
                if opt_pnl < 0:
                    consecutive_losses += 1
                else:
                    consecutive_losses = 0

                trades.append({
                    'strike': pos['strike'],
                    'entry_time': pos['entry_time'],
                    'exit_time': ts_str,
                    'reason': reason,
                    'opt_pnl': opt_pnl
                })
                active_pos = None

                # Circuit breaker: 2 consecutive losses OR 12:45 cutoff
                if consecutive_losses >= 2 or ts_str >= '12:45' or len(trades) >= 4:
                    break
                continue

        close_t = curr_bar['close']
        open_t = curr_bar['open']
        low_t = curr_bar['low']
        high_t = curr_bar['high']

        lower_wick = min(open_t, close_t) - low_t
        upper_wick = high_t - max(open_t, close_t)

        is_dip = (low_t <= curr_bar['bb_lower'] or low_t <= curr_bar['vwap']) and lower_wick >= 4.0 and close_t > open_t
        is_rip = (high_t >= curr_bar['bb_upper'] or high_t >= curr_bar['vwap']) and upper_wick >= 4.0 and close_t < open_t

        strike_num = int(round(close_t / 50.0) * 50)

        if is_dip and not active_pos:
            active_pos = {
                'action': 'BUY_CE',
                'strike': f'NIFTY {strike_num} CE',
                'entry_spot': close_t,
                'target_spot': close_t + target_pts,
                'sl_spot': close_t - sl_pts,
                'entry_idx': i,
                'entry_time': ts_str,
                'trailed': False
            }
        elif is_rip and not active_pos:
            active_pos = {
                'action': 'BUY_PE',
                'strike': f'NIFTY {strike_num} PE',
                'entry_spot': close_t,
                'target_spot': close_t - target_pts,
                'sl_spot': close_t + sl_pts,
                'entry_idx': i,
                'entry_time': ts_str,
                'trailed': False
            }

    return {
        'date': date_str,
        'trades_count': len(trades),
        'trades': trades,
        'net_opt_pnl': round(daily_opt_pnl, 1)
    }

dirs = sorted([d for d in CAPTURE_BASE_DIR.glob('2026-*') if d.is_dir()])
results = []
for d in dirs:
    res = evaluate_day(d)
    if res:
        results.append(res)

matrix_data = []
for r in results:
    trade_summary = '; '.join([f"{t['strike']} ({t['entry_time']}-{t['exit_time']}: {t['reason']} {t['opt_pnl']:+0.1f})" for t in r['trades']])
    matrix_data.append({
        'Date': r['date'],
        'Strikes Traded': r['trades_count'],
        'Net Option PnL (pts)': r['net_opt_pnl'],
        'Option Trades Log': trade_summary if trade_summary else 'Disciplined Stand-Aside'
    })

matrix_df = pd.DataFrame(matrix_data)
out_csv = 'runtime/gated_all_days_option_matrix.csv'
matrix_df.to_csv(out_csv, index=False)

print('\n=== GATED OPTION STRIKE MATRIX ACROSS ALL LIVE CAPTURES ===')
print(matrix_df[['Date', 'Strikes Traded', 'Net Option PnL (pts)']].to_string(index=False))

total_opt_pnl = sum(r['net_opt_pnl'] for r in results)
total_trades = sum(r['trades_count'] for r in results)
wins = sum(1 for r in results for t in r['trades'] if t['opt_pnl'] > 0)
losses = sum(1 for r in results for t in r['trades'] if t['opt_pnl'] < 0)

print(f'\nTotal Sessions: {len(results)} | Total Option Trades: {total_trades}')
print(f'Wins: {wins} | Losses: {losses}')
print(f'Cumulative Net Option Premium PnL (after slippage): {total_opt_pnl:+0.1f} pts')
