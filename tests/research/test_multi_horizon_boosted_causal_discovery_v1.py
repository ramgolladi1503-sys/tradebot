from __future__ import annotations

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_multi_horizon_boosted_causal_discovery_v1 as campaign


def test_frozen_horizons_and_quantiles() -> None:
    assert campaign.HORIZONS == (5, 10, 15, 20)
    assert campaign.QUANTILES == (0.85, 0.90, 0.95)


def test_feature_set_is_causal() -> None:
    forbidden = {"gross_return_pct", "net_return_pct", "stress_return_pct", "forward_close_change_points"}
    assert forbidden.isdisjoint(campaign.nested.FEATURES)


def test_calibration_gate_requires_occurrence() -> None:
    metric = common.Metrics(
        trades=19, sessions=19, profit_factor=2.0, mean_return_pct=1.0,
        median_return_pct=0.5, win_rate=0.6, net_return_pct_sum=19.0,
        remove_top_five_profit_factor=1.5, remove_top_three_profit_factor=1.5,
        stress_profit_factor=1.2, bootstrap_mean_ci_low=0.1,
        bootstrap_mean_ci_high=2.0, positive_folds=0, total_folds=0,
        positive_halves=2, total_halves=2, largest_winner_share=0.1,
        largest_session_share=0.1,
    )
    assert campaign.calibration_gate(metric) is False


def test_model_is_shallow_and_regularized() -> None:
    model = campaign.new_model(1)
    assert model.max_depth == 3
    assert model.min_samples_leaf == 150
    assert model.l2_regularization == 3.0
