import pandas as pd
import numpy as np

def build_vectorized_signals(df: pd.DataFrame, config) -> pd.DataFrame:
    """
    Fully vectorized mapping of TradeBuilder and ensemble.py logic.
    Optimized for intraday 5-minute data dynamics.
    Returns a DataFrame containing only rows with valid trading signals.
    """
    df = df.copy()
    
    # Check if index is datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except:
            return pd.DataFrame() # Needs datetime index for daily groupings
            
    # 1. Base Intraday Arrays
    ltp = df['close']
    
    # True Daily Anchored VWAP
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    cum_pv = (typical_price * df['volume']).groupby(df.index.date).cumsum()
    cum_v = df['volume'].groupby(df.index.date).cumsum()
    vwap = cum_pv / cum_v
    
    # Ensure VWAP has no NAs
    vwap = vwap.fillna(ltp)
    
    # 14-period ATR
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().fillna(0)
    
    # VWAP slope (in basis points)
    vwap_slope = (vwap.diff(3) / vwap.shift(3) * 10000).fillna(0)
    
    # RSI 14
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi_14 = 100 - (100 / (1 + rs))
    rsi_14 = rsi_14.fillna(50)
    
    rsi_mom = rsi_14.diff(3).fillna(0)
    
    # ADX 14
    up_move = df['high'] - df['high'].shift()
    down_move = df['low'].shift() - df['low']
    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    pos_dm_series = pd.Series(pos_dm, index=df.index)
    neg_dm_series = pd.Series(neg_dm, index=df.index)
    tr_smooth = tr.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    pos_di = 100 * (pos_dm_series.ewm(alpha=1/14, min_periods=14, adjust=False).mean() / tr_smooth)
    neg_di = 100 * (neg_dm_series.ewm(alpha=1/14, min_periods=14, adjust=False).mean() / tr_smooth)
    dx = 100 * (pos_di - neg_di).abs() / (pos_di + neg_di).abs()
    adx = dx.ewm(alpha=1/14, min_periods=14, adjust=False).mean().fillna(25)
    
    # Daily 20-EMA Macro Filter
    # Resample to daily 'close', compute EMA 20, then forward-fill back to intraday index
    daily_close = df['close'].resample('D').last()
    daily_ema_20 = daily_close.ewm(span=20, adjust=False).mean()
    # Reindex back to intraday and forward fill
    macro_ema = daily_ema_20.reindex(df.index, method='ffill')
    
    # 15-Minute ORB (Opening Range Breakout)
    # Get high/low of the first 3 bars (09:15, 09:20, 09:25) of each day
    orb_high = df.groupby(df.index.date)['high'].transform(lambda x: x.iloc[:3].max() if len(x) >= 3 else x.max())
    orb_low = df.groupby(df.index.date)['low'].transform(lambda x: x.iloc[:3].min() if len(x) >= 3 else x.min())
    
    # 2. Volatility Filter (Recalibrated for intraday)
    # ATR needs to be at least 0.05% of price for decent 5-min volatility
    valid_vol = (atr / ltp) >= 0.0005
    trend = (ltp - vwap) / vwap
    
    # VWAP ATR Bands
    vwap_upper = vwap + (atr * 1.5)
    vwap_lower = vwap - (atr * 1.5)
    vwap_mr_upper = vwap + (atr * 2.5)
    vwap_mr_lower = vwap - (atr * 2.5)
    
    # (RSI and ADX already computed above)
    vol_z = df.get('vol_z', pd.Series(0, index=df.index))
    # Trend VWAP (Breakout of ATR band, strict slope, strong ADX, aligns with Macro Trend)
    macro_bull = ltp > macro_ema
    macro_bear = ltp < macro_ema
    buy_trend = (ltp > vwap_upper) & (ltp.shift(1) <= vwap_upper) & (vwap_slope >= 0) & (adx > 25) & macro_bull
    sell_trend = (ltp < vwap_lower) & (ltp.shift(1) >= vwap_lower) & (vwap_slope <= 0) & (adx > 25) & macro_bear
    
    # Mean Reversion (Statistical extreme ATR stretch, RSI oversold/overbought)
    buy_mr = (ltp < vwap_mr_lower) & (rsi_14 < 30) & (rsi_mom >= 0)
    sell_mr = (ltp > vwap_mr_upper) & (rsi_14 > 70) & (rsi_mom <= 0)
    
    # ORB Breakout (Price crossing the 15-min range + buffer, strong ADX, valid after 09:30)
    time_strs = df.index.strftime('%H:%M')
    after_orb = time_strs >= "09:30"
    
    orb_upper_buf = orb_high + (atr * 0.2)
    orb_lower_buf = orb_low - (atr * 0.2)
    
    buy_orb = (ltp > orb_upper_buf) & (ltp.shift(1) <= orb_upper_buf) & after_orb & (adx > 25) & macro_bull
    sell_orb = (ltp < orb_lower_buf) & (ltp.shift(1) >= orb_lower_buf) & after_orb & (adx > 25) & macro_bear
    
    # 4. Time of Day Filter
    start_time = getattr(config, 'allowed_time_start', "09:30")
    end_time = getattr(config, 'allowed_time_end', "15:00")
    time_mask = (time_strs >= start_time) & (time_strs <= end_time)

    # 5. Final Aggregated Signals
    buy_mask = (buy_trend | buy_mr | buy_orb) & valid_vol & time_mask
    sell_mask = (sell_trend | sell_mr | sell_orb) & valid_vol & time_mask
    
    # 6. Build Signals DataFrame
    signals_df = pd.DataFrame(index=df.index)
    signals_df['signal_side'] = np.where(buy_mask, 'BUY', np.where(sell_mask, 'SELL', None))
    
    # ML Features
    signals_df['rsi_14'] = rsi_14
    signals_df['adx_14'] = adx
    signals_df['vwap_slope'] = vwap_slope
    signals_df['trend_dist'] = trend
    signals_df['atr_pct'] = (atr / ltp) * 100
    signals_df['hour'] = df.index.hour
    signals_df['minute'] = df.index.minute
    
    # Drop rows without signals
    signals_df = signals_df.dropna(subset=['signal_side']).copy()
    
    if signals_df.empty:
        return signals_df
        
    # Map valid signal indices back to original dataframe to extract prices
    # USE NEXT BAR'S OPEN to avoid lookahead bias!
    next_open = df['open'].shift(-1)
    # If the signal is on the very last bar, fallback to its close
    sig_entry = next_open.loc[signals_df.index].fillna(df.loc[signals_df.index, 'close'])
    sig_atr = atr.loc[signals_df.index]
    
    signals_df['entry_price'] = sig_entry
    
    # Risk parameters: Configurable ATR multipliers
    is_buy = signals_df['signal_side'] == 'BUY'
    
    tgt_mult = getattr(config, 'target_atr_mult', 1.5)
    stp_mult = getattr(config, 'stop_atr_mult', 1.0)
    
    # Stop and Target must be anchored to the actual execution entry, not the signal bar close
    signals_df['target'] = np.where(is_buy, sig_entry + sig_atr * tgt_mult, sig_entry - sig_atr * tgt_mult)
    signals_df['stop_loss'] = np.where(is_buy, sig_entry - sig_atr * stp_mult, sig_entry + sig_atr * stp_mult)
    
    # Qty and Lot Size
    try:
        from config import config as cfg
        nifty_lot = getattr(cfg, 'LOT_SIZE', {}).get('NIFTY', 65)
    except ImportError:
        nifty_lot = 65
        
    signals_df['qty'] = 1  # 1 lot by default
    signals_df['lot_size'] = nifty_lot
    
    # Canonical Setup Identity
    buy_trend_mask = buy_trend.loc[signals_df.index]
    sell_trend_mask = sell_trend.loc[signals_df.index]
    buy_mr_mask = buy_mr.loc[signals_df.index]
    sell_mr_mask = sell_mr.loc[signals_df.index]
    buy_orb_mask = buy_orb.loc[signals_df.index]
    sell_orb_mask = sell_orb.loc[signals_df.index]
    
    signals_df['strategy_family'] = np.where(buy_trend_mask | sell_trend_mask, "TrendVWAP", 
                                    np.where(buy_mr_mask | sell_mr_mask, "MeanReversion", 
                                    np.where(buy_orb_mask | sell_orb_mask, "ORB", "Unknown")))
    
    # Dynamic Regime Inference
    signals_df['regime'] = np.where(vol_z.loc[signals_df.index] > 1.0, "high_vol", 
                           np.where(vol_z.loc[signals_df.index] < -1.0, "low_vol", "base"))
    signals_df['direction'] = signals_df['signal_side']
    signals_df['entry'] = signals_df['entry_price']
    
    # Dynamic confidence
    trend_val = trend.loc[signals_df.index]
    rsi_val = rsi_mom.loc[signals_df.index]
    signals_df['confidence'] = np.clip(0.5 + abs(trend_val) * 10 + abs(rsi_val) * 0.5, 0.5, 1.0)
    
    time_bucket = pd.Series(signals_df.index.strftime('%H'), index=signals_df.index)
    vol_bucket = np.where(vol_z.loc[signals_df.index] > 0, "high", "low")
    
    # Deterministic fingerprint setup_id
    signals_df['setup_id'] = (
        signals_df['strategy_family'] + "_" + 
        signals_df['regime'] + "_" + 
        signals_df['direction'] + "_v" + 
        vol_bucket + "_t" +
        time_bucket
    )
    signals_df['truth_quality'] = "VECTORIZED_HEURISTIC"
    
    return signals_df
