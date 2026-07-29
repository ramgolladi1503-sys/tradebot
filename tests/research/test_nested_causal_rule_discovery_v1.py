from __future__ import annotations

from scripts import run_nested_causal_rule_discovery_v1 as campaign


def test_leaf_gate_requires_inner_stability_and_large_leaf() -> None:
    stats = {
        "rows": 500,
        "sessions": 80,
        "profit_factor_1pct": 1.3,
        "mean_1pct": 0.4,
        "median_1pct": 0.1,
        "trim_top_20_profit_factor_1pct": 1.1,
        "inner_blocks": 3,
        "positive_inner_blocks": 2,
        "largest_winner_share": 0.04,
    }
    assert campaign.leaf_gate(stats) is True
    stats["positive_inner_blocks"] = 1
    assert campaign.leaf_gate(stats) is False


def test_feature_set_contains_only_causal_inputs() -> None:
    forbidden = {
        "gross_return_pct",
        "net_return_pct",
        "stress_return_pct",
        "forward_close_change_points",
        "forward_mfe_points",
        "forward_mae_points",
    }
    assert forbidden.isdisjoint(campaign.FEATURES)


def test_inner_blocks_are_chronological_and_complete() -> None:
    sessions = [f"s{i}" for i in range(9)]
    blocks = campaign.inner_blocks(sessions)
    assert blocks == [sessions[:3], sessions[3:6], sessions[6:]]
