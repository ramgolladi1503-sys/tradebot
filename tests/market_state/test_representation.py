from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

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


def test_contract_contains_required_families_and_causal_timestamp_semantics() -> None:
    contract = state_contract()
    assert contract["timestamp_semantics"] == "all states at row t use row t and earlier completed bars only"
    assert {
        "trend",
        "compression_expansion",
        "balance_imbalance",
        "acceptance_rejection",
        "participation",
        "option_responsiveness",
        "absorption_exhaustion_proxies",
        "quality",
    }.issubset(contract["families"])


def test_strict_uptrend_produces_directionally_correct_state() -> None:
    frame = _sample_frame()
    result = build_market_state_frame(frame)
    mature = result.iloc[-1]

    assert mature["trend_return_short"] > 0
    assert mature["trend_return_medium"] > 0
    assert mature["trend_slope_medium"] > 0
    assert mature["trend_path_efficiency"] > 0.90
    assert mature["trend_directional_ratio"] > 0.75
    assert mature["trend_vwap_residence"] > 0.75
    assert mature["directional_efficiency_signed"] > 0
    assert mature["above_vwap_dwell"] == pytest.approx(1.0)
    assert mature["below_vwap_dwell"] == pytest.approx(0.0)


def test_option_response_is_measured_from_exact_input_not_fabricated() -> None:
    frame = _sample_frame()
    result = build_market_state_frame(frame)
    mature = result.iloc[-1]

    expected_option_return = frame["option_close"].iloc[-1] / frame["option_close"].iloc[-6] - 1.0
    expected_underlying_return = frame["close"].iloc[-1] / frame["close"].iloc[-6] - 1.0
    assert mature["option_return_short"] == pytest.approx(expected_option_return)
    assert mature["option_elasticity_short"] == pytest.approx(expected_option_return / expected_underlying_return)
    assert mature["option_response_consistency"] == pytest.approx(1.0)
    assert mature["option_observable"] == 1


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


def test_session_boundary_resets_all_rolling_state() -> None:
    first = _sample_frame(45)
    second = _sample_frame(45).copy()
    second["timestamp"] = second["timestamp"] + pd.Timedelta(days=1)
    second["session_date"] = "2026-01-06"
    second[["open", "high", "low", "close"]] += 5000

    combined = build_market_state_frame(pd.concat([first, second], ignore_index=True))
    second_only = build_market_state_frame(second)
    state_columns = [name for family in state_contract()["families"].values() for name in family]
    observed_second = combined[combined["session_date"] == "2026-01-06"].reset_index(drop=True)

    pd.testing.assert_frame_equal(
        observed_second[state_columns],
        second_only[state_columns],
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
    assert result["state_reliability"].max() <= 0.75


def test_missing_required_columns_fail_closed() -> None:
    frame = _sample_frame().drop(columns=["high"])
    with pytest.raises(ValueError, match="high"):
        build_market_state_frame(frame)
