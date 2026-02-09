import pandas as pd
from core.time_utils import now_ist


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


def _time_bucket(ts):
    try:
        h = ts.hour
    except Exception:
        h = now_ist().hour
    if h < 11:
        return "OPEN"
    if h < 14:
        return "MID"
    return "CLOSE"


def _regime_label(regime):
    r = str(regime or "").upper()
    mapping = {
        "TREND": "TREND",
        "RANGE": "RANGE",
        "RANGE_VOLATILE": "RANGE_VOLATILE",
        "EVENT": "EVENT",
        "PANIC": "PANIC",
    }
    return mapping.get(r, "NEUTRAL")


def _vol_quartile(vol_z):
    try:
        v = float(vol_z)
    except Exception:
        return 2
    if v <= -0.5:
        return 1
    if v <= 0.5:
        return 2
    if v <= 1.5:
        return 3
    return 4


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

    regime = market_data.get("primary_regime") or market_data.get("regime")
    time_bucket = market_data.get("time_bucket") or _time_bucket(market_data.get("timestamp", now_ist()))
    is_expiry = market_data.get("day_type") in ("EXPIRY_DAY",)
    vol_q = market_data.get("vol_quartile")
    if vol_q is None:
        vol_q = _vol_quartile(market_data.get("vol_z", 0))

    fx_ret_5m = market_data.get("fx_ret_5m")
    if fx_ret_5m is None:
        fx_ret_5m = market_data.get("x_usdinr_ret5") or market_data.get("x_fx_ret5")
    vix_z = market_data.get("vix_z")
    if vix_z is None:
        vix_z = market_data.get("x_india_vix_z") or market_data.get("x_vix_z")
    crude_ret_15m = market_data.get("crude_ret_15m")
    if crude_ret_15m is None:
        crude_ret_15m = market_data.get("x_crude_ret15") or market_data.get("x_crudeoil_ret15")
    corr_fx_nifty = market_data.get("corr_fx_nifty")
    if corr_fx_nifty is None:
        corr_fx_nifty = market_data.get("x_usdinr_corr_nifty") or market_data.get("x_fx_corr_nifty")

    feats = {
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
        "vol_z": market_data.get("vol_z", 0),
        "fx_ret_5m": 0.0 if fx_ret_5m is None else fx_ret_5m,
        "vix_z": 0.0 if vix_z is None else vix_z,
        "crude_ret_15m": 0.0 if crude_ret_15m is None else crude_ret_15m,
        "corr_fx_nifty": 0.0 if corr_fx_nifty is None else corr_fx_nifty,
        "seg_regime": _regime_label(regime),
        "seg_bucket": str(time_bucket).upper(),
        "seg_expiry": 1 if is_expiry else 0,
        "seg_vol_q": int(vol_q),
    }
    try:
        for k, v in (market_data or {}).items():
            if isinstance(k, str) and k.startswith("x_"):
                feats[k] = 0.0 if v is None else v
    except Exception:
        pass
    return feats
