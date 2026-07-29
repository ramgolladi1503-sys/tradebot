from __future__ import annotations

import pandas as pd

from scripts import run_joint_wing_volatility_resolution_v1 as mod


def _metric(**overrides):
    values = dict(
        trades=100,
        sessions=80,
        profit_factor=1.5,
        mean_return_pct=1.5,
        median_return_pct=0.5,
        win_rate=0.6,
        net_return_pct_sum=150.0,
        remove_top_five_profit_factor=1.2,
        stress_profit_factor=1.1,
        bootstrap_mean_ci_low=0.1,
        bootstrap_mean_ci_high=2.5,
        positive_folds=5,
        total_folds=5,
        largest_winner_share=0.1,
        top_five_session_profit_share=0.2,
    )
    values.update(overrides)
    return mod.metrics_mod.Metrics(**values)


def test_mechanisms_and_cumulative_multiplicity_are_frozen():
    assert len(mod.MECHANISMS) == 8
    assert len(set(mod.MECHANISMS)) == 8
    assert mod.CUMULATIVE_MECHANISM_COUNT == 47


def test_joint_wing_features_are_present_time_only():
    frame = pd.DataFrame(
        {
            "prior_5m_return_pct": [2.0],
            "mirror_return": [1.0],
            "option_asymmetry": [1.0],
            "previous_option_asymmetry": [0.25],
            "return_acceleration": [0.5],
            "mirror_acceleration": [-0.1],
            "prior_5m_volume_ratio": [2.0],
            "mirror_volume_ratio": [1.0],
        }
    )
    frame["joint_wing_return"] = frame["prior_5m_return_pct"] + frame["mirror_return"]
    frame["dominance_delta"] = frame["option_asymmetry"] - frame["previous_option_asymmetry"]
    frame["target_vs_mirror_volume"] = frame["prior_5m_volume_ratio"] - frame["mirror_volume_ratio"]
    assert frame.loc[0, "joint_wing_return"] == 3.0
    assert frame.loc[0, "dominance_delta"] == 0.75
    assert frame.loc[0, "target_vs_mirror_volume"] == 1.0


def test_mirror_control_maps_to_opposite_contract_only():
    frame = pd.DataFrame(
        {
            "expired_instrument_key": ["ce"],
            "entry_price_next_open": [120.0],
            "option_type": ["CE"],
            "days_to_expiry": [1],
            "minute_of_day": [600],
            "control_expired_instrument_key": ["pe"],
            "control_entry_price_next_open": [110.0],
            "control_option_type": ["PE"],
            "control_days_to_expiry": [1],
            "control_minute_of_day": [600],
        }
    )
    control = mod.mirror_control_signals(frame)
    assert control.loc[0, "expired_instrument_key"] == "pe"
    assert control.loc[0, "option_type"] == "PE"
    assert frame.loc[0, "expired_instrument_key"] == "ce"


def test_oof_gate_requires_high_occurrence_and_adjusted_ci():
    assert mod.oof_gate(_metric(), 0.1)
    assert not mod.oof_gate(_metric(trades=79), 0.1)
    assert not mod.oof_gate(_metric(sessions=59), 0.1)
    assert not mod.oof_gate(_metric(), -0.01)


def test_controls_must_be_materially_weaker():
    primary = _metric(mean_return_pct=2.0)
    delayed = _metric(trades=80, mean_return_pct=1.5)
    mirror = _metric(trades=80, mean_return_pct=1.0)
    assert mod.control_gate(primary, delayed, mirror)
    assert not mod.control_gate(primary, _metric(trades=80, mean_return_pct=1.9), mirror)
    assert not mod.control_gate(primary, delayed, _metric(trades=80, mean_return_pct=1.7))


def test_master_holdout_is_never_materialized():
    import inspect

    source = inspect.getsource(mod.main)
    assert 'causal["session_id"].isin(partitions["master_holdout"])' not in source
    assert '"master_holdout_outcomes_materialized": False' in source
    assert '"allowed_for_live_execution": False' in source


def test_feature_source_excludes_outcome_columns():
    forbidden = {
        "forward_mfe_points",
        "forward_mae_points",
        "forward_close_change_points",
        "forward_expansion_pct",
        "is_expansion_event",
        "move_cluster_id",
    }
    assert forbidden.isdisjoint(set(mod.surface_mod.CAUSAL_COLUMNS))
