from __future__ import annotations

import numpy as np
import pandas as pd

from core.market_state import MarketStateConfig, build_market_state_frame, state_contract


def _sample_frame(rows: int = 80) -> pd.DataFrame:
    ts = pd.date_range("2026-01-05 09:15", periods=rows, freq="min", tz="Asia/Kolkata")
    close = 24000 + np.linspace(0, 120, rows) + np.sin(np.arange(rows) / 3)
    return pd.DataFrame(
        {
            "timestamp": ts,
            "session_date": "2026-01-05",
            "open": close - 1,
            "high": close + 3,
            "low": close - 3,
            "close": close,
            "volume": np.linspace(1000, 3000, rows),
            "option_close": 150 + np.linspace(0, 35, rows),
            "option_volume": np.linspace(400, 900, rows),
        }
    )


def test_contract_contains_required_families() -> None:
    families = state_contract()["families"]
    assert {
        "trend",
        "compression_expansion",
        "balance_imbalance",
        "acceptance_rejection",
        "participation",
        "option_responsiveness",
        "absorption_exhaustion_proxies",
        "quality",
    }.issubset(families)


def test_output_is_timestamp_sorted_and_has_state_columns() -> None:
    frame = _sample_frame().sample(frac=1.0, random_state=7)
    result = build_market_state_frame(frame)
    assert result["timestamp"].is_monotonic_increasing
    assert "trend_path_efficiency" in result
    assert "option_elasticity_short" in result
    assert "state_reliability" in result
    assert result["state_reliability"].between(0, 1).all()


def test_prefix_invariance_proves_no_future_rows_are_used() -> None:
    frame = _sample_frame()
    full = build_market_state_frame(frame)
    prefix = build_market_state_frame(frame.iloc[:50].copy())
    columns = [name for family in state_contract()["families"].values() for name in family]
    pd.testing.assert_frame_equal(
        full.loc[:49, columns].reset_index(drop=True),
        prefix.loc[:, columns].reset_index(drop=True),
        check_dtype=False,
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


def test_missing_option_data_is_explicit_not_fabricated() -> None:
    frame = _sample_frame().drop(columns=["option_close", "option_volume"])
    result = build_market_state_frame(frame, MarketStateConfig())
    assert result["option_observable"].eq(0).all()
    assert result["option_elasticity_short"].isna().all()


def test_missing_required_columns_fail_closed() -> None:
    frame = _sample_frame().drop(columns=["high"])
    try:
        build_market_state_frame(frame)
    except ValueError as exc:
        assert "high" in str(exc)
    else:
        raise AssertionError("missing required column must fail closed")
