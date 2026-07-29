from __future__ import annotations

import pandas as pd

from scripts import run_leadership_handoff_campaign_v6 as mod
from scripts import run_leadership_handoff_campaign_v6_1 as repaired


def test_mechanism_family_and_cumulative_count_are_frozen():
    assert mod.HORIZONS == (10, 15)
    assert mod.VARIANTS == ("handoff", "strong_handoff")
    assert mod.CUMULATIVE_MECHANISM_COUNT == 31


def test_handoff_requires_positive_origin_gap_and_negative_delayed_gap():
    frame = pd.DataFrame(
        {
            "expired_instrument_key": ["x"],
            "timestamp": pd.to_datetime(["2026-01-01 04:35:00Z"]),
            "session_id": ["s1"],
            "expiry_id": ["e1"],
            "option_type": ["CE"],
            "strike": [25000.0],
            "peer_lead_gap": [-0.5],
            "leader_gap": [0.5],
            "prior_5m_return_pct": [1.0],
            "adjacent_mean_return": [0.5],
            "prior_5m_volume_ratio": [1.5],
            "oi_change_ratio": [0.1],
            "mirror_return": [-0.5],
            "option_asymmetry": [1.5],
            "entry_price_next_open": [120.0],
            "minute_of_day": [600],
            "days_to_expiry": [1],
            "surface_count": [3],
            "adjacent_count": [2],
            "volume": [100],
            "previous_return": [0.2],
            "return_acceleration": [0.8],
            "peer_dispersion": [0.1],
        }
    )
    origins = pd.DataFrame(
        {
            "expired_instrument_key": ["x"],
            "timestamp": pd.to_datetime(["2026-01-01 04:35:00Z"]),
            "session_id": ["s1"],
            "origin_timestamp": pd.to_datetime(["2026-01-01 04:30:00Z"]),
            "origin_peer_lead_gap": [1.0],
            "origin_leader_gap": [-1.0],
            "origin_prior_5m_return_pct": [0.0],
            "origin_adjacent_mean_return": [1.0],
            "origin_prior_5m_volume_ratio": [1.0],
            "origin_oi_change_ratio": [0.0],
            "origin_mirror_return": [0.0],
            "origin_option_asymmetry": [0.0],
            "mechanism": ["handoff"],
        }
    )
    original_origin_rows = mod.digest._origin_rows
    original_lookup = mod.digest._delayed_lookup
    try:
        mod.digest._origin_rows = lambda *_args, **_kwargs: origins.copy()
        mod.digest._delayed_lookup = lambda *_args, **_kwargs: frame.copy()
        signals = mod.build_handoff_signals(
            frame,
            pd.Series([True]),
            "handoff",
            {"handoff_gap_p30": -0.2},
            ["s1"],
        )
    finally:
        mod.digest._origin_rows = original_origin_rows
        mod.digest._delayed_lookup = original_lookup
    assert len(signals) == 1
    assert signals.iloc[0]["origin_peer_lead_gap"] > 0
    assert signals.iloc[0]["peer_lead_gap"] < 0


def test_strong_handoff_uses_prior_only_gap_cutoff():
    frame = pd.DataFrame(
        {
            "peer_lead_gap": [-0.5, -0.1],
            "prior_5m_return_pct": [1.0, 1.0],
            "return_acceleration": [0.5, 0.5],
            "origin_peer_lead_gap": [1.0, 1.0],
            "entry_price_next_open": [100.0, 100.0],
            "minute_of_day": [600, 600],
            "days_to_expiry": [1, 1],
            "volume": [1, 1],
            "surface_count": [3, 3],
        }
    )
    limit = min(0.0, -0.2)
    mask = (
        (frame["prior_5m_return_pct"] > 0)
        & (frame["return_acceleration"] >= 0)
        & (frame["peer_lead_gap"] < limit)
        & (frame["origin_peer_lead_gap"] > 0)
    )
    assert mask.tolist() == [True, False]


def test_repaired_runner_binds_fixed_shift_function():
    assert repaired.campaign.horizon.shift_signal_entry is repaired.fixed.shift_signal_entry


def test_master_holdout_is_not_materialized():
    import inspect

    source = inspect.getsource(mod.main)
    assert '"master_holdout_outcomes_materialized": False' in source
    assert '"master_holdout_status": "SEALED_FOR_CROSS_FAMILY_FINAL_CERTIFICATION"' in source
