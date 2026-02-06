import pandas as pd

def adx(df, period=14):
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
    return dx.rolling(period).mean().iloc[-1]

def trend_slope(df, window=20):
    if len(df) < window:
        return 0.0
    y = df["close"].iloc[-window:].values
    x = pd.Series(range(window)).values
    coef = (x * y).sum() / (x * x).sum()
    return float(coef - y.mean())

def detect_regime(df):
    atr = (df["high"] - df["low"]).rolling(14).mean().iloc[-1]
    ltp = df["close"].iloc[-1]
    vol = atr / ltp if ltp else 0
    slope = trend_slope(df)
    adx_val = adx(df)

    if adx_val >= 25 and abs(slope) > 0:
        return "TREND"
    if vol < 0.001:
        return "CHOPPY"
    return "MEAN_REVERT"
