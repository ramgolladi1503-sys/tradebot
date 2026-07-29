from __future__ import annotations

from scripts import run_barrier_path_causal_discovery_v1 as campaign


def test_frozen_barrier_has_two_to_one_reward_risk() -> None:
    assert campaign.TARGET_PCT == 10.0
    assert campaign.STOP_PCT == 5.0
    assert campaign.MAX_HOLD_MINUTES == 10


def test_leaf_gate_allows_positive_bounded_path_leaf() -> None:
    stats = {
        "rows": 500,
        "sessions": 40,
        "minimum_required_sessions": 35,
        "profit_factor_1pct": 1.3,
        "mean_1pct": 0.4,
        "target_hit_rate": 0.42,
        "trim_top_20_profit_factor_1pct": 1.1,
        "inner_blocks": 3,
        "positive_inner_blocks": 2,
        "largest_winner_share": 0.02,
    }
    assert campaign.leaf_gate(stats) is True
    stats["target_hit_rate"] = 0.30
    assert campaign.leaf_gate(stats) is False


def test_barrier_features_exclude_outcomes() -> None:
    forbidden = {
        "gross_return_pct",
        "net_return_pct",
        "stress_return_pct",
        "barrier_exit_reason",
        "barrier_exit_minute",
    }
    assert forbidden.isdisjoint(campaign.nested.FEATURES)
