from __future__ import annotations

import pandas as pd

from scripts.run_option_surface_transition_discovery_v1 import (
    MECHANISMS,
    _partition_sessions,
    _select_first_signal,
    calculate_metrics,
)


def test_mechanism_budget_is_exactly_twelve() -> None:
    assert len(MECHANISMS) == 12
    assert len(set(MECHANISMS)) == 12


def test_partition_keeps_latest_quarter_as_holdout() -> None:
    frame = pd.DataFrame({"session_id": [f"2026-01-{day:02d}" for day in range(1, 21)]})
    partitions = _partition_sessions(frame)
    assert len(partitions["development"]) == 12
    assert len(partitions["validation"]) == 3
    assert len(partitions["holdout"]) == 5
    assert partitions["holdout"] == [f"2026-01-{day:02d}" for day in range(16, 21)]


def test_tail_concentration_is_exposed_by_remove_top_two() -> None:
    returns = [30.0, 25.0, 1.0, -4.0, -4.0, -4.0, -4.0, -4.0]
    frame = pd.DataFrame(
        {
            "session_id": [f"s{index}" for index in range(len(returns))],
            "timestamp": pd.date_range("2026-01-01", periods=len(returns), freq="D", tz="UTC"),
            "net_return_pct": returns,
            "stress_return_pct": [value - 0.9 for value in returns],
        }
    )
    metrics = calculate_metrics(frame)
    assert metrics.profit_factor is not None and metrics.profit_factor > 1.0
    assert metrics.remove_top_two_profit_factor is not None
    assert metrics.remove_top_two_profit_factor < 1.0
    assert metrics.largest_winner_share is not None and metrics.largest_winner_share > 0.5


def test_first_signal_is_one_per_session_at_earliest_timestamp() -> None:
    frame = pd.DataFrame(
        {
            "session_id": ["a", "a", "a", "b"],
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01 05:00:00Z",
                    "2026-01-01 05:00:00Z",
                    "2026-01-01 05:05:00Z",
                    "2026-01-02 05:00:00Z",
                ]
            ),
            "entry_price_next_open": [140.0, 151.0, 150.0, 155.0],
            "minute_of_day": [600, 600, 605, 600],
            "days_to_expiry": [1, 1, 1, 1],
            "surface_count": [4, 4, 4, 4],
            "volume": [100, 100, 100, 100],
            "previous_return": [0.1, 0.1, 0.1, 0.1],
            "return_acceleration": [1.0, 2.0, 100.0, 1.0],
            "option_asymmetry": [1.0, 2.0, 100.0, 1.0],
            "breadth_delta": [0.1, 0.2, 1.0, 0.1],
            "prior_5m_volume_ratio": [1.0, 1.2, 3.0, 1.0],
            "directional_mass_shift": [0.0, 0.0, 20.0, 0.0],
            "expired_instrument_key": ["one", "two", "late", "four"],
        }
    )
    selected = _select_first_signal(
        frame,
        pd.Series([True, True, True, True]),
        "test_mechanism",
        ["a", "b"],
    )
    assert selected["session_id"].tolist() == ["a", "b"]
    assert selected.loc[selected["session_id"].eq("a"), "expired_instrument_key"].item() == "two"
    assert selected.loc[selected["session_id"].eq("a"), "timestamp"].item() == pd.Timestamp(
        "2026-01-01 05:00:00Z"
    )
