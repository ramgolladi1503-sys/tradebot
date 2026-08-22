from datetime import datetime, timedelta

import pandas as pd

from scripts.research.hypothesis_factory import run_raj_arora_hyp_b1_intersection_v11 as v11


def _bars(closes):
    start = datetime(2025, 1, 2, 9, 15)
    out = []
    for i, close in enumerate(closes):
        out.append({
            "timestamp": start + timedelta(minutes=5 * i),
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
        })
    return out


def test_downside_first_reclaim_detected():
    bars = _bars([100, 100, 98.0, 99.5, 100, 101, 102, 103, 104, 105, 106, 107])
    assert v11.find_failed_downside_reclaim(bars) == 3


def test_upside_first_rejected():
    bars = _bars([100, 100, 102.0, 98.0, 99.5, 100, 101])
    assert v11.find_failed_downside_reclaim(bars) is None


def test_reclaim_must_be_within_two_bars():
    bars = _bars([100, 100, 98.0, 98.1, 98.2, 99.5, 100, 101])
    assert v11.find_failed_downside_reclaim(bars) is None


def test_basis_is_sampled_at_completed_reclaim_bar_end():
    bars = _bars([100, 100, 98.0, 99.5, 100, 101, 102])
    start = pd.Timestamp("2025-01-02 09:15:00")
    rows = []
    for i in range(40):
        spot = 100.0
        basis = 5.0 + (9.0 if i >= 19 else 0.0)
        rows.append({
            "timestamp": start + pd.Timedelta(minutes=i),
            "session_date": "2025-01-02",
            "spot_close": spot,
            "futures_close": spot + basis,
        })
    panel = pd.DataFrame(rows)
    panel["raw_basis"] = panel["futures_close"] - panel["spot_close"]
    panel["basis_chg_15m"] = panel["raw_basis"].diff(15)
    got, reason = v11.basis_at_reclaim_end(
        "2025-01-02",
        bars,
        3,
        {"2025-01-02": panel},
        {"2025-01-02": start},
    )
    assert reason == "OK"
    assert got == 9.0


def test_top5_concentration_can_exceed_one_when_rest_loses():
    assert v11.top5_fraction([10.0, 8.0, 6.0, 3.0, 2.0, -4.0, -3.0]) > 1.0
