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
    / "run_observation_first_pattern_atlas_analogues_v1.py"
)
SPEC = importlib.util.spec_from_file_location("atlas_analogues", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def frozen_catalog() -> dict:
    return {
        "semantic_sha256": "abc",
        "policy": {
            "outcomes_read": False,
            "future_returns_calculated": False,
            "pnl_calculated": False,
            "direction_selected": False,
            "unopened_sessions_scored": False,
            "regimes_mixed": False,
        },
        "lanes": [
            {
                "instrument": "NIFTY",
                "regime": "PRE_CAS",
                "verdict": "OUTCOME_BLIND_NATIVE_CADENCE_MOTIFS_FROZEN",
                "unopened_sessions_scored": False,
                "observation_sessions": ["2024-01-01", "2024-01-02"],
                "replication_sessions": ["2024-01-03"],
                "unopened_sessions": ["2024-01-04"],
                "native_cadence_minutes": 5.0,
                "windows": [],
            }
        ],
    }


def test_catalog_rejects_opened_outcome_authority() -> None:
    catalog = frozen_catalog()
    catalog["policy"]["pnl_calculated"] = True
    with pytest.raises(ValueError, match="outcome-blind authority"):
        MODULE.validate_catalog(catalog, "NIFTY", "PRE_CAS")


def test_catalog_rejects_overlapping_unopened_block() -> None:
    catalog = frozen_catalog()
    catalog["lanes"][0]["unopened_sessions"] = ["2024-01-03"]
    with pytest.raises(ValueError, match="blocks overlap"):
        MODULE.validate_catalog(catalog, "NIFTY", "PRE_CAS")


def test_prefix_indexes_take_first_half_of_every_component() -> None:
    indexes = MODULE.prefix_indices(points=6, components=3, fraction=0.5)
    assert indexes.tolist() == [0, 1, 2, 6, 7, 8, 12, 13, 14]


def test_cas_sensitivity_is_time_of_day_heuristic_only() -> None:
    assert MODULE.classify_cas_sensitivity(0.50) == "CAS_LOW_SENSITIVITY_CANDIDATE"
    assert MODULE.classify_cas_sensitivity(0.80) == "CAS_MEDIUM_SENSITIVITY"
    assert MODULE.classify_cas_sensitivity(0.90) == "CAS_HIGH_SENSITIVITY"
    assert (
        MODULE.classify_cas_sensitivity(0.97)
        == "CAS_DIRECT_CLOSING_ZONE_REVALIDATION_REQUIRED"
    )


def test_matched_pairs_use_prefix_geometry_and_different_sessions() -> None:
    prefix_values = np.asarray(
        [
            [0.0, 0.0],
            [0.05, 0.05],
            [1.0, 1.0],
        ],
        dtype=float,
    )
    metadata = pd.DataFrame(
        [
            {
                "session_date": "2024-01-01",
                "start_timestamp": "2024-01-01T10:00:00+05:30",
                "start_progress": 0.20,
            },
            {
                "session_date": "2024-01-02",
                "start_timestamp": "2024-01-02T10:01:00+05:30",
                "start_progress": 0.205,
            },
            {
                "session_date": "2024-01-03",
                "start_timestamp": "2024-01-03T14:00:00+05:30",
                "start_progress": 0.75,
            },
        ]
    )
    pairs = MODULE.matched_pairs(
        prefix_values,
        metadata,
        completion_rows=np.asarray([0, 2]),
        divergence_rows=np.asarray([1]),
    )
    assert [
        (item["divergence_session_date"], item["completion_session_date"])
        for item in pairs
    ] == [("2024-01-02", "2024-01-01")]
    assert pairs[0]["divergence_start_timestamp"] == "2024-01-02T10:01:00+05:30"
    assert pairs[0]["completion_start_timestamp"] == "2024-01-01T10:00:00+05:30"
    assert pairs[0]["prefix_match_distance"] < 0.1


def test_distance_is_dimension_normalized() -> None:
    values = np.asarray([[1.0, 1.0, 1.0, 1.0]])
    center = np.zeros(4)
    distance = MODULE.normalized_distances(values, center)
    assert distance.tolist() == pytest.approx([1.0])
