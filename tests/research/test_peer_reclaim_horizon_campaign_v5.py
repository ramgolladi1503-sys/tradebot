from __future__ import annotations

import pandas as pd

from scripts import run_peer_reclaim_horizon_campaign_v5 as mod
from scripts import run_peer_reclaim_horizon_campaign_v5_1 as fixed


def test_horizons_are_frozen_and_cumulative_count_is_declared():
    assert mod.HORIZONS == (10, 15, 20)
    assert mod.CUMULATIVE_MECHANISM_COUNT == 27


def test_exact_horizon_uses_future_close_only_in_outcome_attachment():
    signal = pd.DataFrame(
        {
            "expired_instrument_key": ["x"],
            "timestamp": pd.to_datetime(["2026-01-01 04:30:00Z"]),
            "entry_price_next_open": [100.0],
            "session_id": ["s1"],
        }
    )
    causal = pd.DataFrame(
        {
            "expired_instrument_key": ["x"],
            "timestamp": pd.to_datetime(["2026-01-01 04:40:00Z"]),
            "close": [110.0],
        }
    )
    trades = mod.attach_exact_horizon(signal, causal, 10, "fold_1")
    assert trades.loc[0, "gross_return_pct"] == 10.0
    assert trades.loc[0, "label_horizon_minutes"] == 10


def test_fixed_delayed_entry_preserves_session_key():
    signal = pd.DataFrame(
        {
            "expired_instrument_key": ["x"],
            "timestamp": pd.to_datetime(["2026-01-01 04:30:00Z"]),
            "session_id": ["s1"],
            "entry_price_next_open": [100.0],
            "expiry_id": ["e1"],
            "option_type": ["CE"],
            "strike": [25000.0],
            "days_to_expiry": [1],
            "minute_of_day": [600],
        }
    )
    causal = pd.DataFrame(
        {
            "expired_instrument_key": ["x"],
            "timestamp": pd.to_datetime(["2026-01-01 04:35:00Z"]),
            "session_id": ["s1"],
            "entry_price_next_open": [95.0],
            "expiry_id": ["e1"],
            "option_type": ["CE"],
            "strike": [25000.0],
            "days_to_expiry": [1],
            "minute_of_day": [605],
        }
    )
    shifted = fixed.shift_signal_entry(signal, causal, 5)
    assert shifted.loc[0, "session_id"] == "s1"
    assert shifted.loc[0, "entry_price_next_open"] == 95.0


def test_master_holdout_remains_sealed():
    import inspect

    source = inspect.getsource(mod.main)
    after_partitions = source.split("partitions =", 1)[1]
    assert "master_holdout_outcomes_materialized\": False" in source
    assert "base._load_outcomes" not in source
    assert "master_holdout" in after_partitions
