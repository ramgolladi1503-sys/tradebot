import pandas as pd
import numpy as np

def build_vectorized_signals(df: pd.DataFrame, config) -> pd.DataFrame:
    """
    Fully vectorized mapping of TradeBuilder and ensemble.py logic.
    Returns a DataFrame containing only rows with valid trading signals.
    """
    df = df.copy()
    
    # 1. Base arrays needed
    ltp = df['close']
    vwap = df.get('vwap', df['close'].rolling(20).mean())
    atr = df.get('atr_14', df['close'].rolling(14).std() * 1.5)
    
    # Fill NA for missing indicators to prevent mask issues
    vwap = vwap.fillna(ltp)
    atr = atr.fillna(0)
    
    vwap_slope = df.get('vwap_slope', vwap.pct_change(periods=5).fillna(0))
    rsi_mom = df.get('rsi_mom', df['close'].pct_change(periods=5).fillna(0))
    orb_high = df.get('orb_high', df['high'].rolling(5).max().shift(1).fillna(0))
    orb_low = df.get('orb_low', df['low'].rolling(5).min().shift(1).fillna(100000))
    vol_z = df.get('vol_z', pd.Series(0, index=df.index))
    
    trend = (ltp - vwap) / vwap
    
    # 2. Volatility Filter
    valid_vol = (atr / ltp) >= 0.001
    
    # 3. Strategy Masks
    # Trend VWAP
    buy_trend = (trend > 0.0015) & (vwap_slope >= -0.02)
    sell_trend = (trend < -0.0015) & (vwap_slope <= 0.02)
    
    # Mean Reversion
    buy_mr = (trend < -0.003) & (rsi_mom >= -0.2)
    sell_mr = (trend > 0.003) & (rsi_mom <= 0.2)
    
    # ORB Breakout
    buy_orb = (ltp > orb_high) & (vol_z > 0.2)
    sell_orb = (ltp < orb_low) & (vol_z > 0.2)
    
    # 4. Time of Day Filter
    if 'timestamp' in df.columns:
        dt = pd.to_datetime(df['timestamp'])
        if dt.dt.tz is None:
            dt = dt.dt.tz_localize('UTC')
        dt_ist = dt.dt.tz_convert('Asia/Kolkata')
        time_strs = dt_ist.dt.strftime('%H:%M')
        
        start_time = getattr(config, 'allowed_time_start', "09:15")
        end_time = getattr(config, 'allowed_time_end', "15:30")
        time_mask = (time_strs >= start_time) & (time_strs <= end_time)
    else:
        time_mask = pd.Series(True, index=df.index)

    # 5. Final Aggregated Signals
    buy_mask = (buy_trend | buy_mr | buy_orb) & valid_vol & time_mask
    sell_mask = (sell_trend | sell_mr | sell_orb) & valid_vol & time_mask
    
    # 6. Build Signals DataFrame
    signals_df = pd.DataFrame(index=df.index)
    signals_df['signal_side'] = np.where(buy_mask, 'BUY', np.where(sell_mask, 'SELL', None))
    
    # Drop rows without signals
    signals_df = signals_df.dropna(subset=['signal_side']).copy()
    
    if signals_df.empty:
        return signals_df
        
    # Map valid signal indices back to original dataframe to extract prices
    sig_ltp = df.loc[signals_df.index, 'close']
    sig_atr = atr.loc[signals_df.index]
    
    signals_df['entry_price'] = sig_ltp
    
    # Risk parameters: Configurable ATR multipliers
    is_buy = signals_df['signal_side'] == 'BUY'
    
    tgt_mult = getattr(config, 'target_atr_mult', 1.5)
    stp_mult = getattr(config, 'stop_atr_mult', 1.0)
    
    signals_df['target'] = np.where(is_buy, sig_ltp + sig_atr * tgt_mult, sig_ltp - sig_atr * tgt_mult)
    signals_df['stop_loss'] = np.where(is_buy, sig_ltp - sig_atr * stp_mult, sig_ltp + sig_atr * stp_mult)
    
    # Qty and Lot Size (Static base mapping for elite backtests)
    signals_df['qty'] = 1  # 1 lot by default
    signals_df['lot_size'] = 65  # NIFTY lot size
    
    # Canonical Setup Identity
    # For vectorized, we infer strategy_family from which mask triggered
    signals_df['strategy_family'] = np.where(buy_trend | sell_trend, "TrendVWAP", 
                                    np.where(buy_mr | sell_mr, "MeanReversion", 
                                    np.where(buy_orb | sell_orb, "ORB", "Unknown")))
    
    signals_df['regime'] = "base" # Can be expanded based on vol_z or trend
    signals_df['direction'] = signals_df['signal_side']
    signals_df['entry'] = signals_df['entry_price']
    
    # Generate unique setup IDs
    signals_df['setup_id'] = [f"vec_{str(idx)}_{fam}" for idx, fam in zip(signals_df.index, signals_df['strategy_family'])]
    
    signals_df['confidence'] = 0.5 # Default heuristic confidence
    signals_df['truth_quality'] = "VECTORIZED_HEURISTIC"
    
    return signals_df
