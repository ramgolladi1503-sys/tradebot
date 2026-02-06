import pandas as pd

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add common indicators to an OHLCV dataframe.
    Required columns: ['open','high','low','close','volume']
    """
    df = df.copy()
    df["sma_10"] = df["close"].rolling(10).mean()
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()

    # RSI 14
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-9)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # ATR 14
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()

    # VWAP (cumulative)
    pv = df["close"] * df["volume"]
    df["vwap"] = (pv.cumsum() / df["volume"].replace(0, 1).cumsum())
    df["vwap_slope"] = df["vwap"].diff(3)

    # Returns
    df["return_1"] = df["close"].pct_change(1)

    # RSI momentum
    df["rsi_mom"] = df["rsi_14"].diff(3)

    # Simple volume profile proxy: z-score of volume
    vol_mean = df["volume"].rolling(20).mean()
    vol_std = df["volume"].rolling(20).std().replace(0, 1)
    df["vol_z"] = (df["volume"] - vol_mean) / vol_std

    # ADX proxy
    df["adx_14"] = _adx(df)

    # Clean NaNs
    return df

def _adx(df, period=14):
    high = df["high"]
    low = df["low"]
    close = df["close"]
    plus_dm = high.diff()
    minus_dm = low.diff() * -1
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([pd.NA, pd.NaT], 0) * 100
    return dx.rolling(period).mean()

def build_trade_features(market_data, opt):
    """
    Build a feature dict for ML scoring.
    """
    ltp = market_data.get("ltp", 0)
    vwap = market_data.get("vwap", ltp)
    atr = market_data.get("atr", 0)

    spread = max(opt["ask"] - opt["bid"], 0)
    spread_pct = spread / opt["ltp"] if opt["ltp"] else 0
    moneyness = (ltp - opt["strike"]) / ltp if ltp else 0
    vwap_dist = (ltp - vwap) / vwap if vwap else 0

    return {
        "ltp": opt["ltp"],
        "bid": opt["bid"],
        "ask": opt["ask"],
        "spread_pct": spread_pct,
        "volume": opt.get("volume", 0),
        "atr": atr,
        "vwap_dist": vwap_dist,
        "moneyness": moneyness,
        "is_call": 1 if opt["type"] == "CE" else 0,
        "vwap_slope": market_data.get("vwap_slope", 0),
        "rsi_mom": market_data.get("rsi_mom", 0),
        "vol_z": market_data.get("vol_z", 0)
    }
