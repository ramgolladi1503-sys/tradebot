from __future__ import annotations

import pandas as pd

from scripts import run_post_imbalance_digestion_campaign_v4 as mod


def test_family_is_frozen_and_cumulative_multiplicity_is_declared():
    assert len(mod.MECHANISMS) == 8
    assert mod.CUMULATIVE_MECHANISM_COUNT == 24
    assert set(mod.ORIGIN_FAMILY) == set(mod.MECHANISMS)


def test_origin_timestamp_is_delayed_before_entry():
    frame = pd.DataFrame(
        {
            "expired_instrument_key": ["x"],
            "timestamp": pd.to_datetime(["2026-01-01 04:30:00Z"]),
            "session_id": ["s1"],
            "expiry_id": ["e1"],
            "option_type": ["CE"],
            "strike": [25000.0],
            "peer_lead_gap": [1.0],
            "leader_gap": [-1.0],
            "prior_5m_return_pct": [0.0],
            "adjacent_mean_return": [1.0],
            "prior_5m_volume_ratio": [2.0],
            "oi_change_ratio": [0.1],
            "mirror_return": [-1.0],
            "option_asymmetry": [1.0],
            "entry_price_next_open": [100.0],
            "minute_of_day": [600],
            "days_to_expiry": [1],
            "surface_count": [3],
            "adjacent_count": [2],
            "volume": [10],
            "previous_return": [0.0],
        }
    )
    rows = mod._origin_rows(frame, pd.Series([True]), mod.MECHANISMS[0], ["s1"])
    assert rows.loc[0, "timestamp"] == rows.loc[0, "origin_timestamp"] + pd.Timedelta(minutes=5)


def test_confirmation_is_computed_from_completed_delayed_state():
    frame = pd.DataFrame(
        {
            "prior_5m_return_pct": [1.0],
            "leader_gap": [0.5],
            "return_acceleration": [0.2],
            "prior_5m_volume_ratio": [2.0],
            "oi_change_ratio": [0.1],
            "adjacent_mean_return": [0.5],
            "peer_dispersion": [0.1],
            "previous_return": [0.2],
            "peer_lead_gap": [0.2],
            "origin_peer_lead_gap": [1.0],
            "mirror_return": [-0.5],
            "option_asymmetry": [1.5],
        }
    )
    cut = {
        "delayed_volume_p50": 1.0,
        "delayed_dispersion_p60": 0.5,
        "delayed_target_abs_p60": 2.0,
    }
    assert mod.confirmation_mask(frame, "delayed_confirmed_leader_reentry", cut).iloc[0]
    assert mod.confirmation_mask(frame, "delayed_persistent_peer_reclaim", cut).iloc[0]


def test_master_holdout_is_sealed_in_source():
    import inspect

    source = inspect.getsource(mod.main)
    after_outcome_load = source.split("research_outcomes =", 1)[1]
    assert 'partitions["master_holdout"]' not in after_outcome_load
    assert '"master_holdout_outcomes_materialized": False' in source
