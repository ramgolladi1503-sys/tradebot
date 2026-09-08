from __future__ import annotations

import pandas as pd
import pytest

from research.macd_futures_participation_regime_v1.analysis import CampaignBlocked
from research.macd_futures_participation_regime_v1.timing_control import (
    within_session_circular_state_shift_control,
)


def _fixture():
    state_rows = []
    signal_rows = []
    assignment_rows = []
    primary_rows = []

    for day_idx, day in enumerate(["2026-01-05", "2026-01-06"]):
        ts = pd.date_range(
            f"{day} 10:00", periods=60, freq="min", tz="Asia/Kolkata"
        )
        labels = [False] * 20 + [True] * 20 + [False] * 20
        for t, label in zip(ts, labels):
            state_rows.append(
                {
                    "timestamp": t,
                    "session_date": day,
                    "h1_active": label,
                }
            )

        for local_idx, pos in enumerate([5, 25, 35, 50]):
            trade_id = f"D{day_idx}S{local_idx}"
            label = labels[pos]
            signal_net = 10.0 if label else 1.0
            signal_rows.append(
                {
                    "signal_trade_id": trade_id,
                    "signal_origin": ts[pos],
                    "net_6bps": signal_net,
                }
            )
            primary_rows.append(
                {
                    "signal_trade_id": trade_id,
                    "signal_state": label,
                    "delta_net_6bps": signal_net,
                }
            )
            for placebo_ts in ts:
                assignment_rows.append(
                    {
                        "signal_trade_id": trade_id,
                        "matched_placebo_origin": placebo_ts,
                        "net_6bps": 0.0,
                    }
                )

    return (
        pd.DataFrame(signal_rows),
        pd.DataFrame(assignment_rows),
        pd.DataFrame(state_rows),
        pd.DataFrame(primary_rows),
    )


def test_timing_shift_control_recomputes_matching_with_valid_replications():
    signals, assigned, state, primary = _fixture()
    result = within_session_circular_state_shift_control(
        signals=signals,
        assigned=assigned,
        state=state,
        state_col="h1_active",
        primary_per_signal=primary,
        reps=200,
        seed=20260908,
    )
    assert result["reps_valid"] == 200
    assert result["minimum_compatible_placebos_per_signal"] == 20
    assert 0.0 < result["empirical_p_active_one_sided"] <= 1.0
    assert 0.0 < result["empirical_p_interaction_one_sided"] <= 1.0
    assert result["global_multiplicity_applied"] is False
    assert result["structural_edge_certified"] is False


def test_timing_shift_control_blocks_when_matching_is_too_thin():
    signals, assigned, state, primary = _fixture()
    # Leave only five placebo origins per signal; every shifted replication then
    # violates the production frozen minimum of 20 compatible origins.
    thin = assigned.groupby("signal_trade_id", sort=False).head(5).reset_index(drop=True)
    with pytest.raises(CampaignBlocked, match="INSUFFICIENT_VALID_REPS"):
        within_session_circular_state_shift_control(
            signals=signals,
            assigned=thin,
            state=state,
            state_col="h1_active",
            primary_per_signal=primary,
            reps=50,
            seed=20260908,
        )
