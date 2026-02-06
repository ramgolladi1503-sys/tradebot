from statistics import mean, pstdev


def _safe_mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def compute_indicators(candles, vwap_window=20, atr_period=14, adx_period=14, vol_window=30, slope_window=10):
    """
    Compute VWAP, VWAP slope, ATR, ADX, vol_z from in-memory candles.
    Returns dict with ok flag and last_ts.
    """
    out = {
        "vwap": None,
        "vwap_slope": 0.0,
        "atr": None,
        "adx": None,
        "vol_z": 0.0,
        "ok": False,
        "last_ts": None,
    }
    if not candles:
        return out
    out["last_ts"] = candles[-1].get("ts")
    if len(candles) < max(vwap_window, atr_period + 1, adx_period + 1, vol_window):
        return out

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    vols = [c.get("volume", 1) or 1 for c in candles]

    # VWAP
    tp = [((h + l + c) / 3.0) for h, l, c in zip(highs, lows, closes)]
    tp_window = tp[-vwap_window:]
    vol_window = vols[-vwap_window:]
    vwap = sum(t * v for t, v in zip(tp_window, vol_window)) / max(sum(vol_window), 1)
    out["vwap"] = vwap

    # VWAP slope (simple)
    if len(tp) >= slope_window + 1:
        v0 = sum(tp[-slope_window-1:-1]) / slope_window
        out["vwap_slope"] = (vwap - v0) / slope_window

    # ATR
    tr = []
    for i in range(1, len(candles)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        tr.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    atr = sum(tr[-atr_period:]) / atr_period
    out["atr"] = atr

    # ADX (Wilder)
    plus_dm = []
    minus_dm = []
    tr2 = []
    for i in range(1, len(candles)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)
        tr2.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    if len(tr2) >= adx_period:
        atr_s = sum(tr2[:adx_period])
        plus_s = sum(plus_dm[:adx_period])
        minus_s = sum(minus_dm[:adx_period])
        dx_list = []
        for i in range(adx_period, len(tr2)):
            atr_s = atr_s - (atr_s / adx_period) + tr2[i]
            plus_s = plus_s - (plus_s / adx_period) + plus_dm[i]
            minus_s = minus_s - (minus_s / adx_period) + minus_dm[i]
            plus_di = 100 * (plus_s / atr_s) if atr_s else 0
            minus_di = 100 * (minus_s / atr_s) if atr_s else 0
            dx = 100 * abs(plus_di - minus_di) / max(plus_di + minus_di, 1e-9)
            dx_list.append(dx)
        if dx_list:
            out["adx"] = sum(dx_list[-adx_period:]) / min(len(dx_list), adx_period)

    # vol_z based on ATR% history
    atr_pct_series = []
    for i in range(atr_period, len(tr)):
        close = closes[i] if closes[i] else 1
        atr_i = sum(tr[i-atr_period:i]) / atr_period
        atr_pct_series.append(atr_i / close)
    if len(atr_pct_series) >= 5:
        mu = mean(atr_pct_series)
        sd = pstdev(atr_pct_series) or 0.0
        out["vol_z"] = (atr_pct_series[-1] - mu) / sd if sd > 0 else 0.0

    out["ok"] = True
    return out
