from __future__ import annotations

import pandas as pd

from scripts.audit_late_day_ce_inventory_rebound_v5_signal_oracle import (
    expanding_folds,
    identities,
    select,
    thresholds,
)


def test_expanding_folds_are_chronological_and_non_overlapping() -> None:
    sessions = [f"2026-01-{day:02d}" for day in range(1, 21)]
    folds = expanding_folds(sessions)

    assert len(folds) == 4
    previous_training = 0
    for training, testing, fold_id in folds:
        assert fold_id.startswith("fold_")
        assert len(training) >= previous_training
        assert set(training).isdisjoint(testing)
        assert max(training) < min(testing)
        previous_training = len(training)


def test_select_uses_first_time_then_most_extreme_contract() -> None:
    timestamp = pd.Timestamp("2026-01-05 08:00:00", tz="UTC")
    frame = pd.DataFrame(
        {
            "option_type": ["CE", "CE", "CE"],
            "minute_of_day": [800, 800, 805],
            "prior_5m_return_pct": [-10.0, -12.0, -20.0],
            "prior_5m_volume_ratio": [4.0, 4.0, 5.0],
            "return_acceleration": [-7.0, -9.0, -12.0],
            "mirror_return": [8.0, 9.0, 12.0],
            "option_asymmetry": [-18.0, -21.0, -32.0],
            "entry_price_next_open": [100.0, 90.0, 80.0],
            "days_to_expiry": [1, 1, 1],
            "surface_count": [5, 5, 5],
            "volume": [1000, 1000, 1000],
            "previous_return": [-2.0, -2.0, -2.0],
            "session_id": ["2026-01-05"] * 3,
            "directional_mass_shift": [0.0, 0.0, 0.0],
            "expired_instrument_key": ["a", "b", "c"],
            "timestamp": [
                timestamp,
                timestamp,
                timestamp + pd.Timedelta(minutes=5),
            ],
        }
    )
    cut = {
        "ret_p10": -9.0,
        "ret_p80": 4.0,
        "volume_p90": 3.0,
        "accel_p10": -6.0,
        "asym_p10": -15.0,
    }

    selected = select(frame, cut, ["2026-01-05"])

    assert len(selected) == 1
    assert selected.iloc[0]["expired_instrument_key"] == "b"


def test_thresholds_use_only_supplied_training_rows() -> None:
    training = pd.DataFrame(
        {
            "prior_5m_return_pct": [-10.0, -5.0, 0.0, 5.0, 10.0],
            "prior_5m_volume_ratio": [1.0, 2.0, 3.0, 4.0, 5.0],
            "return_acceleration": [-8.0, -4.0, 0.0, 4.0, 8.0],
            "option_asymmetry": [-20.0, -10.0, 0.0, 10.0, 20.0],
        }
    )

    cut = thresholds(training)

    assert cut["ret_p10"] == -8.0
    assert cut["ret_p80"] == 6.0
    assert cut["volume_p90"] == 4.6
    assert cut["accel_p10"] == -6.4
    assert cut["asym_p10"] == -16.0


def test_identities_stamp_role_and_fold() -> None:
    frame = pd.DataFrame(
        {
            "session_id": ["2026-01-05"],
            "timestamp": [pd.Timestamp("2026-01-05", tz="UTC")],
            "expired_instrument_key": ["contract-a"],
        }
    )

    result = identities(frame, "research_oof_primary", "fold_1")

    assert result.loc[0, "ledger_role"] == "research_oof_primary"
    assert result.loc[0, "fold_id"] == "fold_1"
