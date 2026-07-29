from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import run_inventory_absorption_transition_v1 as campaign


def _frame() -> pd.DataFrame:
    timestamps = pd.to_datetime(
        ["2026-01-01T04:30:00Z", "2026-01-01T04:35:00Z", "2026-01-01T04:40:00Z", "2026-01-01T05:00:00Z"],
        utc=True,
    )
    return pd.DataFrame(
        {
            "expired_instrument_key": ["A"] * 4,
            "session_id": ["2026-01-01"] * 4,
            "timestamp": timestamps,
            "entry_price_next_open": [100.0] * 4,
            "days_to_expiry": [1] * 4,
            "surface_count": [5] * 4,
            "volume": [100] * 4,
            "previous_return": [-10.0] * 4,
            "mirror_return": [5.0] * 4,
            "mechanism_score": [4.0, 3.0, 2.0, 1.0],
            "option_type": ["CE"] * 4,
            "expiry_id": ["2026-01-02"] * 4,
            "strike": [24000.0] * 4,
            "premium_distance": [50.0] * 4,
        }
    )


def test_onset_only_marks_false_to_true_transition() -> None:
    frame = _frame()
    mask = pd.Series([False, True, True, False], index=frame.index)
    assert campaign._onset(frame, mask).tolist() == [False, True, False, False]


def test_metrics_trim_and_concentration_are_deterministic() -> None:
    trades = pd.DataFrame(
        {
            "session_id": [f"s{i // 2}" for i in range(20)],
            "timestamp": pd.date_range("2026-01-01", periods=20, freq="5min", tz="UTC"),
            "fold_id": [f"fold_{1 + i // 5}" for i in range(20)],
            "net_return_pct": np.linspace(-1.0, 2.0, 20),
            "stress_return_pct": np.linspace(-1.9, 1.1, 20),
        }
    )
    first = campaign.calculate_metrics(trades)
    second = campaign.calculate_metrics(trades)
    assert first == second
    assert first.trades == 20
    assert first.sessions == 10
    assert first.bootstrap_mean_ci_low is not None
    assert first.largest_session_share is not None


def test_oof_gate_requires_more_occurrences() -> None:
    metric = campaign.Metrics(
        trades=59,
        sessions=50,
        profit_factor=2.0,
        mean_return_pct=1.0,
        median_return_pct=0.5,
        win_rate=0.6,
        net_return_pct_sum=59.0,
        remove_top_five_profit_factor=1.5,
        remove_top_three_profit_factor=1.5,
        stress_profit_factor=1.2,
        bootstrap_mean_ci_low=0.1,
        bootstrap_mean_ci_high=2.0,
        positive_folds=4,
        total_folds=4,
        positive_halves=2,
        total_halves=2,
        largest_winner_share=0.1,
        largest_session_share=0.1,
    )
    assert campaign.oof_gate(metric) is False


def test_semantic_hash_is_order_invariant() -> None:
    assert campaign.semantic_hash({"a": 1, "b": 2}) == campaign.semantic_hash({"b": 2, "a": 1})
