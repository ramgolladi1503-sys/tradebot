import numpy as np
import pandas as pd


def _causal_prior_session_ema(close: pd.Series, span: int = 20) -> pd.Series:
    """Return the EMA of completed prior-session closes for each intraday row."""
    if not isinstance(close.index, pd.DatetimeIndex):
        raise TypeError("close must use a DatetimeIndex")
    if span <= 0:
        raise ValueError("span must be positive")

    session_keys = close.index.normalize()
    daily_close = close.groupby(session_keys).last()
    prior_session_ema = daily_close.ewm(span=span, adjust=False).mean().shift(1)
    return pd.Series(session_keys, index=close.index).map(prior_session_ema).astype(float)


def _same_session_next_open(open_prices: pd.Series) -> pd.Series:
    """Return next-bar opens only when the next row is in the same session."""
    if not isinstance(open_prices.index, pd.DatetimeIndex):
        raise TypeError("open_prices must use a DatetimeIndex")
    if not open_prices.index.is_monotonic_increasing:
        raise ValueError("open_prices must be sorted chronologically")

    sessions = pd.Series(open_prices.index.normalize(), index=open_prices.index)
    next_open = open_prices.shift(-1)
    next_session = sessions.shift(-1)
    return next_open.where(next_session.eq(sessions))


def build_vectorized_signals(df: pd.DataFrame, config) -> pd.DataFrame:
    """Build causal vectorized intraday signals with next-bar-open entries."""
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except BaseException:
            return pd.DataFrame()
    if not df.index.is_monotonic_increasing:
        raise ValueError("signal data must be sorted chronologically")

    ltp = df["close"]
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_pv = (typical_price * df["volume"]).groupby(df.index.date).cumsum()
    cum_v = df["volume"].groupby(df.index.date).cumsum()
    vwap = (cum_pv / cum_v).fillna(ltp)

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().fillna(0)
    vwap_slope = (vwap.diff(3) / vwap.shift(3) * 10000).fillna(0)

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi_14 = (100 - (100 / (1 + rs))).fillna(50)
    rsi_mom = rsi_14.diff(3).fillna(0)

    up_move = df["high"] - df["high"].shift()
    down_move = df["low"].shift() - df["low"]
    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    pos_dm_series = pd.Series(pos_dm, index=df.index)
    neg_dm_series = pd.Series(neg_dm, index=df.index)
    tr_smooth = tr.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    pos_di = 100 * (
        pos_dm_series.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        / tr_smooth
    )
    neg_di = 100 * (
        neg_dm_series.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        / tr_smooth
    )
    dx = 100 * (pos_di - neg_di).abs() / (pos_di + neg_di).abs()
    adx = dx.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean().fillna(25)

    macro_ema = _causal_prior_session_ema(df["close"], span=20)
    orb_high = df.groupby(df.index.date)["high"].transform(
        lambda values: values.iloc[:3].max() if len(values) >= 3 else values.max()
    )
    orb_low = df.groupby(df.index.date)["low"].transform(
        lambda values: values.iloc[:3].min() if len(values) >= 3 else values.min()
    )

    valid_vol = (atr / ltp) >= 0.0005
    trend = (ltp - vwap) / vwap
    vwap_upper = vwap + (atr * 1.5)
    vwap_lower = vwap - (atr * 1.5)
    vwap_mr_upper = vwap + (atr * 2.5)
    vwap_mr_lower = vwap - (atr * 2.5)

    vol_z = df.get("vol_z", pd.Series(0, index=df.index))
    macro_bull = ltp > macro_ema
    macro_bear = ltp < macro_ema
    buy_trend = (
        (ltp > vwap_upper)
        & (ltp.shift(1) <= vwap_upper)
        & (vwap_slope >= 0)
        & (adx > 25)
        & macro_bull
    )
    sell_trend = (
        (ltp < vwap_lower)
        & (ltp.shift(1) >= vwap_lower)
        & (vwap_slope <= 0)
        & (adx > 25)
        & macro_bear
    )
    buy_mr = (ltp < vwap_mr_lower) & (rsi_14 < 30) & (rsi_mom >= 0)
    sell_mr = (ltp > vwap_mr_upper) & (rsi_14 > 70) & (rsi_mom <= 0)

    time_strs = df.index.strftime("%H:%M")
    after_orb = time_strs >= "09:30"
    orb_upper_buf = orb_high + (atr * 0.2)
    orb_lower_buf = orb_low - (atr * 0.2)
    buy_orb = (
        (ltp > orb_upper_buf)
        & (ltp.shift(1) <= orb_upper_buf)
        & after_orb
        & (adx > 25)
        & macro_bull
    )
    sell_orb = (
        (ltp < orb_lower_buf)
        & (ltp.shift(1) >= orb_lower_buf)
        & after_orb
        & (adx > 25)
        & macro_bear
    )

    start_time = getattr(config, "allowed_time_start", "09:30")
    end_time = getattr(config, "allowed_time_end", "15:00")
    time_mask = (time_strs >= start_time) & (time_strs <= end_time)
    buy_mask = (buy_trend | buy_mr | buy_orb) & valid_vol & time_mask
    sell_mask = (sell_trend | sell_mr | sell_orb) & valid_vol & time_mask

    signals_df = pd.DataFrame(index=df.index)
    signals_df["signal_side"] = np.where(
        buy_mask, "BUY", np.where(sell_mask, "SELL", None)
    )
    signals_df["rsi_14"] = rsi_14
    signals_df["adx_14"] = adx
    signals_df["vwap_slope"] = vwap_slope
    signals_df["trend_dist"] = trend
    signals_df["atr_pct"] = (atr / ltp) * 100
    signals_df["hour"] = df.index.hour
    signals_df["minute"] = df.index.minute
    signals_df = signals_df.dropna(subset=["signal_side"]).copy()
    if signals_df.empty:
        return signals_df

    next_open = _same_session_next_open(df["open"])
    sig_entry = next_open.loc[signals_df.index]
    executable_mask = sig_entry.notna()
    signals_df = signals_df.loc[executable_mask].copy()
    sig_entry = sig_entry.loc[executable_mask]
    if signals_df.empty:
        return signals_df

    sig_atr = atr.loc[signals_df.index]
    signals_df["entry_price"] = sig_entry
    is_buy = signals_df["signal_side"] == "BUY"
    tgt_mult = getattr(config, "target_atr_mult", 1.5)
    stp_mult = getattr(config, "stop_atr_mult", 1.0)
    signals_df["target"] = np.where(
        is_buy, sig_entry + sig_atr * tgt_mult, sig_entry - sig_atr * tgt_mult
    )
    signals_df["stop_loss"] = np.where(
        is_buy, sig_entry - sig_atr * stp_mult, sig_entry + sig_atr * stp_mult
    )

    try:
        from config import config as cfg

        nifty_lot = getattr(cfg, "LOT_SIZE", {}).get("NIFTY", 65)
    except ImportError:
        nifty_lot = 65
    signals_df["qty"] = 1
    signals_df["lot_size"] = nifty_lot

    buy_trend_mask = buy_trend.loc[signals_df.index]
    sell_trend_mask = sell_trend.loc[signals_df.index]
    buy_mr_mask = buy_mr.loc[signals_df.index]
    sell_mr_mask = sell_mr.loc[signals_df.index]
    buy_orb_mask = buy_orb.loc[signals_df.index]
    sell_orb_mask = sell_orb.loc[signals_df.index]
    signals_df["strategy_family"] = np.where(
        buy_trend_mask | sell_trend_mask,
        "TrendVWAP",
        np.where(
            buy_mr_mask | sell_mr_mask,
            "MeanReversion",
            np.where(buy_orb_mask | sell_orb_mask, "ORB", "Unknown"),
        ),
    )

    signals_df["regime"] = np.where(
        vol_z.loc[signals_df.index] > 1.0,
        "high_vol",
        np.where(vol_z.loc[signals_df.index] < -1.0, "low_vol", "base"),
    )
    signals_df["direction"] = signals_df["signal_side"]
    signals_df["entry"] = signals_df["entry_price"]
    trend_val = trend.loc[signals_df.index]
    rsi_val = rsi_mom.loc[signals_df.index]
    signals_df["confidence"] = np.clip(
        0.5 + abs(trend_val) * 10 + abs(rsi_val) * 0.5, 0.5, 1.0
    )

    time_bucket = pd.Series(
        signals_df.index.strftime("%H"), index=signals_df.index
    )
    vol_bucket = np.where(vol_z.loc[signals_df.index] > 0, "high", "low")
    signals_df["setup_id"] = (
        signals_df["strategy_family"]
        + "_"
        + signals_df["regime"]
        + "_"
        + signals_df["direction"]
        + "_v"
        + vol_bucket
        + "_t"
        + time_bucket
    )
    signals_df["truth_quality"] = "VECTORIZED_HEURISTIC"
    return signals_df
