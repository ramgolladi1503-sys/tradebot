from __future__ import annotations

import pandas as pd

from scripts import run_cross_strike_diffusion_discovery_v1 as mod


def _metrics(**overrides):
    values = dict(
        trades=100,
        sessions=80,
        profit_factor=1.5,
        mean_return_pct=1.0,
        median_return_pct=0.5,
        win_rate=0.6,
        net_return_pct_sum=100.0,
        remove_top_five_profit_factor=1.2,
        stress_profit_factor=1.1,
        bootstrap_mean_ci_low=0.1,
        bootstrap_mean_ci_high=1.9,
        positive_folds=5,
        total_folds=5,
        largest_winner_share=0.1,
        top_five_session_profit_share=0.2,
    )
    values.update(overrides)
    return mod.Metrics(**values)


def test_mechanism_family_is_frozen_and_small():
    assert len(mod.MECHANISMS) == 8
    assert len(set(mod.MECHANISMS)) == len(mod.MECHANISMS)


def test_expanding_folds_are_prior_only():
    sessions = [f"2026-01-{day:02d}" for day in range(1, 31)]
    folds = mod.expanding_folds(sessions)
    assert len(folds) == 5
    for training, testing, _ in folds:
        assert training
        assert testing
        assert max(training) < min(testing)
        assert set(training).isdisjoint(testing)


def test_oof_gate_requires_high_occurrence():
    assert mod.oof_gate(_metrics())
    assert not mod.oof_gate(_metrics(trades=79))
    assert not mod.oof_gate(_metrics(sessions=59))


def test_holdout_gate_requires_positive_confidence_bound():
    assert mod.holdout_gate(_metrics(trades=30, sessions=25, total_folds=1, positive_folds=1))
    assert not mod.holdout_gate(
        _metrics(trades=30, sessions=25, total_folds=1, positive_folds=1, bootstrap_mean_ci_low=-0.01)
    )


def test_delayed_control_must_be_materially_weaker():
    primary = _metrics(mean_return_pct=1.0)
    delayed = _metrics(trades=80, mean_return_pct=0.7)
    assert mod.control_gate(primary, delayed)
    assert not mod.control_gate(primary, _metrics(trades=80, mean_return_pct=0.9))


def test_selection_enforces_session_cap_and_time_separation():
    timestamps = pd.to_datetime(
        ["2026-01-01 04:30:00Z", "2026-01-01 04:35:00Z", "2026-01-01 05:00:00Z"]
    )
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "diffusion_score": [3.0, 4.0, 2.0],
            "premium_distance": [1.0, 1.0, 1.0],
            "expired_instrument_key": ["a", "b", "c"],
        }
    )
    selected = mod._select_independent(frame)
    assert len(selected) == 2
    assert selected["timestamp"].max() - selected["timestamp"].min() >= pd.Timedelta(minutes=15)


def test_profit_factor_and_concentration_are_calculated():
    trades = pd.DataFrame(
        {
            "net_return_pct": [2.0, 1.0, -1.0, 0.5, -0.2] * 6,
            "stress_return_pct": [1.0, 0.0, -2.0, -0.5, -1.2] * 6,
            "fold_id": [f"fold_{index % 5}" for index in range(30)],
            "session_id": [f"s{index // 2}" for index in range(30)],
        }
    )
    metrics = mod.calculate_metrics(trades)
    assert metrics.trades == 30
    assert metrics.sessions == 15
    assert metrics.profit_factor is not None
    assert metrics.largest_winner_share is not None
    assert metrics.top_five_session_profit_share is not None


def test_feature_code_does_not_request_outcome_columns():
    forbidden = {
        "forward_mfe_points",
        "forward_mae_points",
        "forward_close_change_points",
        "forward_expansion_pct",
        "is_expansion_event",
        "move_cluster_id",
    }
    assert forbidden.isdisjoint(base_column_names())


def base_column_names():
    from scripts import run_option_surface_transition_discovery_v1 as base

    return set(base.CAUSAL_COLUMNS)
