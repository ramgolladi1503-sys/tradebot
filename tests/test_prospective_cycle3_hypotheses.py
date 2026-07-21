from __future__ import annotations

import pandas as pd

from research.prospective_structural_edge_v2.cycle3_development_runner import (
    ac11,
    ac12,
    ac13,
    blocks,
    summarize,
)


def _df(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01 09:15", periods=len(values), freq="min"),
            "symbol": ["X"] * len(values),
            "open": values,
            "high": [v + 0.2 for v in values],
            "low": [v - 0.2 for v in values],
            "close": values,
            "volume": [0.0] * len(values),
        }
    )


def test_ac11_leader_laggard_determinism_and_future_suffix():
    data = {
        "NIFTY": _df([100] * 30 + [101.0] + [101.5] * 30),
        "BANKNIFTY": _df([100] * 30 + [100.02] + [101.0] * 30),
        "SENSEX": _df([100] * 61),
    }
    first = ac11("20260101", data, None)
    data["NIFTY"].loc[50:, "close"] = 80.0
    second = ac11("20260101", data, None)

    assert [c.candidate_id for c in first] == [c.candidate_id for c in second]


def test_ac12_missing_prior_fails_closed():
    data = {"NIFTY": _df([100] * 40), "BANKNIFTY": _df([100] * 40), "SENSEX": _df([100] * 40)}

    assert ac12("20260101", data, None) == []


def test_ac13_convergence_candidate_targets_laggard():
    data = {
        "NIFTY": _df([100] * 30 + [99.0] + [99.4] * 100),
        "BANKNIFTY": _df([100] * 30 + [100.1] + [100.1] * 100),
        "SENSEX": _df([100] * 30 + [100.2] + [100.2] * 100),
    }

    candidates = ac13("20260101", data, None)

    assert candidates
    assert candidates[0].symbol == "NIFTY"
    assert candidates[0].direction == 1


def test_wfa_blocks_are_six_contiguous_blocks():
    sessions = [f"20260{i:03d}" for i in range(500)]
    parts = blocks(sessions)

    assert len(parts) == 6
    assert sum(len(part) for part in parts) == 500
    assert parts[0][0] == sessions[0]
    assert parts[-1][-1] == sessions[-1]


def test_summarize_empty_is_fail_closed():
    summary = summarize([])

    assert summary["candidate_count"] == 0
    assert summary["candidate_sessions"] == 0
