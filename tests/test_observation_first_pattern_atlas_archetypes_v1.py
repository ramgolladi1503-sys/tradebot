from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_observation_first_pattern_atlas_archetypes_v1.py"
SPEC = importlib.util.spec_from_file_location("atlas_archetype", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def payload(sessions: int = 80) -> dict:
    rows = []
    for index in range(sessions):
        regime = "PRE_CAS" if index < sessions - 5 else "POST_CAS"
        group = index % 2
        curve = (np.linspace(0, 0.02, 12) if group == 0 else np.linspace(0, -0.02, 12)) + np.sin(np.arange(12)) * 0.0001
        rows.append({
            "instrument": "NIFTY",
            "session_date": (pd.Timestamp("2025-01-01") + pd.Timedelta(days=index)).date().isoformat(),
            "regime": regime,
            "semantic_sha256": str(index),
            "features": {
                "return_from_open": curve.tolist(),
                "rolling_volatility_15": (np.abs(curve) + 0.001).tolist(),
                "directional_efficiency_15": [0.8] * 12,
                "expanding_range_position": [0.8 if group == 0 else 0.2] * 12,
                "vwap_distance": (curve * 0.5).tolist(),
            },
        })
    return {"sessions": rows}


def test_outcome_like_keys_are_rejected() -> None:
    with pytest.raises(ValueError):
        MODULE.flatten_sessions({"sessions": [{"instrument": "NIFTY", "future_return_5": 1}]})


def test_flatten_keeps_regimes_explicit() -> None:
    frame = MODULE.flatten_sessions(payload())
    assert set(frame["regime"]) == {"PRE_CAS", "POST_CAS"}


def test_chronological_blocks_do_not_shuffle() -> None:
    frame = MODULE.flatten_sessions(payload(60)).loc[lambda value: value["regime"].eq("PRE_CAS")]
    observation, replication, unopened = MODULE.chronological_blocks(frame)
    assert observation["session_date"].max() < replication["session_date"].min()
    assert replication["session_date"].max() < unopened["session_date"].min()


def test_post_cas_small_lane_is_not_pooled_into_pre_cas() -> None:
    frame = MODULE.flatten_sessions(payload())
    lane = MODULE.fit_lane(frame, "NIFTY", "POST_CAS")
    assert lane["verdict"] == "INSUFFICIENT_SESSIONS_FOR_ARCHETYPE_DISCOVERY"
    assert lane["sessions"] == 5


def test_synthetic_pre_cas_lane_freezes_archetypes() -> None:
    frame = MODULE.flatten_sessions(payload(100))
    lane = MODULE.fit_lane(frame, "NIFTY", "PRE_CAS")
    assert lane["verdict"] == "OUTCOME_BLIND_DAY_ARCHETYPES_FROZEN"
    assert lane["stable_archetype_ids"]
    assert lane["outcomes_read"] is False
