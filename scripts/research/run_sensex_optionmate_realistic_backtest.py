import glob
import os
import datetime
import math
import pandas as pd
import numpy as np

def calculate_dynamic_sustainable_anchor(spot: float, vix: float, dte: float) -> float:
    """
    Dynamic Black-Scholes ATM half-straddle sustainable price anchor calculation:
    formula from core/sentinel_live_stream_advisor.py:
    0.40 * spot * (max(vix, 9.0) / 100.0) * sqrt(max(dte, 0.20) / 365.0)
    """
    eff_dte = max(0.20, float(dte))
    eff_vix = max(9.0, float(vix))
    return round(0.40 * spot * (eff_vix / 100.0) * math.sqrt(eff_dte / 365.0), 1)

def run_realistic_backtest():
    files = sorted(glob.glob('runtime/kite_candidate_replay/*/underlying/*SENSEX*.parquet'))
    sessions = []
    for f in files:
        d_str = f.split('/')[2]
        try:
            dt = datetime.datetime.strptime(d_str, '%Y-%m-%d').date()
            if dt >= datetime.date(2026, 1, 1):
                sessions.append((dt, f))
        except:
            pass

    sessions = sorted(sessions, key=lambda x: x[0])
    
    # Pre-calculate daily ATR_14
    daily_ranges = []
    daily_stats = {}
    for dt, f in sessions:
        df = pd.read_parquet(f)
        if df.empty:
            continue
        d_high = df['high'].max()
        d_low = df['low'].min()
        d_close = df['close'].iloc[-1]
        tr = d_high - d_low
        daily_stats[dt] = {'high': d_high, 'low': d_low, 'close': d_close, 'tr': tr}
        daily_ranges.append((dt, tr))

    results = []
    
    for i, (dt, f) in enumerate(sessions):
        if i >= 14:
            prev_trs = [daily_ranges[k][1] for k in range(i-14, i)]
            atr14 = np.mean(prev_trs)
        else:
            atr14 = 550.0
            
        df = pd.read_parquet(f)
        if len(df) < 10:
            continue
            
        df['ist'] = df['date'].dt.tz_convert('Asia/Kolkata')
        
        c0 = df.iloc[0]
        c0_open = c0['open']
        c0_high = c0['high']
        c0_low = c0['low']
        c0_close = c0['close']
        
        c0_range = c0_high - c0_low
        c0_body = abs(c0_close - c0_open)
        c0_body_ratio = c0_body / max(1.0, c0_range)
        
        # SENSEX Weekly Expiry is Thursday (weekday() == 3)
        # Compute exact DTE:
        # Thursday = 0.2 DTE (expiry day)
        # Wednesday = 1.0 DTE
        # Tuesday = 2.0 DTE
        # Monday = 3.0 DTE
        # Friday = 4.0 DTE (prior Friday)
        weekday = dt.weekday()
        is_expiry = (weekday == 3)
        if is_expiry:
            dte = 0.20
        elif weekday == 2: # Wednesday
            dte = 1.0
        elif weekday == 1: # Tuesday
            dte = 2.0
        elif weekday == 0: # Monday
            dte = 3.0
        else: # Friday (4)
            dte = 4.0
            
        # VIX proxy from daily ATR/Spot or default ~13.5
        vix = 13.5
        
        gate2_passed = True
        gate2_reasons = []
        
        if atr14 < 450.0:
            gate2_passed = False
            gate2_reasons.append(f"Low ATR ({atr14:.0f} < 450)")
            
        min_or_req = 0.35 * atr14
        if c0_range < min_or_req:
            gate2_passed = False
            gate2_reasons.append(f"Narrow OR ({c0_range:.0f} < {min_or_req:.0f})")
            
        if c0_body_ratio < 0.55:
            gate2_passed = False
            gate2_reasons.append(f"Doji/Weak Body ({c0_body_ratio*100:.1f}% < 55%)")
            
        bullish = c0_close > c0_open
        direction = "BULLISH" if bullish else "BEARISH"
        
        td = round(c0_close / 300.0) * 300.0
        rp1 = td + 300.0 if bullish else td - 300.0
        rp2 = td + 600.0 if bullish else td - 600.0
        
        target_strike = int(round(rp2 / 100.0) * 100)
        option_type = "CE" if bullish else "PE"
        contract_symbol = f"SENSEX {target_strike} {option_type}"
        
        # DYNAMIC SUSTAINABLE ANCHOR:
        dynamic_anchor = calculate_dynamic_sustainable_anchor(c0_close, vix, dte)
        
        # OptionMate Premium Selection Rule:
        # On Expiry Day (0-DTE): Use the ₹28 - ₹48 ladder (median ₹38) for OTM slingshot at RP2
        # On Non-Expiry Day (>1-DTE): The entry premium for an OTM contract at RP2 (300-600 pts OTM)
        # trades at approximately 0.50x to 0.65x of the Dynamic ATM Sustainable Anchor!
        if is_expiry:
            entry_premium = 38.0
        else:
            # 600-pt OTM option on SENSEX trades at ~55% of the ATM half-straddle anchor
            entry_premium = round(dynamic_anchor * 0.55, 1)
        
        entry_triggered = False
        entry_candle_idx = -1
        entry_price = 0.0
        entry_time = ""
        
        if gate2_passed:
            for idx in range(1, min(len(df), 25)):
                curr_c = df.iloc[idx]
                curr_t = curr_c['ist'].strftime('%H:%M')
                
                if idx == 1:
                    if (bullish and curr_c['high'] > c0_high) or (not bullish and curr_c['low'] < c0_low):
                        entry_triggered = True
                        entry_candle_idx = idx
                        entry_price = c0_high if bullish else c0_low
                        entry_time = curr_t
                        break
                else:
                    if bullish and curr_c['close'] > c0_high:
                        entry_triggered = True
                        entry_candle_idx = idx
                        entry_price = curr_c['close']
                        entry_time = curr_t
                        break
                    elif not bullish and curr_c['close'] < c0_low:
                        entry_triggered = True
                        entry_candle_idx = idx
                        entry_price = curr_c['close']
                        entry_time = curr_t
                        break

        trade_outcome = "NO_TRADE"
        exit_time = ""
        exit_premium = 0.0
        pts_captured = 0.0
        pnl_per_lot = 0.0
        invalidation_level = (c0_low - 50.0) if bullish else (c0_high + 50.0)
        
        if entry_triggered:
            subsequent_bars = df.iloc[entry_candle_idx+1:]
            
            # 2-Tier Target Management:
            half_booked = False
            rp1_hit_time = ""
            cost_sl_active = False
            
            for s_idx, bar in subsequent_bars.iterrows():
                b_high = bar['high']
                b_low = bar['low']
                b_close = bar['close']
                b_time = bar['ist'].strftime('%H:%M')
                
                # Check Invalidation
                if not cost_sl_active:
                    if bullish and b_low <= invalidation_level:
                        trade_outcome = "STOP_LOSS_HIT"
                        exit_time = b_time
                        exit_premium = entry_premium * 0.70 if is_expiry else entry_premium * 0.80
                        break
                    elif not bullish and b_high >= invalidation_level:
                        trade_outcome = "STOP_LOSS_HIT"
                        exit_time = b_time
                        exit_premium = entry_premium * 0.70 if is_expiry else entry_premium * 0.80
                        break
                else:
                    # Trailing cost SL active on runner
                    if bullish and b_low <= entry_price:
                        trade_outcome = "TRAILED_COST_EXIT"
                        exit_time = b_time
                        exit_premium = (exit_premium + entry_premium) / 2.0
                        break
                    elif not bullish and b_high >= entry_price:
                        trade_outcome = "TRAILED_COST_EXIT"
                        exit_time = b_time
                        exit_premium = (exit_premium + entry_premium) / 2.0
                        break
                        
                # Check RP1 (+300 pts)
                if not half_booked:
                    if (bullish and b_high >= rp1) or (not bullish and b_low <= rp1):
                        half_booked = True
                        rp1_hit_time = b_time
                        cost_sl_active = True
                        # RP1 expansion: on expiry 2.0x, on non-expiry 1.40x
                        rp1_premium = entry_premium * 2.0 if is_expiry else entry_premium * 1.40
                        exit_premium = rp1_premium
                        
                # Check RP2 (+600 pts)
                if half_booked:
                    if (bullish and b_high >= rp2) or (not bullish and b_low <= rp2):
                        trade_outcome = "TARGET_RP2_HIT"
                        exit_time = b_time
                        rp2_premium = entry_premium * 3.2 if is_expiry else entry_premium * 1.75
                        exit_premium = (exit_premium + rp2_premium) / 2.0
                        break
                        
                # EOD Exit (15:15)
                if bar['ist'].hour >= 15 and bar['ist'].minute >= 15:
                    if half_booked:
                        trade_outcome = "HALF_RP1_EOD"
                        exit_time = b_time
                        exit_premium = (exit_premium + entry_premium) / 2.0
                    else:
                        trade_outcome = "EOD_SQUAREOFF"
                        exit_time = b_time
                        exit_premium = entry_premium * 0.60 if is_expiry else entry_premium * 0.85
                    break
                    
            if exit_premium > 0:
                pts_captured = exit_premium - entry_premium
                pnl_per_lot = pts_captured * 20.0
                
        results.append({
            'date': dt,
            'is_expiry': is_expiry,
            'day_name': dt.strftime('%a'),
            'dte': dte,
            'atr14': atr14,
            'c0_range': c0_range,
            'c0_body_ratio': c0_body_ratio,
            'direction': direction,
            'gate2_passed': gate2_passed,
            'gate2_reasons': "; ".join(gate2_reasons) if not gate2_passed else "PASSED",
            'entry_triggered': entry_triggered,
            'entry_time': entry_time,
            'contract': contract_symbol if entry_triggered else "-",
            'dynamic_anchor': dynamic_anchor if entry_triggered else 0.0,
            'entry_prem': entry_premium if entry_triggered else 0.0,
            'exit_prem': round(exit_premium, 2) if entry_triggered else 0.0,
            'pts_captured': round(pts_captured, 2),
            'pnl_per_lot': round(pnl_per_lot, 2),
            'outcome': trade_outcome if entry_triggered else "GATE2_FILTERED"
        })
        
    res_df = pd.DataFrame(results)
    return res_df

if __name__ == '__main__':
    df = run_realistic_backtest()
    
    expiry_df = df[df['is_expiry'] == True]
    non_expiry_df = df[df['is_expiry'] == False]
    
    print("\n================== DYNAMIC SENSEX EXPIRY THURSDAYS (0-DTE) ==================")
    print(f"Total Expiry Sessions: {len(expiry_df)}")
    exp_trades = expiry_df[expiry_df['entry_triggered'] == True]
    print(f"Trades Fired: {len(exp_trades)}")
    if len(exp_trades) > 0:
        exp_wins = exp_trades[exp_trades['pts_captured'] > 0]
        exp_losses = exp_trades[exp_trades['pts_captured'] <= 0]
        print(f"Wins: {len(exp_wins)} ({len(exp_wins)/len(exp_trades)*100:.1f}%)")
        print(f"Losses: {len(exp_losses)} ({len(exp_losses)/len(exp_trades)*100:.1f}%)")
        print(f"Total PnL per lot (20 qty): Rs. {exp_trades['pnl_per_lot'].sum():,.2f}")
        print(f"Avg PnL per trade: Rs. {exp_trades['pnl_per_lot'].mean():,.2f}")
        print("\nAll Expiry Trades Detail:")
        print(exp_trades[['date', 'direction', 'entry_time', 'contract', 'dynamic_anchor', 'entry_prem', 'exit_prem', 'pts_captured', 'pnl_per_lot', 'outcome']].to_string(index=False))

    print("\n================== DYNAMIC SENSEX NON-EXPIRY SESSIONS ==================")
    print(f"Total Non-Expiry Sessions: {len(non_expiry_df)}")
    non_trades = non_expiry_df[non_expiry_df['entry_triggered'] == True]
    print(f"Trades Fired: {len(non_trades)}")
    if len(non_trades) > 0:
        non_wins = non_trades[non_trades['pts_captured'] > 0]
        non_losses = non_trades[non_trades['pts_captured'] <= 0]
        print(f"Wins: {len(non_wins)} ({len(non_wins)/len(non_trades)*100:.1f}%)")
        print(f"Losses: {len(non_losses)} ({len(non_losses)/len(non_trades)*100:.1f}%)")
        print(f"Total PnL per lot (20 qty): Rs. {non_trades['pnl_per_lot'].sum():,.2f}")
        print(f"Avg PnL per trade: Rs. {non_trades['pnl_per_lot'].mean():,.2f}")
        print("\nAll Non-Expiry Trades Detail (Dynamic Anchors & Premiums):")
        print(non_trades[['date', 'day_name', 'dte', 'direction', 'entry_time', 'contract', 'dynamic_anchor', 'entry_prem', 'exit_prem', 'pts_captured', 'pnl_per_lot', 'outcome']].to_string(index=False))

    df.to_csv('runtime/sensex_optionmate_realistic_audit.csv', index=False)
    print("\nUpdated runtime/sensex_optionmate_realistic_audit.csv with dynamic premiums and anchors.")
