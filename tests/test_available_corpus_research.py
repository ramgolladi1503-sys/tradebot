from __future__ import annotations

import pandas as pd

from research.three_year_structural_edge_discovery.available_corpus_research import (
    Candidate,
    direction_return,
    narrow_opening_range,
)


def _bars(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01 09:15", periods=len(closes), freq="min"),
            "symbol": ["NIFTY"] * len(closes),
            "open": closes,
            "high": [x + 1 for x in closes],
            "low": [x - 1 for x in closes],
            "close": closes,
            "synthetic": [False] * len(closes),
            "mock": [False] * len(closes),
            "fallback": [False] * len(closes),
        }
    )


def _narrow_bars(closes: list[float]) -> pd.DataFrame:
    df = _bars(closes)
    df["high"] = [x + 0.05 for x in closes]
    df["low"] = [x - 0.05 for x in closes]
    return df


def test_candidate_id_is_deterministic_from_causal_fields():
    first = Candidate("H", "20260101", "NIFTY", 1, 31, "ts", 30, {"x": 1})
    second = Candidate("H", "20260101", "NIFTY", 1, 31, "ts", 30, {"x": 1})
    changed = Candidate("H", "20260101", "NIFTY", 1, 32, "ts", 30, {"x": 1})

    assert first.candidate_id == second.candidate_id
    assert first.candidate_id != changed.candidate_id


def test_direction_return_uses_entry_and_future_horizon_only():
    df = _bars([100, 101, 102, 103])

    ret, mfe, mae = direction_return(df, 1, 1, 2)

    assert round(ret, 6) == round((103 / 101 - 1) * 10_000, 6)
    assert mfe > 0
    assert mae < mfe


def test_narrow_opening_range_future_suffix_does_not_change_past_entry():
    prefix = [100.0] * 30 + [101.0, 102.0, 103.0]
    later_a = _narrow_bars(prefix + [120.0] * 20)
    later_b = _narrow_bars(prefix + [80.0] * 20)

    first = narrow_opening_range("20260101", {"NIFTY": later_a}, None)[0]
    second = narrow_opening_range("20260101", {"NIFTY": later_b}, None)[0]

    assert first.entry_index == second.entry_index
    assert first.direction == second.direction
    assert first.candidate_id == second.candidate_id
