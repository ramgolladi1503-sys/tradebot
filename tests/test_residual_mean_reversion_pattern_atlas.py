from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.residual_liquidity_exhaustion_mr_v2.pattern_atlas import (
    PatternAtlasContract,
    build_residual_panel,
    build_segment_metrics,
    canonicalize_symbol,
    extract_residual_events,
    permutation_control,
    resample_completed_bars,
)


def _frame(closes: list[float], *, start: str = "2026-01-02 09:15") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(closes), freq="5min")
    close = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": np.arange(len(close), dtype=float) + 1.0,
        }
    )


def test_symbol_aliases_are_explicit_and_unknown_symbols_fail() -> None:
    assert canonicalize_symbol("NSE_INDEX|Nifty 50") == "NIFTY"
    assert canonicalize_symbol("NSE_INDEX|Nifty Bank") == "BANKNIFTY"
    assert canonicalize_symbol("BSE_INDEX|SENSEX") == "SENSEX"
    with pytest.raises(ValueError, match="unsupported atlas symbol"):
        canonicalize_symbol("RANDOM")


def test_resample_uses_completed_bucket_and_records_known_at() -> None:
    minute_index = pd.date_range("2026-01-02 09:15", periods=10, freq="1min")
    frame = pd.DataFrame(
        {
            "timestamp": minute_index,
            "open": np.arange(10, dtype=float) + 100.0,
            "high": np.arange(10, dtype=float) + 101.0,
            "low": np.arange(10, dtype=float) + 99.0,
            "close": np.arange(10, dtype=float) + 100.5,
            "volume": 1.0,
        }
    )
    bars = resample_completed_bars(frame, bar_minutes=5)
    assert bars["timestamp"].tolist() == [
        pd.Timestamp("2026-01-02 09:15"),
        pd.Timestamp("2026-01-02 09:20"),
    ]
    assert bars["known_at"].tolist() == [
        pd.Timestamp("2026-01-02 09:20"),
        pd.Timestamp("2026-01-02 09:25"),
    ]
    assert bars.loc[0, "open"] == 100.0
    assert bars.loc[0, "close"] == 104.5
    assert bars.loc[0, "source_rows"] == 5


def test_current_shock_does_not_enter_its_own_volatility_normalizer() -> None:
    contract = PatternAtlasContract(
        volatility_window_bars=4,
        volatility_min_periods=2,
        residual_threshold=1.0,
        permutation_count=20,
    )
    nifty = _frame([100.0, 100.1, 100.0, 100.2, 100.1, 110.0, 110.1])
    bank = _frame([200.0, 200.2, 200.0, 200.4, 200.2, 200.3, 200.4])
    panel = build_residual_panel({"NIFTY": nifty, "BANKNIFTY": bank}, contract=contract)
    shock_time = pd.Timestamp("2026-01-02 09:40")
    prior_returns = panel.loc[: pd.Timestamp("2026-01-02 09:35"), "NIFTY__log_return"].dropna()
    expected = prior_returns.tail(4).std(ddof=1)
    assert panel.loc[shock_time, "NIFTY__causal_vol"] == pytest.approx(expected)
    assert abs(panel.loc[shock_time, "NIFTY__return_z"]) > 10


def test_event_confirmation_uses_only_the_immediate_next_completed_bar() -> None:
    contract = PatternAtlasContract(
        volatility_window_bars=4,
        volatility_min_periods=2,
        residual_threshold=1.0,
        contraction_ratio=0.6,
        max_extension_fraction=0.5,
        horizons_minutes=(5, 10),
        permutation_count=20,
    )
    nifty = _frame(
        [100.0, 100.1, 100.0, 100.2, 100.1, 105.0, 104.8, 104.0, 103.8, 103.5]
    )
    bank = _frame(
        [200.0, 200.2, 200.0, 200.4, 200.2, 200.3, 200.3, 200.3, 200.3, 200.3]
    )
    panel = build_residual_panel({"NIFTY": nifty, "BANKNIFTY": bank}, contract=contract)
    events = extract_residual_events(panel, contract=contract)
    event = events.loc[
        (events["target_symbol"] == "NIFTY")
        & (events["event_time"] == "2026-01-02T09:40:00")
    ].iloc[0]
    assert event["event_known_at"] == "2026-01-02T09:45:00"
    assert event["confirmation_time"] == "2026-01-02T09:45:00"
    assert bool(event["residual_contracted"])
    assert bool(event["continuation_failed"])
    assert bool(event["exhaustion_confirmed"])
    assert event["confirmed_reversion_bps_5m"] > 0


def test_segment_metrics_and_permutation_control_are_deterministic() -> None:
    events = pd.DataFrame(
        {
            "target_symbol": ["NIFTY", "NIFTY", "BANKNIFTY", "BANKNIFTY"],
            "event_side": ["UP_SHOCK", "DOWN_SHOCK", "UP_SHOCK", "DOWN_SHOCK"],
            "time_bucket": ["MORNING_1000_1200"] * 4,
            "magnitude_bucket": ["RZ_2_2P5"] * 4,
            "volatility_bucket": ["VOL_5_10BPS"] * 4,
            "calendar_period": ["2026H1"] * 4,
            "exhaustion_confirmed": [True, False, True, False],
            "residual_z": [2.1, -2.2, 2.3, -2.4],
            "shock_sign": [1, -1, 1, -1],
            "raw_mfe_bps_60m": [20.0, 10.0, 30.0, 5.0],
            "raw_mae_bps_60m": [5.0, 15.0, 4.0, 20.0],
            "raw_reversion_bps_5m": [4.0, -1.0, 6.0, -2.0],
            "confirmed_reversion_bps_5m": [5.0, 0.0, 7.0, 0.0],
            "raw_reversion_bps_15m": [8.0, -2.0, 10.0, -3.0],
            "confirmed_reversion_bps_15m": [9.0, 0.0, 11.0, 0.0],
        }
    )
    contract = PatternAtlasContract(horizons_minutes=(5, 15), permutation_count=50)
    metrics = build_segment_metrics(events, contract=contract)
    overall = metrics.loc[metrics["dimension"] == "overall"].iloc[0]
    assert overall["event_count"] == 4
    assert overall["raw_mean_reversion_bps_15m"] == pytest.approx(3.25)

    first = permutation_control(events, horizon_minutes=15, contract=contract)
    second = permutation_control(events, horizon_minutes=15, contract=contract)
    assert first == second
    assert first["classification"] == "DIRECTION_PERMUTATION_CONTROL"
    assert 0.0 < first["one_sided_p_value"] <= 1.0


def test_duplicate_timestamps_fail_closed() -> None:
    frame = _frame([100.0, 101.0, 102.0])
    frame.loc[2, "timestamp"] = frame.loc[1, "timestamp"]
    with pytest.raises(ValueError, match="duplicate timestamps"):
        resample_completed_bars(frame)
