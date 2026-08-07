from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, filename: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RECERT = load(
    "atlas_motif_recertification_v2_test",
    "run_observation_first_pattern_atlas_motif_recertification_v2.py",
)
ANALOGUE_V2 = load(
    "atlas_analogues_v2_test",
    "run_observation_first_pattern_atlas_analogues_v2.py",
)


def catalog(policy_overrides: dict | None = None) -> dict:
    policy = {
        "native_observed_rows_only": True,
        "trajectory_quality_accepted_sessions_only": True,
        "rejected_sessions_excluded": True,
        "regimes_mixed": False,
        "unopened_sessions_scored": False,
        "outcomes_read": False,
        "future_returns_calculated": False,
        "pnl_calculated": False,
        "direction_selected": False,
    }
    policy.update(policy_overrides or {})
    return {
        "schema_version": 2,
        "stage": "trajectory_accepted_native_cadence_motif_recertification_v2",
        "semantic_sha256": "abc",
        "frozen_motif_count": 2,
        "policy": policy,
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
                "windows": [
                    {"window_minutes": 5, "motifs": [{"motif_id": "a"}]},
                    {"window_minutes": 10, "motifs": [{"motif_id": "b"}]},
                ],
            }
        ],
    }


def test_previous_catalog_safety_rejects_opened_pnl() -> None:
    unsafe = catalog({"pnl_calculated": True})
    with pytest.raises(ValueError, match="outside outcome-blind authority"):
        RECERT.safe_previous_catalog(unsafe)


def test_motif_counts_are_reported_by_horizon() -> None:
    counts = RECERT.motif_counts_by_window(catalog(), "NIFTY", "PRE_CAS")
    assert counts == {"5m": 1, "10m": 1}


def test_analogue_v2_rejects_legacy_unfiltered_catalog() -> None:
    legacy = catalog()
    legacy["schema_version"] = 1
    legacy["stage"] = "outcome_blind_native_cadence_motifs_v1"
    legacy["policy"].pop("trajectory_quality_accepted_sessions_only")
    legacy["policy"].pop("rejected_sessions_excluded")
    with pytest.raises(ValueError, match="trajectory-accepted sessions only"):
        ANALOGUE_V2.validate_recertified_catalog(legacy, "NIFTY", "PRE_CAS")


def test_analogue_v2_accepts_recertified_outcome_blind_catalog() -> None:
    lane = ANALOGUE_V2.validate_recertified_catalog(catalog(), "NIFTY", "PRE_CAS")
    assert lane["instrument"] == "NIFTY"
    assert lane["regime"] == "PRE_CAS"
