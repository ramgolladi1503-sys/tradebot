from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.govern_provider_sparse_bars_v1 import (
    apply_research_eligibility,
    build_fixture_for_gap,
    causal_feature_validity,
    five_minute_governance,
)


ROOT = Path("research/provider_sparse_bar_governance_v1")


def read_json(name: str):
    return json.loads((ROOT / name).read_text())


def test_final_promotes_discovery_ready_with_exact_four_sparse_bars() -> None:
    final = read_json("final_verdict.json")
    gaps = read_json("gap_metadata.json")["sparse_bars"]
    assert final["final_verdict"] == "DISCOVERY_READY"
    assert final["provider_authoritative_sparse_bar_count"] == 4
    assert len(gaps) == 4
    assert {row["absence_reason"] for row in gaps} == {"PROVIDER_AUTHORITATIVE_ABSENCE_HTTP_200_REQUIRED_BAR_ABSENT"}
    assert all(row["synthetic_ohlc_allowed"] is False for row in gaps)


def test_gap_aware_features_do_not_leak_across_missing_minute() -> None:
    frame = build_fixture_for_gap("2024-12-12", "09:42")
    governed = causal_feature_validity(frame)
    after_gap = governed[pd.to_datetime(governed["timestamp"]).dt.strftime("%H:%M").eq("09:43")].iloc[0]
    assert not bool(after_gap["momentum_valid"])
    assert not bool(after_gap["atr_valid"])
    assert not bool(after_gap["rolling_volatility_valid"])
    assert bool(after_gap["continuation_counts_valid"])
    assert int(after_gap["continuation_counts_restart_group"]) == 1


def test_partial_five_minute_bucket_blocks_strict_research() -> None:
    frame = build_fixture_for_gap("2025-03-25", "10:42")
    governed = apply_research_eligibility(five_minute_governance(causal_feature_validity(frame)))
    partial = governed[governed["observed_minutes"].lt(governed["expected_minutes"])]
    assert not partial.empty
    assert partial["five_minute_window_complete"].eq(False).all()
    assert partial["eligible_for_strict_research"].eq(False).all()
    assert partial["research_eligible"].eq(False).all()


def test_capability_matrix_matches_sparse_bar_policy() -> None:
    matrix = read_json("capability_matrix.json")["capabilities"]
    assert matrix["Option replay"] == "SUPPORTED"
    assert matrix["Strike research"] == "SUPPORTED"
    assert matrix["Joint warehouse"] == "SUPPORTED"
    assert matrix["Structural discovery"] == "SUPPORTED"
    assert matrix["Sparse-bar aware"] == "SUPPORTED"
    assert matrix["Synthetic candles"] == "NOT SUPPORTED"
    assert matrix["Gap interpolation"] == "FORBIDDEN"
    assert matrix["Spread simulation"] == "NOT SUPPORTED"
    assert matrix["IV research"] == "NOT SUPPORTED"
    assert matrix["Volume research"] == "LIMITED"
