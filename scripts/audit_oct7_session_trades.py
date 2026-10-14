import json
from datetime import datetime

with open('runtime/today_full_candles.json') as f:
    candles = json.load(f)

# Build candle lookup by timestamp string
candle_map = {c[0]: c for c in candles}
candle_times = [c[0] for c in candles]

# 1. Establish Opening Range (09:15 to 09:45)
or_high = -1e9
or_low = 1e9
for c in candles:
    t_str = c[0].split('T')[1].split('+')[0]
    if t_str <= '09:45:00':
        or_high = max(or_high, float(c[2]))
        or_low = min(or_low, float(c[3]))

print(f"=== OR AUDIT: High={or_high:.2f}, Low={or_low:.2f}, Width={or_high-or_low:.2f} pts ===")

# 2. Simulate Causal Execution Across the Whole Session (09:45 to 15:15)
# Invariants:
# - Signal on Bar T Close.
# - Fill strictly on Bar T+1 Open.
# - Evaluation against Target (+18 option pts ~ +36 index pts assuming delta ~0.50 ATM)
# - Stop Loss (-12 option pts ~ -24 index pts)
# - Trailing lock (+8 option pts ~ +16 index pts lock to breakeven)
# - Max hold: 15 bars.

trades = []
active_trade = None

for i, c in enumerate(candles):
    t_str = c[0].split('T')[1].split('+')[0]
    if t_str < '09:46:00' or t_str > '15:15:00':
        continue

    t_curr, o, h, l, close = c[0], float(c[1]), float(c[2]), float(c[3]), float(c[4])

    # Manage active trade
    if active_trade:
        # Check T+1 onwards
        direction = active_trade['direction']
        entry_spot = active_trade['entry_spot']
        hold_bars = i - active_trade['entry_idx']
        
        # In index points (delta ~ 0.50):
        # Target: +36 pts index (+18 pts option)
        # SL: -24 pts index (-12 pts option)
        # Trailing Ratchet: +16 pts index (+8 pts option) ratchets SL to Entry
        
        if direction == 'LONG_CE':
            max_fav = h - entry_spot
            max_adv = entry_spot - l
            
            # Check trailing ratchet
            if max_fav >= 16.0:
                active_trade['trailed_to_be'] = True

            # Pessimistic: if SL hit
            current_sl = entry_spot if active_trade['trailed_to_be'] else (entry_spot - 24.0)
            
            if l <= current_sl:
                active_trade['exit_time'] = t_str
                active_trade['exit_price'] = current_sl
                active_trade['exit_reason'] = 'TRAILED_STOP' if active_trade['trailed_to_be'] else 'STOP_LOSS'
                active_trade['pnl_index'] = current_sl - entry_spot
                active_trade['pnl_opt'] = (current_sl - entry_spot) * 0.50
                active_trade['max_fav'] = max(active_trade['max_fav'], max_fav)
                active_trade['max_adv'] = max(active_trade['max_adv'], max_adv)
                trades.append(active_trade)
                active_trade = None
                continue
            elif h >= entry_spot + 36.0:
                active_trade['exit_time'] = t_str
                active_trade['exit_price'] = entry_spot + 36.0
                active_trade['exit_reason'] = 'TARGET_HIT'
                active_trade['pnl_index'] = 36.0
                active_trade['pnl_opt'] = 18.0
                active_trade['max_fav'] = max(active_trade['max_fav'], max_fav)
                active_trade['max_adv'] = max(active_trade['max_adv'], max_adv)
                trades.append(active_trade)
                active_trade = None
                continue
            elif hold_bars >= 15:
                active_trade['exit_time'] = t_str
                active_trade['exit_price'] = close
                active_trade['exit_reason'] = 'TIME_EXIT'
                active_trade['pnl_index'] = close - entry_spot
                active_trade['pnl_opt'] = (close - entry_spot) * 0.50
                active_trade['max_fav'] = max(active_trade['max_fav'], max_fav)
                active_trade['max_adv'] = max(active_trade['max_adv'], max_adv)
                trades.append(active_trade)
                active_trade = None
                continue
            else:
                active_trade['max_fav'] = max(active_trade['max_fav'], max_fav)
                active_trade['max_adv'] = max(active_trade['max_adv'], max_adv)

        elif direction == 'LONG_PE':
            max_fav = entry_spot - l
            max_adv = h - entry_spot

            if max_fav >= 16.0:
                active_trade['trailed_to_be'] = True

            current_sl = entry_spot if active_trade['trailed_to_be'] else (entry_spot + 24.0)

            if h >= current_sl:
                active_trade['exit_time'] = t_str
                active_trade['exit_price'] = current_sl
                active_trade['exit_reason'] = 'TRAILED_STOP' if active_trade['trailed_to_be'] else 'STOP_LOSS'
                active_trade['pnl_index'] = entry_spot - current_sl
                active_trade['pnl_opt'] = (entry_spot - current_sl) * 0.50
                active_trade['max_fav'] = max(active_trade['max_fav'], max_fav)
                active_trade['max_adv'] = max(active_trade['max_adv'], max_adv)
                trades.append(active_trade)
                active_trade = None
                continue
            elif l <= entry_spot - 36.0:
                active_trade['exit_time'] = t_str
                active_trade['exit_price'] = entry_spot - 36.0
                active_trade['exit_reason'] = 'TARGET_HIT'
                active_trade['pnl_index'] = 36.0
                active_trade['pnl_opt'] = 18.0
                active_trade['max_fav'] = max(active_trade['max_fav'], max_fav)
                active_trade['max_adv'] = max(active_trade['max_adv'], max_adv)
                trades.append(active_trade)
                active_trade = None
                continue
            elif hold_bars >= 15:
                active_trade['exit_time'] = t_str
                active_trade['exit_price'] = close
                active_trade['exit_reason'] = 'TIME_EXIT'
                active_trade['pnl_index'] = entry_spot - close
                active_trade['pnl_opt'] = (entry_spot - close) * 0.50
                active_trade['max_fav'] = max(active_trade['max_fav'], max_fav)
                active_trade['max_adv'] = max(active_trade['max_adv'], max_adv)
                trades.append(active_trade)
                active_trade = None
                continue
            else:
                active_trade['max_fav'] = max(active_trade['max_fav'], max_fav)
                active_trade['max_adv'] = max(active_trade['max_adv'], max_adv)

    # If flat, look for entry signal on bar close T, fill on T+1 Open
    if not active_trade and i + 1 < len(candles):
        next_candle = candles[i+1]
        next_open = float(next_candle[1])
        next_t_str = next_candle[0].split('T')[1].split('+')[0]
        
        total_range = max(0.1, h - l)
        upper_wick = h - max(o, close)
        lower_wick = min(o, close) - l

        sig = None
        contract = None
        if close > or_high:
            sig = 'OR_HIGH_BREAKOUT'
            direction = 'LONG_CE'
            strike = int(round(close / 50.0) * 50)
            contract = f"NIFTY {strike} CE"
        elif close < or_low:
            sig = 'OR_LOW_BREAKDOWN'
            direction = 'LONG_PE'
            strike = int(round(close / 50.0) * 50)
            contract = f"NIFTY {strike} PE"
        elif lower_wick >= 6.0 and (lower_wick / total_range) >= 0.40:
            sig = 'BULLISH_REJECTION_WICK'
            direction = 'LONG_CE'
            strike = int(round(close / 50.0) * 50)
            contract = f"NIFTY {strike} CE"
        elif upper_wick >= 6.0 and (upper_wick / total_range) >= 0.40:
            sig = 'BEARISH_REJECTION_WICK'
            direction = 'LONG_PE'
            strike = int(round(close / 50.0) * 50)
            contract = f"NIFTY {strike} PE"

        if sig:
            active_trade = {
                'signal_time': t_str,
                'signal_spot': close,
                'entry_time': next_t_str,
                'entry_spot': next_open,
                'entry_idx': i + 1,
                'direction': direction,
                'setup': sig,
                'contract': contract,
                'trailed_to_be': False,
                'max_fav': 0.0,
                'max_adv': 0.0,
            }

print(f"\nTotal Simulated Realized Trades: {len(trades)}")
cum_opt_pnl = 0.0
for idx, t in enumerate(trades, 1):
    cum_opt_pnl += t['pnl_opt']
    print(f"Trade #{idx} | {t['signal_time']} -> {t['entry_time']} | {t['contract']} ({t['setup']}) | Fill: {t['entry_spot']:.2f}")
    print(f"   Exit: {t['exit_time']} @ {t['exit_price']:.2f} ({t['exit_reason']}) | PnL Opt: {t['pnl_opt']:+.1f} pts (Idx: {t['pnl_index']:+.1f})")
    print(f"   Max Fav Excursion: +{t['max_fav']:.1f} pts index (~+{t['max_fav']*0.5:.1f} opt) | Max Adv: -{t['max_adv']:.1f} pts index (~-{t['max_adv']*0.5:.1f} opt)")
    print(f"   Cumulative Net: {cum_opt_pnl:+.1f} pts")
    print("-" * 75)

