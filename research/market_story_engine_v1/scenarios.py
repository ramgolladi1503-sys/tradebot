from __future__ import annotations

import numpy as np
import pandas as pd


def _timestamps(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-07-01 03:45:00+00:00", periods=n, freq="5min")


def build_scenario(
    kind: str,
    noise_seed: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    n = 24
    timestamps = _timestamps(n)
    rng = np.random.default_rng(noise_seed)
    base = np.array(
        [
            100.0,
            100.1,
            100.0,
            100.2,
            100.1,
            100.25,
            100.2,
            100.3,
            100.28,
            100.35,
            100.32,
            100.38,
            100.34,
            100.40,
            100.37,
            100.42,
            100.39,
            100.43,
            100.41,
            100.44,
            100.42,
            100.45,
            100.43,
            100.46,
        ]
    )
    bullish_kinds = {
        "bull",
        "weak_breadth",
        "weak_option",
        "missing_option",
        "crossed_option",
    }
    if kind in bullish_kinds:
        close = base.copy()
        close[-3:] = [100.62, 100.49, 100.70]
    elif kind == "false_break":
        close = base.copy()
        close[-3:] = [100.62, 100.36, 100.38]
    elif kind == "bear":
        close = 200.0 - base
        close[-3:] = [99.38, 99.51, 99.30]
    else:
        raise ValueError(kind)

    if noise_seed is not None:
        noise = rng.normal(0.0, 0.002, size=n)
        noise[-3:] *= 0.2
        close = close + noise

    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + 0.04
    low = np.minimum(open_, close) - 0.04
    underlying = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
        }
    )

    if kind == "bear":
        weighted_breadth = np.linspace(0.48, 0.30, n)
        equal_breadth = np.linspace(0.47, 0.32, n)
    else:
        weighted_breadth = np.linspace(0.49, 0.72, n)
        equal_breadth = np.linspace(0.50, 0.68, n)
    if kind == "weak_breadth":
        weighted_breadth[:] = 0.49
        equal_breadth[:] = 0.48
    breadth = pd.DataFrame(
        {
            "timestamp": timestamps,
            "weighted_breadth": weighted_breadth,
            "equal_breadth": equal_breadth,
            "top5_concentration": np.full(n, 0.42),
            "sector_agreement": np.full(n, 0.72),
        }
    )

    ce = np.linspace(100.0, 102.0, n)
    pe = np.linspace(100.0, 98.5, n)
    if kind in {"bull", "weak_breadth", "missing_option", "crossed_option"}:
        ce[-3:] = [106.0, 104.5, 112.0]
        pe[-3:] = [96.0, 97.0, 93.0]
    elif kind == "weak_option":
        ce[-3:] = [102.2, 102.1, 102.24]
        pe[-3:] = [98.2, 98.3, 98.1]
    elif kind == "false_break":
        ce[-3:] = [105.0, 100.5, 100.8]
        pe[-3:] = [96.0, 101.0, 100.5]
    elif kind == "bear":
        ce[-3:] = [96.0, 97.0, 93.0]
        pe[-3:] = [106.0, 104.5, 112.0]

    options = pd.DataFrame(
        {
            "timestamp": timestamps,
            "ce_bid": ce * 0.995,
            "ce_ask": ce * 1.005,
            "ce_last": ce,
            "ce_volume": np.full(n, 1000.0),
            "pe_bid": pe * 0.995,
            "pe_ask": pe * 1.005,
            "pe_last": pe,
            "pe_volume": np.full(n, 1000.0),
            "underlying_reference": close,
        }
    )
    if kind == "missing_option":
        options.loc[options.index[-1], ["ce_bid", "ce_ask"]] = np.nan
    if kind == "crossed_option":
        options.loc[options.index[-1], ["ce_bid", "ce_ask"]] = [105.0, 104.0]
    return underlying, breadth, options
