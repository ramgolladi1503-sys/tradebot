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
    / "run_market_event_graph_independent_recertification_v2_regime_safe.py"
)
SPEC = importlib.util.spec_from_file_location("meg_independent_regime_safe_v2", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def frame_for_dates(dates: list[str]) -> pd.DataFrame:
    rows = []
    for date in dates:
        timestamps = pd.date_range(
            f"{date} 09:15", periods=4, freq="1min", tz="Asia/Kolkata"
        )
        for index, timestamp in enumerate(timestamps):
            rows.append(
                {
                    "timestamp": timestamp,
                    "session_date": date,
                    "close": 100.0 + index,
                    "breadth_down_1": 0.1,
                    "index_breadth_divergence": -0.0001,
                }
            )
    return pd.DataFrame(rows)


def test_pre_cas_independent_lane_is_classified_without_pooling() -> None:
    result = MODULE.classify_independent_regime(
        frame_for_dates(["2026-07-23", "2026-07-24"])
    )
    assert result["regime"] == "PRE_CAS"
    assert result["pre_cas_session_count"] == 2
    assert result["post_cas_session_count"] == 0
    assert result["regimes_pooled"] is False


def test_post_cas_independent_lane_is_classified_without_pooling() -> None:
    result = MODULE.classify_independent_regime(
        frame_for_dates(["2026-08-03", "2026-08-04"])
    )
    assert result["regime"] == "POST_CAS"
    assert result["pre_cas_session_count"] == 0
    assert result["post_cas_session_count"] == 2
    assert result["regimes_pooled"] is False


def test_cross_cas_dataset_fails_closed() -> None:
    frame = frame_for_dates(["2026-08-02", "2026-08-03"])
    with pytest.raises(ValueError, match="crosses_cas_boundary"):
        MODULE.classify_independent_regime(frame)


def test_consumed_original_holdout_still_fails_before_regime_classification() -> None:
    frame = frame_for_dates(["2026-07-22"])
    with pytest.raises(ValueError, match="not_strictly_post_holdout"):
        MODULE.classify_independent_regime(frame)


def test_semantic_hash_changes_when_regime_authority_changes() -> None:
    left = {"regime": "PRE_CAS", "regimes_pooled": False}
    right = {"regime": "POST_CAS", "regimes_pooled": False}
    assert MODULE.V2.semantic_hash(left) != MODULE.V2.semantic_hash(right)
