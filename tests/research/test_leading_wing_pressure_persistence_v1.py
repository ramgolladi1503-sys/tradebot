from __future__ import annotations

import pandas as pd

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_leading_wing_pressure_persistence_v1 as campaign


def test_onset_only_emits_false_to_true_transition() -> None:
    frame = pd.DataFrame({"expired_instrument_key": ["A"] * 4})
    mask = pd.Series([False, True, True, False])
    assert campaign.onset(frame, mask).tolist() == [False, True, False, False]


def test_oof_gate_requires_high_occurrence() -> None:
    metric = common.Metrics(
        trades=99,
        sessions=80,
        profit_factor=2.0,
        mean_return_pct=1.0,
        median_return_pct=0.5,
        win_rate=0.6,
        net_return_pct_sum=99.0,
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


def test_control_gate_requires_mirror_rejection_and_delay_degradation() -> None:
    primary = common.Metrics(40, 30, 1.5, 1.0, 0.3, 0.6, 40.0, 1.3, 1.3, 1.2, 0.1, 2.0, 0, 0, 2, 2, 0.1, 0.1)
    mirror = common.Metrics(30, 25, 0.8, -0.5, -0.4, 0.4, -15.0, 0.7, 0.7, 0.6, -1.0, 0.1, 0, 0, 0, 0, 0.1, 0.1)
    delayed = common.Metrics(35, 28, 1.2, 0.4, 0.1, 0.5, 14.0, 1.0, 1.0, 0.9, -0.2, 1.0, 0, 0, 0, 0, 0.1, 0.1)
    assert campaign.control_gate(primary, mirror, delayed) is True


def test_thresholds_are_feature_only() -> None:
    frame = pd.DataFrame(
        {
            "prior_5m_return_pct": [1.0, 2.0],
            "return_acceleration": [0.1, 0.2],
            "prior_5m_volume_ratio": [1.0, 2.0],
            "volume_acceleration": [0.0, 1.0],
            "oi_change_ratio": [0.0, 0.1],
            "option_asymmetry": [1.0, 2.0],
            "breadth_positive": [0.5, 1.0],
            "breadth_acceleration": [0.5, 1.0],
            "breadth_delta": [0.0, 0.5],
            "directional_mass_shift": [0.0, 10.0],
            "surface_return_dispersion": [1.0, 2.0],
        }
    )
    result = campaign.thresholds(frame)
    assert "ret60" in result
    assert "forward_close_change_points" not in result
