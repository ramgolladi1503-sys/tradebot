"""Transparent AlphaTrendPro-inspired research mechanism.

This module does not reproduce the proprietary TradingView script. It converts
the published mechanism (trend + confirmed structure + six-line momentum +
fresh alignment / pullback continuation) into deterministic, auditable features
for NIFTY OHLCV research.

Research only: no broker, option selection, order, paper, or live authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd

BULLISH = 1
BEARISH = -1
NEUTRAL = 0

SIGNAL_COLUMNS = (
    "signal_trend_only",
    "signal_trend_structure",
    "signal_trend_momentum",
    "signal_full_fresh",
    "signal_continuation",
)


@dataclass(frozen=True)
class AlphaTrendMechanismConfig:
    fast_span: int = 8
    slow_span: int = 21
    momentum_spans: tuple[int, ...] = (3, 5, 8, 13, 21, 34)
    slope_lookback: int = 2
    atr_span: int = 14
    pivot_left: int = 2
    pivot_right: int = 2
    structure_stale_bars: int = 20
    fresh_trend_max_age_bars: int = 34
    momentum_recency_bars: int = 3
    min_trend_age_bars: int = 5
    continuation_cooldown_bars: int = 5
    pullback_lookback_bars: int = 3
    pullback_buffer_atr: float = 0.20

    def validate(self) -> None:
        ints = {
            "fast_span": self.fast_span,
            "slow_span": self.slow_span,
            "slope_lookback": self.slope_lookback,
            "atr_span": self.atr_span,
            "pivot_left": self.pivot_left,
            "pivot_right": self.pivot_right,
            "structure_stale_bars": self.structure_stale_bars,
            "fresh_trend_max_age_bars": self.fresh_trend_max_age_bars,
            "momentum_recency_bars": self.momentum_recency_bars,
            "min_trend_age_bars": self.min_trend_age_bars,
            "continuation_cooldown_bars": self.continuation_cooldown_bars,
            "pullback_lookback_bars": self.pullback_lookback_bars,
        }
        bad = [name for name, value in ints.items() if int(value) < 1]
        if bad:
            raise ValueError(f"positive integer parameters required: {bad}")
        if len(self.momentum_spans) != 6:
            raise ValueError("momentum_spans must contain exactly six spans")
        if tuple(sorted(set(self.momentum_spans))) != self.momentum_spans:
            raise ValueError("momentum_spans must be strictly increasing")
        if self.fast_span >= self.slow_span:
            raise ValueError("fast_span must be < slow_span")
        if self.pullback_buffer_atr < 0:
            raise ValueError("pullback_buffer_atr must be >= 0")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_features(
    frame: pd.DataFrame,
    config: AlphaTrendMechanismConfig | None = None,
) -> pd.DataFrame:
    """Build causally available intraday features and event signals.

    Feature state resets at each session. Confirmed pivots are written on the
    confirmation bar, never backfilled onto the pivot bar.
    """
    cfg = config or AlphaTrendMechanismConfig()
    cfg.validate()
    df = _prepare(frame)
    parts: list[pd.DataFrame] = []
    for _, group in df.groupby("session_date", sort=False):
        parts.append(_build_session(group.copy(), cfg))
    out = pd.concat(parts, axis=0).sort_values("_row_order")
    out = out.drop(columns=["_row_order"])
    out.attrs["mechanism"] = "ALPHATREND_INSPIRED_TRANSPARENT_V1"
    out.attrs["proprietary_equivalence_claimed"] = False
    out.attrs["research_only"] = True
    out.attrs["config"] = cfg.to_dict()
    return out.reset_index(drop=True)


def add_forward_labels(
    frame: pd.DataFrame,
    horizons: Iterable[int] = (5, 10, 15, 20, 30),
) -> pd.DataFrame:
    """Add session-contained forward returns and high/low excursions."""
    df = _prepare(frame)
    hs = tuple(sorted({int(h) for h in horizons}))
    if not hs or hs[0] < 1:
        raise ValueError("horizons must contain positive integers")

    parts: list[pd.DataFrame] = []
    for _, group in df.groupby("session_date", sort=False):
        g = group.copy()
        for horizon in hs:
            future_close = g["close"].shift(-horizon)
            g[f"fwd_ret_{horizon}_bps"] = (future_close / g["close"] - 1.0) * 10000.0

            highs = pd.concat(
                [g["high"].shift(-step) for step in range(1, horizon + 1)],
                axis=1,
            )
            lows = pd.concat(
                [g["low"].shift(-step) for step in range(1, horizon + 1)],
                axis=1,
            )
            future_high = highs.max(axis=1, skipna=False)
            future_low = lows.min(axis=1, skipna=False)
            g[f"fwd_high_{horizon}_bps"] = (future_high / g["close"] - 1.0) * 10000.0
            g[f"fwd_low_{horizon}_bps"] = (future_low / g["close"] - 1.0) * 10000.0
        parts.append(g)

    out = pd.concat(parts, axis=0).sort_values("_row_order").drop(columns=["_row_order"])
    return out.reset_index(drop=True)


def build_negative_controls(
    frame: pd.DataFrame,
    signal_column: str,
    *,
    shift_bars: int = 17,
) -> pd.DataFrame:
    """Create deterministic sign-inversion and same-session time-shift controls."""
    if signal_column not in frame.columns:
        raise KeyError(signal_column)
    if shift_bars < 1:
        raise ValueError("shift_bars must be >= 1")
    df = _prepare(frame)
    signal = pd.to_numeric(df[signal_column], errors="coerce").fillna(0).astype(int)
    df[f"{signal_column}__control_inverse"] = -signal
    df[f"{signal_column}__control_shift_{shift_bars}"] = (
        signal.groupby(df["session_date"], sort=False).shift(shift_bars).fillna(0).astype(int)
    )
    return df.sort_values("_row_order").drop(columns=["_row_order"]).reset_index(drop=True)


def evaluate_signal(
    frame: pd.DataFrame,
    signal_column: str,
    horizons: Iterable[int] = (5, 10, 15, 20, 30),
) -> dict[str, object]:
    """Summarize directional outcomes without making an option-P&L claim."""
    if signal_column not in frame.columns:
        raise KeyError(signal_column)
    signal = pd.to_numeric(frame[signal_column], errors="coerce").fillna(0).astype(int)
    events = frame.loc[signal.ne(0)].copy()
    event_signal = signal.loc[signal.ne(0)]

    result: dict[str, object] = {
        "signal": signal_column,
        "events": int(len(events)),
        "long_events": int((event_signal > 0).sum()),
        "short_events": int((event_signal < 0).sum()),
        "option_pnl_claimed": False,
        "horizons": {},
    }
    for horizon in tuple(sorted({int(h) for h in horizons})):
        ret_col = f"fwd_ret_{horizon}_bps"
        hi_col = f"fwd_high_{horizon}_bps"
        lo_col = f"fwd_low_{horizon}_bps"
        missing = [name for name in (ret_col, hi_col, lo_col) if name not in frame.columns]
        if missing:
            raise KeyError(f"missing forward label columns: {missing}")

        valid = events[ret_col].notna() & events[hi_col].notna() & events[lo_col].notna()
        e = events.loc[valid]
        s = event_signal.loc[e.index]
        directional_ret = s * e[ret_col]
        directional_mfe = e[hi_col].where(s > 0, -e[lo_col])
        directional_mae = e[lo_col].where(s > 0, -e[hi_col])

        result["horizons"][str(horizon)] = {
            "n": int(len(e)),
            "mean_directional_bps": _finite_or_none(directional_ret.mean()),
            "median_directional_bps": _finite_or_none(directional_ret.median()),
            "hit_rate": _finite_or_none((directional_ret > 0).mean()),
            "mean_mfe_bps": _finite_or_none(directional_mfe.mean()),
            "mean_mae_bps": _finite_or_none(directional_mae.mean()),
        }
    return result


def _build_session(g: pd.DataFrame, cfg: AlphaTrendMechanismConfig) -> pd.DataFrame:
    close = g["close"]
    high = g["high"]
    low = g["low"]

    prev_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    g["atr"] = true_range.ewm(span=cfg.atr_span, adjust=False, min_periods=cfg.atr_span).mean()
    g["ema_fast"] = close.ewm(span=cfg.fast_span, adjust=False, min_periods=cfg.fast_span).mean()
    g["ema_slow"] = close.ewm(span=cfg.slow_span, adjust=False, min_periods=cfg.slow_span).mean()

    fast_slope = g["ema_fast"] - g["ema_fast"].shift(cfg.slope_lookback)
    trend = pd.Series(NEUTRAL, index=g.index, dtype="int64")
    bull_trend = (g["ema_fast"] > g["ema_slow"]) & (fast_slope > 0) & (close > g["ema_slow"])
    bear_trend = (g["ema_fast"] < g["ema_slow"]) & (fast_slope < 0) & (close < g["ema_slow"])
    trend.loc[bull_trend] = BULLISH
    trend.loc[bear_trend] = BEARISH
    g["trend_state"] = trend
    g["trend_age"] = _state_age(trend)

    momentum_emas: list[str] = []
    momentum_slopes: list[pd.Series] = []
    for span in cfg.momentum_spans:
        name = f"momentum_ema_{span}"
        g[name] = close.ewm(span=span, adjust=False, min_periods=span).mean()
        momentum_emas.append(name)
        momentum_slopes.append(g[name] - g[name].shift(cfg.slope_lookback))

    bull_stack = pd.Series(True, index=g.index)
    bear_stack = pd.Series(True, index=g.index)
    for left, right in zip(momentum_emas[:-1], momentum_emas[1:]):
        bull_stack &= g[left] > g[right]
        bear_stack &= g[left] < g[right]
    bull_slopes = pd.Series(True, index=g.index)
    bear_slopes = pd.Series(True, index=g.index)
    for slope in momentum_slopes:
        bull_slopes &= slope > 0
        bear_slopes &= slope < 0

    momentum = pd.Series(NEUTRAL, index=g.index, dtype="int64")
    momentum.loc[bull_stack & bull_slopes] = BULLISH
    momentum.loc[bear_stack & bear_slopes] = BEARISH
    g["momentum_state"] = momentum
    g["momentum_age"] = _state_age(momentum)

    structure = _confirmed_structure(g, cfg)
    g["structure_state"] = structure["state"]
    g["last_swing_high"] = structure["swing_high"]
    g["last_swing_low"] = structure["swing_low"]
    g["structure_label"] = structure["label"]

    trend_event = trend.where(trend.ne(0) & trend.ne(trend.shift(1)), 0)
    g["signal_trend_only"] = trend_event.astype(int)
    g["signal_trend_structure"] = trend_event.where(structure["state"].eq(trend_event), 0).astype(int)
    g["signal_trend_momentum"] = trend_event.where(momentum.eq(trend_event), 0).astype(int)

    aligned = trend.ne(0) & trend.eq(momentum) & trend.eq(structure["state"])
    fresh = (
        aligned
        & g["trend_age"].le(cfg.fresh_trend_max_age_bars)
        & g["momentum_age"].le(cfg.momentum_recency_bars)
    )
    fresh_pulse = fresh & ~fresh.shift(1, fill_value=False)
    g["signal_full_fresh"] = trend.where(fresh_pulse, 0).astype(int)

    ribbon_names = [f"momentum_ema_{span}" for span in cfg.momentum_spans]
    ribbon_upper = g[ribbon_names].max(axis=1)
    ribbon_lower = g[ribbon_names].min(axis=1)
    buffer_ = cfg.pullback_buffer_atr * g["atr"]
    pullback_touch = (low <= ribbon_upper + buffer_) & (high >= ribbon_lower - buffer_)
    recent_touch = (
        pullback_touch.shift(1, fill_value=False)
        .rolling(cfg.pullback_lookback_bars, min_periods=1)
        .max()
        .astype(bool)
    )
    established = g["trend_age"].ge(cfg.min_trend_age_bars)
    bull_rebreak = close.gt(high.shift(1)) & close.gt(g[momentum_emas[0]])
    bear_rebreak = close.lt(low.shift(1)) & close.lt(g[momentum_emas[0]])
    cont = (
        aligned
        & established
        & recent_touch
        & ((trend.eq(BULLISH) & bull_rebreak) | (trend.eq(BEARISH) & bear_rebreak))
        & ~fresh
    )
    cont_pulse = cont & ~cont.shift(1, fill_value=False)
    raw_continuation = trend.where(cont_pulse, 0).astype(int)
    g["signal_continuation"] = _apply_cooldown(raw_continuation, cfg.continuation_cooldown_bars)

    g["alignment_state"] = trend.where(aligned, 0).astype(int)
    g["research_state"] = g["alignment_state"].map(
        {BULLISH: "BULLISH", BEARISH: "BEARISH", NEUTRAL: "NO_TRADE"}
    )
    return g


def _confirmed_structure(
    g: pd.DataFrame,
    cfg: AlphaTrendMechanismConfig,
) -> dict[str, pd.Series]:
    highs = g["high"].tolist()
    lows = g["low"].tolist()
    index = list(g.index)
    n = len(g)

    states = [NEUTRAL] * n
    labels = ["INSUFFICIENT"] * n
    swing_highs: list[float | None] = [None] * n
    swing_lows: list[float | None] = [None] * n

    prev_high: float | None = None
    last_high: float | None = None
    prev_low: float | None = None
    last_low: float | None = None
    last_high_confirm: int | None = None
    last_low_confirm: int | None = None

    for t in range(n):
        candidate = t - cfg.pivot_right
        if candidate >= cfg.pivot_left:
            lo = candidate - cfg.pivot_left
            hi = candidate + cfg.pivot_right + 1
            if hi <= n:
                h = highs[candidate]
                l = lows[candidate]
                if h >= max(highs[lo:hi]):
                    prev_high, last_high = last_high, h
                    last_high_confirm = t
                if l <= min(lows[lo:hi]):
                    prev_low, last_low = last_low, l
                    last_low_confirm = t

        swing_highs[t] = last_high
        swing_lows[t] = last_low
        if None in (prev_high, last_high, prev_low, last_low, last_high_confirm, last_low_confirm):
            continue
        stale = (
            t - int(last_high_confirm) > cfg.structure_stale_bars
            or t - int(last_low_confirm) > cfg.structure_stale_bars
        )
        if stale:
            labels[t] = "STALE"
            continue

        higher_high = float(last_high) > float(prev_high)
        higher_low = float(last_low) > float(prev_low)
        lower_high = float(last_high) < float(prev_high)
        lower_low = float(last_low) < float(prev_low)
        if higher_high and higher_low:
            states[t] = BULLISH
            labels[t] = "HH_HL"
        elif lower_high and lower_low:
            states[t] = BEARISH
            labels[t] = "LH_LL"
        else:
            labels[t] = "MIXED"

    return {
        "state": pd.Series(states, index=index, dtype="int64"),
        "label": pd.Series(labels, index=index, dtype="object"),
        "swing_high": pd.Series(swing_highs, index=index, dtype="float64"),
        "swing_low": pd.Series(swing_lows, index=index, dtype="float64"),
    }


def _apply_cooldown(signal: pd.Series, cooldown_bars: int) -> pd.Series:
    out = pd.Series(0, index=signal.index, dtype="int64")
    last_event = -10**9
    for position, (idx, value) in enumerate(signal.items()):
        value = int(value)
        if value != 0 and position - last_event >= cooldown_bars:
            out.at[idx] = value
            last_event = position
    return out


def _state_age(state: pd.Series) -> pd.Series:
    values = state.tolist()
    ages: list[int] = []
    previous: int | None = None
    age = 0
    for value in values:
        value = int(value)
        if value == previous:
            age += 1
        else:
            age = 1
            previous = value
        ages.append(age)
    return pd.Series(ages, index=state.index, dtype="int64")


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing OHLCV columns: {missing}")
    df = frame.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="raise")
    for column in ("open", "high", "low", "close"):
        df[column] = pd.to_numeric(df[column], errors="raise")
    if "session_date" not in df.columns:
        df["session_date"] = df["timestamp"].dt.date.astype(str)
    else:
        df["session_date"] = df["session_date"].astype(str)
    df["_row_order"] = range(len(df))
    df = df.sort_values(["session_date", "timestamp", "_row_order"]).reset_index(drop=True)
    if df.duplicated(["session_date", "timestamp"]).any():
        raise ValueError("duplicate timestamp within session")
    invalid = (df["high"] < df[["open", "close", "low"]].max(axis=1)) | (
        df["low"] > df[["open", "close", "high"]].min(axis=1)
    )
    if invalid.any():
        raise ValueError("invalid OHLC ordering")
    return df


def _finite_or_none(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


__all__ = [
    "AlphaTrendMechanismConfig",
    "BEARISH",
    "BULLISH",
    "NEUTRAL",
    "SIGNAL_COLUMNS",
    "add_forward_labels",
    "build_features",
    "build_negative_controls",
    "evaluate_signal",
]
