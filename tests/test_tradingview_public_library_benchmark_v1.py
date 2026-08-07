from __future__ import annotations

import numpy as np
import pandas as pd

from research.tradingview_public_library_benchmark_v1 import benchmark as B


def _record(title: str, description: str, primitives: list[str], incompat: list[str] | None = None):
    return {
        "script_id": "x",
        "title": title,
        "description": description,
        "primitives": primitives,
        "incompatibilities": incompat or [],
        "fetch_status": "OK",
    }


def test_mapping_is_frozen_from_description_not_outcomes() -> None:
    spec, status = B.map_record(_record(
        "Advanced Bollinger Bands Signals",
        "Buy when price crosses back above the lower Bollinger Band; sell when price crosses back below the upper band.",
        ["BOLLINGER"],
    ))
    assert status == "TESTABLE_CANONICAL_MECHANISM"
    assert spec is not None
    assert spec.family == "BOLLINGER_REENTRY"
    assert spec.signature == "BOLLINGER_REENTRY::length=20,sigma=2"


def test_volume_script_is_not_faked_on_aeron_ohlc() -> None:
    spec, status = B.map_record(_record(
        "EMA RSI Volume Strategy",
        "Buy on EMA crossover with RSI confirmation and volume above average.",
        ["EMA", "RSI", "VOLUME"],
    ))
    assert spec is None
    assert status == "INDEPENDENT_DATA_MISSING_VOLUME"


def test_options_script_is_data_incompatible() -> None:
    spec, status = B.map_record(_record(
        "Gamma options matrix",
        "Uses option chain gamma and implied volatility.",
        ["TREND"],
        ["OPTIONS_OR_GREEKS"],
    ))
    assert spec is None
    assert status == "INDEPENDENT_DATA_INCOMPATIBLE"


def test_ema_lengths_are_description_derived_before_outcomes() -> None:
    spec, _ = B.map_record(_record(
        "EMA 20/50 crossover",
        "Trend strategy using EMA 20/50 crossover.",
        ["EMA", "TREND"],
    ))
    assert spec is not None
    assert spec.family == "EMA_CROSS"
    assert spec.param_dict() == {"fast": 20.0, "slow": 50.0}


def _two_session_ohlc() -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2024-01-01 09:15")
    for day in range(6):
        for i in range(75):
            ts = base + pd.Timedelta(days=day, minutes=5 * i)
            price = 100.0 + day * 0.3 + i * 0.02 + np.sin((day * 75 + i) / 7) * 0.4
            rows.append({
                "timestamp": ts,
                "symbol": "NIFTY",
                "session_date": ts.strftime("%Y-%m-%d"),
                "open": price - 0.03,
                "high": price + 0.08,
                "low": price - 0.08,
                "close": price,
            })
    return pd.DataFrame(rows)


def test_feature_prefix_is_causal() -> None:
    raw = _two_session_ohlc()
    f1 = B.build_features(raw)
    checkpoint = 250
    original = f1.loc[checkpoint, ["ema20", "rsi14", "z20", "reg_slope50"]].astype(float).to_numpy()

    changed = raw.copy()
    changed.loc[changed.index > checkpoint + 20, ["open", "high", "low", "close"]] *= 10.0
    f2 = B.build_features(changed)
    mutated = f2.loc[checkpoint, ["ema20", "rsi14", "z20", "reg_slope50"]].astype(float).to_numpy()
    assert np.allclose(original, mutated, equal_nan=True)


def test_first_signal_per_session_is_deterministic() -> None:
    raw = _two_session_ohlc()
    frame = B.build_features(raw)
    spec = B.MechanismSpec("PRICE_EMA_TREND", (("length", 20.0),), "test")
    a = B.first_signals(frame, "NIFTY", spec)
    b = B.first_signals(frame, "NIFTY", spec)
    assert a == b
    assert all(direction in {-1, 1} for _, direction in a.values())


def test_holdout_not_scored_without_robust_survivor() -> None:
    raw = _two_session_ohlc()
    frame = B.build_features(raw)
    frame["split"] = "holdout"
    spec = B.MechanismSpec("PRICE_EMA_TREND", (("length", 20.0),), "test")
    result = B.holdout_test(
        frame,
        [spec],
        {"records": []},
        {"survivor_hypothesis_ids": []},
        "NIFTY",
    )
    assert result["holdout_scored"] is False
    assert result["tested"] == []
