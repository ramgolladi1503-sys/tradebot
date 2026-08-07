from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_observation_first_pattern_atlas_full_certification_v2.py"
)
SPEC = importlib.util.spec_from_file_location("atlas_full_certification_v2", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def recertified_motif_catalog() -> dict:
    return {
        "schema_version": 2,
        "stage": "trajectory_accepted_native_cadence_motif_recertification_v2",
        "principal_verdict": "OUTCOME_BLIND_TRAJECTORY_ACCEPTED_MOTIFS_RECERTIFIED",
        "semantic_sha256": "motif-authority",
        "policy": {
            "outcomes_read": False,
            "future_returns_calculated": False,
            "pnl_calculated": False,
            "direction_selected": False,
            "unopened_sessions_scored": False,
            "regimes_mixed": False,
            "trajectory_quality_accepted_sessions_only": True,
            "rejected_sessions_excluded": True,
        },
        "lanes": [
            {
                "instrument": "NIFTY",
                "regime": "PRE_CAS",
                "verdict": "OUTCOME_BLIND_NATIVE_CADENCE_MOTIFS_FROZEN",
                "unopened_sessions_scored": False,
                "observation_sessions": ["2024-01-01"],
                "replication_sessions": ["2024-01-02"],
                "unopened_sessions": ["2024-01-03"],
                "native_cadence_minutes": 5.0,
                "windows": [],
            }
        ],
    }


def causal_analogue_catalog() -> dict:
    return {
        "schema_version": 3,
        "stage": "pre_cas_causal_prefix_matched_geometric_analogues_v3",
        "principal_verdict": "PRE_CAS_CAUSAL_PREFIX_MATCHED_GEOMETRIC_ANALOGUES_FROZEN",
        "source_motif_catalog_sha256": "motif-authority",
        "policy": {
            "pre_cas_only": True,
            "trajectory_quality_accepted_sessions_only": True,
            "causal_prefix_representation": True,
            "prefix_scaler_fit_on_observation_prefixes_only": True,
            "suffix_values_used_in_prefix_trigger": False,
            "unopened_sessions_scored": False,
        },
        "windows": [],
    }


def session_frame(start_utc: str = "2024-01-02T03:45:00Z") -> pd.DataFrame:
    timestamps = pd.date_range(start_utc, periods=10, freq="5min", tz="UTC")
    prices = [100.0, 99.0, 100.0, 102.0, 101.0, 100.5, 100.0, 99.5, 99.0, 98.5]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "session_date": ["2024-01-02"] * len(timestamps),
            "price": prices,
            "causal_vwap": [100.0] * len(timestamps),
            "session_progress": np.linspace(0.0, 0.2, len(timestamps)),
        }
    )


def calibration_that_qualifies_first_and_second(session: pd.DataFrame) -> tuple[dict, float, float]:
    v0 = MODULE.A3.causal_prefix_vector(session.iloc[0:2], 2)
    v2 = MODULE.A3.causal_prefix_vector(session.iloc[2:4], 2)
    median = np.zeros_like(v0)
    scale = np.ones_like(v0)
    prototype = v2.copy()
    d0 = float(MODULE.A3.normalized_distances(v0, prototype)[0])
    d2 = float(MODULE.A3.normalized_distances(v2, prototype)[0])
    calibration = {
        "prefix_points": 2,
        "scaler_median": median.tolist(),
        "scaler_scale": scale.tolist(),
        "motif_prefix_prototype": prototype.tolist(),
        "distance_threshold": max(d0, d2) + 0.01,
        "suffix_values_used": False,
        "scaler_fit_scope": "observation_prefixes_only",
    }
    return calibration, d0, d2


def test_validation_rejects_old_noncausal_analogue_authority() -> None:
    motif = recertified_motif_catalog()
    analogue = causal_analogue_catalog()
    analogue["schema_version"] = 2
    analogue["stage"] = "pre_cas_matched_geometric_analogues_v1"
    analogue["principal_verdict"] = "PRE_CAS_MATCHED_GEOMETRIC_ANALOGUES_FROZEN"
    with pytest.raises(ValueError, match="schema_version=3"):
        MODULE.validate_inputs_v2(motif, analogue, "NIFTY")


def test_validation_accepts_causal_prefix_v3_authority() -> None:
    lane = MODULE.validate_inputs_v2(
        recertified_motif_catalog(), causal_analogue_catalog(), "NIFTY"
    )
    assert lane["regime"] == "PRE_CAS"
    assert lane["unopened_sessions"] == ["2024-01-03"]


def test_first_qualifying_prefix_wins_even_when_later_match_is_closer() -> None:
    session = session_frame()
    calibration, first_distance, second_distance = calibration_that_qualifies_first_and_second(session)
    assert second_distance < first_distance
    start, distance = MODULE.first_qualifying_prefix_index(
        session,
        calibration,
        full_window_points=4,
        cadence_minutes=5.0,
        future_points=2,
    )
    assert start == 0
    assert distance == pytest.approx(first_distance)
    assert distance > second_distance


def test_future_suffix_mutation_does_not_change_first_trigger() -> None:
    session = session_frame()
    calibration, _, _ = calibration_that_qualifies_first_and_second(session)
    original = MODULE.first_qualifying_prefix_index(
        session, calibration, 4, 5.0, 2
    )
    mutated = session.copy()
    mutated.loc[2:, "price"] = [500.0, 10.0, 800.0, 20.0, 900.0, 30.0, 1000.0, 40.0]
    changed = MODULE.first_qualifying_prefix_index(
        mutated, calibration, 4, 5.0, 2
    )
    assert original[0] == changed[0] == 0
    assert original[1] == pytest.approx(changed[1])


def test_known_pre_cas_close_blocks_too_late_signal() -> None:
    late = session_frame("2024-01-02T09:50:00Z")  # 15:20 IST
    calibration, _, _ = calibration_that_qualifies_first_and_second(late)
    result = MODULE.first_qualifying_prefix_index(
        late,
        calibration,
        full_window_points=4,
        cadence_minutes=5.0,
        future_points=2,
    )
    # First prefix would end at 15:25 IST, while the fixed 10m horizon exits 15:35.
    assert result is None
