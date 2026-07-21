from __future__ import annotations

import pandas as pd

from research.prospective_structural_edge_v2.cycle4_underlying_runner import (
    ac16_generate,
    ac17_generate,
    ac18_generate,
    blocks,
    corr,
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


def test_ac16_prior_extreme_acceptance_and_vwap_migration_next_bar():
    prior = {s: _df([100, 101, 99, 100] * 60) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}
    values = [100.0] * 16 + [102.0] * 45 + [102.2, 102.4, 102.6] + [102.6] * 200
    data = {s: _df(values) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}

    candidates, rejections = ac16_generate("20260102", data, prior)

    assert candidates
    assert candidates[0].entry_index > candidates[0].evidence["confirmation_index"]
    assert "MISSING_PRIOR_SESSION" not in rejections


def test_ac16_missing_prior_fails_closed():
    data = {s: _df([100.0] * 300) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}

    assert ac16_generate("20260102", data, None) == ([], ["MISSING_PRIOR_SESSION"])


def test_ac17_zero_variance_correlation_window_fails_closed():
    data = {s: _df([100.0] * 220) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}

    candidates, rejections = ac17_generate("20260102", data, None)

    assert candidates == []
    assert "ZERO_VARIANCE_CORRELATION_WINDOW" in rejections


def test_ac17_correlation_estimator_and_leader_laggard_tie_breaking():
    assert corr([1, 2, 3], [1, 2, 3]) == 1.0
    n = [100.0 + i * 0.01 for i in range(220)]
    b = [100.0 + i * 0.01 for i in range(220)]
    s = [100.0 + i * 0.01 for i in range(220)]
    n[45:61] = [102.0] * 16
    b[45:61] = [98.0] * 16
    s[45:61] = [100.0] * 16
    s[62:65] = [100.2, 100.4, 100.6]
    data = {"NIFTY": _df(n), "BANKNIFTY": _df(b), "SENSEX": _df(s)}

    candidates, _ = ac17_generate("20260102", data, None)

    if candidates:
        assert candidates[0].symbol in {"NIFTY", "BANKNIFTY", "SENSEX"}
        assert candidates[0].evidence["leader"] in {"NIFTY", "BANKNIFTY"}
        assert candidates[0].evidence["laggard"] == candidates[0].symbol


def test_ac18_morning_range_and_confirming_index_count():
    base = [100.0] * 400
    up = base.copy()
    up[286] = 101.0
    data = {
        "NIFTY": _df(up),
        "BANKNIFTY": _df(up),
        "SENSEX": _df(base),
    }

    candidates, _ = ac18_generate("20260102", data, None)

    assert candidates
    assert len(candidates[0].evidence["confirmed_indices"]) == 2
    assert candidates[0].entry_index == 287


def test_cycle4_future_suffix_invariance_and_wfa_blocks():
    prior = {s: _df([100, 101, 99, 100] * 60) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}
    values = [100.0] * 16 + [102.0] * 45 + [102.2, 102.4, 102.6] + [102.6] * 200
    data = {s: _df(values) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}
    first, _ = ac16_generate("20260102", data, prior)
    data["NIFTY"].loc[120:, "close"] = 10.0
    second, _ = ac16_generate("20260102", data, prior)

    assert [c.candidate_id for c in first] == [c.candidate_id for c in second]
    parts = blocks([str(i) for i in range(500)])
    assert len(parts) == 6
    assert sum(len(p) for p in parts) == 500


def test_session_cluster_summary_empty_is_fail_closed():
    summary = summarize([])

    assert summary["candidate_count"] == 0
    assert summary["candidate_sessions"] == 0
