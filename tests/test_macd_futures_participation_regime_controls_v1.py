from __future__ import annotations

import pandas as pd

from research.macd_futures_participation_regime_v1.controls import (
    condition_removal_control,
    session_cluster_sign_flip_control,
)


def _strong_interaction() -> pd.DataFrame:
    rows = []
    sessions = pd.date_range("2025-01-02", periods=40, freq="7D")
    for i, day in enumerate(sessions):
        active = i % 2 == 0
        rows.append(
            {
                "signal_trade_id": f"S{i:03d}",
                "signal_session_date": str(day.date()),
                "signal_state": active,
                "delta_net_6bps": 10.0 if active else 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_condition_removal_requires_state_to_add_point_estimate_information():
    result = condition_removal_control(_strong_interaction())
    assert result["active_delta_net_6bps"] == 10.0
    assert result["inactive_delta_net_6bps"] == 1.0
    assert result["interaction_lift_bps"] == 9.0
    assert result["condition_adds_point_estimate_information"] is True


def test_session_cluster_sign_flip_detects_strong_positive_active_delta():
    result = session_cluster_sign_flip_control(
        _strong_interaction(), reps=4000, seed=20260908
    )
    assert result["active_signal_sessions"] == 20
    assert result["observed_active_session_mean_delta_bps"] == 10.0
    assert result["empirical_p_one_sided"] < 0.05
    assert result["passes_nominal_0_05"] is True
