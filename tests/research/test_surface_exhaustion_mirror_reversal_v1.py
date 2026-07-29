from __future__ import annotations

import pandas as pd

from scripts import run_surface_exhaustion_mirror_reversal_v1 as mod


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


def test_mechanism_family_is_frozen_and_small():
    assert len(mod.MECHANISMS) == 8
    assert len(set(mod.MECHANISMS)) == 8
    assert mod.CUMULATIVE_MECHANISM_COUNT == 39


def test_target_signal_maps_to_opposite_contract():
    frame = pd.DataFrame(
        {
            "target_expired_instrument_key": ["pe-key"],
            "target_entry_price_next_open": [100.0],
            "target_option_type": ["PE"],
            "target_days_to_expiry": [1],
            "target_minute_of_day": [600],
            "source_expired_instrument_key": ["ce-key"],
            "source_entry_price_next_open": [200.0],
            "source_option_type": ["CE"],
            "source_days_to_expiry": [1],
            "source_minute_of_day": [600],
        }
    )
    target = mod.target_signals(frame)
    source = mod.source_control_signals(frame)
    assert target.loc[0, "expired_instrument_key"] == "pe-key"
    assert target.loc[0, "option_type"] == "PE"
    assert source.loc[0, "expired_instrument_key"] == "ce-key"
    assert source.loc[0, "option_type"] == "CE"


def test_oof_gate_requires_high_occurrence_and_adjusted_ci():
    assert mod.oof_gate(_metric(), 0.1)
    assert not mod.oof_gate(_metric(trades=79), 0.1)
    assert not mod.oof_gate(_metric(sessions=59), 0.1)
    assert not mod.oof_gate(_metric(), -0.01)


def test_control_gate_requires_opposite_option_specificity():
    primary = _metric(mean_return_pct=2.0)
    delayed = _metric(trades=80, mean_return_pct=1.5)
    source = _metric(trades=80, mean_return_pct=1.0)
    assert mod.control_gate(primary, delayed, source)
    assert not mod.control_gate(primary, _metric(trades=80, mean_return_pct=1.9), source)
    assert not mod.control_gate(primary, delayed, _metric(trades=80, mean_return_pct=1.7))


def test_partition_policy_reserves_master_holdout():
    frame = pd.DataFrame({"session_id": [f"s{index:03d}" for index in range(100)]})
    parts = mod.splitmod.partition_sessions(frame)
    assert len(parts["research"]) == 70
    assert len(parts["validation"]) == 15
    assert len(parts["master_holdout"]) == 15
    assert max(parts["research"]) < min(parts["validation"])
    assert max(parts["validation"]) < min(parts["master_holdout"])


def test_master_holdout_is_never_materialized_by_runner():
    import inspect

    source = inspect.getsource(mod.main)
    after_partitions = source.split("partitions =", 1)[1]
    assert 'causal["session_id"].isin(partitions["master_holdout"])' not in after_partitions
    assert '"master_holdout_outcomes_materialized": False' in source
    assert '"allowed_for_live_execution": False' in source


def test_feature_request_is_causal_only():
    forbidden = {
        "forward_mfe_points",
        "forward_mae_points",
        "forward_close_change_points",
        "forward_expansion_pct",
        "is_expansion_event",
        "move_cluster_id",
    }
    assert forbidden.isdisjoint(set(mod.surface_mod.CAUSAL_COLUMNS))
