from __future__ import annotations

import pandas as pd

from research.macd_futures_participation_regime_v1.analysis import build_basis_state
from research.macd_futures_participation_regime_v1.robustness import robustness_bundle


def _aligned() -> pd.DataFrame:
    ts = pd.date_range(
        "2026-01-05 09:15", periods=90, freq="min", tz="Asia/Kolkata"
    )
    spot = pd.Series(range(90), dtype=float) + 25000.0
    # Increasing basis makes both change and later acceleration causal/observable.
    basis = pd.Series([0.0] * 20 + [float((i - 19) ** 2) / 10.0 for i in range(20, 90)])
    return pd.DataFrame(
        {
            "timestamp": ts,
            "session_date": "2026-01-05",
            "spot_close": spot,
            "futures_close": spot + basis,
        }
    )


def test_h2_literal_state_requires_positive_change_and_acceleration():
    state = build_basis_state(_aligned())
    known = state[state["h2_active"].notna()].copy()
    active = known[known["h2_active"] == True]  # noqa: E712
    assert not active.empty
    assert (active["basis_chg_15m"] > 0.0).all()
    assert (active["basis_acceleration_15m"] > 0.0).all()


def _per_signal() -> pd.DataFrame:
    sessions = pd.date_range("2025-01-02", periods=40, freq="7D")
    rows = []
    for i, day in enumerate(sessions):
        active = i % 2 == 0
        rows.append(
            {
                "signal_trade_id": f"S{i:03d}",
                "signal_origin": pd.Timestamp(day.date()).tz_localize("Asia/Kolkata")
                + pd.Timedelta(hours=10),
                "signal_session_date": str(day.date()),
                "signal_state": active,
                "signal_net_6bps": 12.0 if active else 2.0,
                "compatible_placebo_n": 100,
                "placebo_mean_net_6bps": 2.0 if active else 1.0,
                "delta_net_6bps": 10.0 if active else 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_robustness_bundle_preserves_positive_interaction_across_folds():
    folds, bundle = robustness_bundle(_per_signal())
    assert len(folds) == 4
    assert bundle["temporal_summary"]["positive_active_delta_folds"] == 4
    assert bundle["temporal_summary"]["positive_interaction_lift_folds"] == 4
    assert bundle["bootstrap"]["active_delta_95ci"][0] > 0.0
    assert bundle["bootstrap"]["interaction_lift_95ci"][0] > 0.0
    assert bundle["top_five_session_removal"]["active_delta_after_removal"] > 0.0
    assert "structural_edge_certified" not in bundle


def test_leave_one_quarter_out_is_populated_and_outcome_rule_unchanged():
    _, bundle = robustness_bundle(_per_signal())
    loo = bundle["leave_one_quarter_out"]
    assert len(loo) >= 2
    assert all(row["active_delta_net_6bps"] == 10.0 for row in loo)
