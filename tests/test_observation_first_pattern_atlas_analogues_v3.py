from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_observation_first_pattern_atlas_analogues_v3.py"
)
SPEC = importlib.util.spec_from_file_location("atlas_analogues_v3", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def sample_window() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "price": [100.0, 101.0, 100.5, 103.0, 95.0, 120.0],
            "causal_vwap": [100.0, 100.4, 100.6, 101.2, 99.0, 105.0],
            "session_progress": [0.10, 0.12, 0.14, 0.16, 0.18, 0.20],
        }
    )


def test_suffix_mutation_cannot_change_causal_prefix_vector() -> None:
    original = sample_window()
    mutated = original.copy()
    mutated.loc[3:, "price"] = [500.0, 10.0, 1000.0]
    mutated.loc[3:, "causal_vwap"] = [2.0, 900.0, 3.0]
    left = MODULE.causal_prefix_vector(original, prefix_points=3)
    right = MODULE.causal_prefix_vector(mutated, prefix_points=3)
    np.testing.assert_array_equal(left, right)


def test_prefix_mutation_can_change_causal_prefix_vector() -> None:
    original = sample_window()
    mutated = original.copy()
    mutated.loc[1, "price"] = 110.0
    left = MODULE.causal_prefix_vector(original, prefix_points=3)
    right = MODULE.causal_prefix_vector(mutated, prefix_points=3)
    assert not np.allclose(left, right)


def test_calibration_payload_explicitly_forbids_suffix_authority() -> None:
    payload = MODULE.calibration_payload(
        prefix_median=np.zeros(4),
        prefix_scale=np.ones(4),
        prototype=np.zeros(4),
        threshold=1.25,
        prefix_points=3,
        cadence_minutes=5.0,
    )
    assert payload["suffix_values_used"] is False
    assert payload["scaler_fit_scope"] == "observation_prefixes_only"
    assert payload["representation"] == "prefix_rows_only_motif_vector_v1"
