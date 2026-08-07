from __future__ import annotations

from datetime import date
from pathlib import Path
import importlib.util
import sys

import numpy as np
import pandas as pd


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_observation_first_pattern_atlas_index_trajectory_v2.py"
)
SPEC = importlib.util.spec_from_file_location("index_trajectory_v2", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_authoritative_source_requires_exact_sha_and_basename() -> None:
    inventory = {
        "files": [
            {
                "path": "a/constituent_index_5m.parquet",
                "sha256": "abc",
                "schema_error": None,
                "outcome_like_columns": [],
            },
            {
                "path": "b/other.parquet",
                "sha256": "abc",
                "schema_error": None,
                "outcome_like_columns": [],
            },
        ]
    }
    selected = MODULE.select_authoritative_source(
        inventory, "abc", "constituent_index_5m.parquet"
    )
    assert selected["path"] == "a/constituent_index_5m.parquet"


def test_exact_index_selection_excludes_options_and_constituents() -> None:
    sessions = pd.date_range("2024-01-01", periods=130, freq="B")
    rows = []
    for session in sessions:
        rows.extend(
            [
                {
                    "session": session.date().isoformat(),
                    "symbol": "NIFTY",
                    "close": 22000.0,
                },
                {
                    "session": session.date().isoformat(),
                    "symbol": "NIFTY 22000 CE 25 JAN 24",
                    "close": 100.0,
                },
                {
                    "session": session.date().isoformat(),
                    "symbol": "RELIANCE",
                    "close": 2500.0,
                },
            ]
        )
    selected, diagnostics = MODULE.select_exact_index_rows(
        pd.DataFrame(rows),
        "NIFTY",
        minimum_sessions=120,
        minimum_median_price=10000.0,
    )
    assert set(selected["symbol"]) == {"NIFTY"}
    assert diagnostics["selected_sessions"] == 130


def make_causal_group(observed_every: int = 5) -> pd.DataFrame:
    rows = 376
    timestamps = pd.date_range(
        "2025-01-02 09:15", periods=rows, freq="1min", tz="Asia/Kolkata"
    )
    observed = np.zeros(rows, dtype=bool)
    observed[::observed_every] = True
    since = pd.Series(observed).groupby(pd.Series(observed).cumsum()).cumcount()
    progress = np.linspace(0.0, 1.0, rows)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "instrument": "NIFTY",
            "session_date": date(2025, 1, 2),
            "regime": "PRE_CAS",
            "native_cadence_minutes": float(observed_every),
            "observed_this_minute": observed,
            "minutes_since_observation": since.astype(float),
            "session_progress": progress,
            "return_from_open": progress * 0.01,
            "rolling_volatility_15": 0.001,
            "directional_efficiency_15": 0.5,
            "expanding_range_position": 0.5,
            "vwap_distance": 0.0,
        }
    )


def test_complete_five_minute_session_passes_native_coverage() -> None:
    accepted, rejected = MODULE.build_cadence_aware_vectors(
        make_causal_group(5),
        points=32,
        minimum_native_coverage=0.90,
        maximum_staleness_multiple=1.25,
    )
    assert [item["session_date"] for item in accepted] == ["2025-01-02"]
    assert accepted[0]["quality"]["native_bar_coverage"] >= 0.90
    assert accepted[0]["quality"]["staleness_multiple"] <= 1.25
    assert rejected == []


def test_missing_native_bars_fail_quality_gate() -> None:
    frame = make_causal_group(5)
    frame.loc[frame.index[100:160], "observed_this_minute"] = False
    observed = frame["observed_this_minute"]
    frame["minutes_since_observation"] = (
        observed.groupby(observed.cumsum()).cumcount().astype(float)
    )
    accepted, rejected = MODULE.build_cadence_aware_vectors(
        frame,
        points=32,
        minimum_native_coverage=0.90,
        maximum_staleness_multiple=1.25,
    )
    assert accepted == []
    assert rejected[0]["session_date"] == "2025-01-02"
    assert "native_gap_exceeds_threshold" in rejected[0]["reasons"]
