from __future__ import annotations

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_post_opening_boosted_forward_validation_v1 as campaign


def test_gate_begins_at_ten_am_ist() -> None:
    assert campaign.START_MINUTE_IST == 600


def test_certification_requires_occurrence() -> None:
    metric = common.Metrics(
        trades=24, sessions=24, profit_factor=2.0, mean_return_pct=1.0,
        median_return_pct=0.5, win_rate=0.6, net_return_pct_sum=24.0,
        remove_top_five_profit_factor=1.5, remove_top_three_profit_factor=1.5,
        stress_profit_factor=1.2, bootstrap_mean_ci_low=0.1,
        bootstrap_mean_ci_high=2.0, positive_folds=0, total_folds=0,
        positive_halves=2, total_halves=2, largest_winner_share=0.1,
        largest_session_share=0.1,
    )
    assert campaign.certification_gate(metric) is False


def test_degraded_control_must_have_coverage() -> None:
    primary = common.Metrics(30, 25, 1.5, 1.0, 0.2, 0.6, 30.0, 1.2, 1.2, 1.1, 0.1, 2.0, 0, 0, 2, 2, 0.1, 0.1)
    control = common.Metrics(5, 5, 0.5, -1.0, -1.0, 0.2, -5.0, 0.4, 0.4, 0.3, -2.0, 0.0, 0, 0, 0, 0, 0.1, 0.1)
    assert campaign.degraded(primary, control) is False
