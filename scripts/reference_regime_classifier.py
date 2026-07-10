import pandas as pd
import numpy as np

def classify_reference_regime(df: pd.DataFrame):
    """
    Independent OHLC-only regime classifier for verification baseline.
    Does NOT import TradeBot production logic.
    """
    if df is None or len(df) == 0:
        return []
        
    df = df.copy()
    
    # Calculate some basic independent features
    df['return_5'] = df['close'].pct_change(5)
    df['high_5'] = df['high'].rolling(5).max()
    df['low_5'] = df['low'].rolling(5).min()
    df['range_pct'] = (df['high_5'] - df['low_5']) / df['low_5']
    df['tr'] = np.maximum(df['high'] - df['low'], np.maximum(abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1))))
    df['atr_proxy'] = df['tr'].rolling(14).mean() / df['close']
    
    # Very basic SMA trend slope
    df['sma_20'] = df['close'].rolling(20).mean()
    df['trend_slope'] = df['sma_20'].pct_change(3)
    
    records = []
    
    for idx, row in df.iterrows():
        ts = str(row.get('timestamp') or row.name)
        
        # Simple classification
        regime = "RANGE_NEUTRAL"
        strategy_family = "Mean Reversion"
        
        slope = row.get('trend_slope', 0)
        ret = row.get('return_5', 0)
        
        if pd.isna(slope): slope = 0
        if pd.isna(ret): ret = 0
        
        if slope > 0.0005 and ret > 0.001:
            regime = "TREND_UP"
            strategy_family = "Trend Pullback long"
        elif slope < -0.0005 and ret < -0.001:
            regime = "TREND_DOWN"
            strategy_family = "Trend Pullback short"
        elif row.get('range_pct', 0) < 0.002:
            regime = "COMPRESSION"
            strategy_family = "Compression Breakout watchlist"
        elif row.get('atr_proxy', 0) > 0.005:
            regime = "VOLATILE_CHOP"
            strategy_family = "reduce ranking confidence"
            
        record = {
            "market_timestamp": ts,
            "reference_regime": regime,
            "reference_strategy_family": strategy_family,
            "features": {
                "return_5": float(ret),
                "range_pct": float(row.get('range_pct', 0)),
                "atr_proxy": float(row.get('atr_proxy', 0)),
                "trend_slope": float(slope)
            }
        }
        records.append(record)
        
    return records
