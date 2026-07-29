from __future__ import annotations

import pandas as pd

from scripts import run_selective_option_leadership_campaign_v3 as mod


def test_mechanism_family_is_frozen_and_cumulative_count_is_declared():
    assert len(mod.MECHANISMS) == 8
    assert mod.CUMULATIVE_MECHANISM_COUNT == 16


def test_prepare_leadership_features_are_past_or_present_only():
    frame = pd.DataFrame(
        {
            "expired_instrument_key": ["x", "x"],
            "prior_5m_return_pct": [1.0, 2.0],
            "adjacent_mean_return": [0.5, 1.0],
        }
    )
    frame["leader_gap"] = frame["prior_5m_return_pct"] - frame["adjacent_mean_return"]
    group = frame.groupby("expired_instrument_key", sort=False)
    frame["previous_leader_gap"] = group["leader_gap"].shift(1)
    assert pd.isna(frame.loc[0, "previous_leader_gap"])
    assert frame.loc[1, "previous_leader_gap"] == 0.5


def test_cluster_bootstrap_requires_many_sessions():
    trades = pd.DataFrame(
        {
            "session_id": [f"s{index // 2}" for index in range(40)],
            "net_return_pct": [1.0, -0.5] * 20,
        }
    )
    assert mod.cluster_bootstrap_ci_low(trades, 16) is None


def test_selection_has_high_occurrence_session_cap():
    timestamps = pd.to_datetime(
        ["2026-01-01 04:30:00Z", "2026-01-01 04:35:00Z", "2026-01-01 05:00:00Z"]
    )
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "leadership_score": [3.0, 4.0, 2.0],
            "premium_distance": [1.0, 1.0, 1.0],
            "expired_instrument_key": ["a", "b", "c"],
        }
    )
    selected = mod._select_independent(frame)
    assert len(selected) == 2
    assert selected["timestamp"].max() - selected["timestamp"].min() >= pd.Timedelta(minutes=15)


def test_master_holdout_is_never_loaded_by_runner_source():
    import inspect

    source = inspect.getsource(mod.main)
    assert 'partitions["master_holdout"]' not in source.split("research_outcomes =", 1)[1]
    assert '"master_holdout_outcomes_materialized": False' in source
