from __future__ import annotations

import pandas as pd

from research.prospective_structural_edge_v2.cycle5_failure_runner import (
    ac22,
    ac23,
    ac24,
    blocks,
    summarize,
)


def _df(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01 09:15", periods=len(values), freq="min"),
            "symbol": ["X"] * len(values),
            "open": values,
            "high": [v + 0.1 for v in values],
            "low": [v - 0.1 for v in values],
            "close": values,
            "volume": [1.0] * len(values),
        }
    )


def test_ac22_opening_repair_second_side_acceptance_next_bar():
    prior = {s: _df([100.0] * 220) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}
    values = [101.0] * 10 + [100.05] * 25 + [99.5] * 100
    data = {s: _df(values) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}

    candidates, _ = ac22("20260102", data, prior)

    assert candidates
    assert candidates[0].entry_index > candidates[0].evidence["confirmation_index"]


def test_ac23_two_index_nonconfirmation_reversal():
    base = [100.0] * 220
    move = base.copy()
    move[76] = 101.0
    data = {"NIFTY": _df(move), "BANKNIFTY": _df(base), "SENSEX": _df(base)}

    candidates, _ = ac23("20260102", data, None)

    assert candidates
    assert candidates[0].symbol == "NIFTY"
    assert candidates[0].direction == -1


def test_ac24_prior_body_midpoint_rejection():
    prior = {s: _df([100.0] * 219 + [100.0]) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}
    values = [100.4] * 10 + [100.0] * 10 + [100.2] * 150
    data = {s: _df(values) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}

    candidates, _ = ac24("20260102", data, prior)

    assert candidates
    assert candidates[0].direction == 1


def test_cycle5_blocks_and_empty_summary_are_fail_closed():
    parts = blocks([str(i) for i in range(500)])
    assert len(parts) == 6
    assert sum(len(p) for p in parts) == 500

    summary = summarize([])
    assert summary["candidate_count"] == 0
    assert summary["candidate_sessions"] == 0
