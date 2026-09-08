from __future__ import annotations

import pandas as pd

from research.macd_futures_participation_regime_v1.oracle import (
    reconstruct_per_signal,
    reconstruct_state,
    verify_primary_output,
)


def _aligned() -> pd.DataFrame:
    ts = pd.date_range(
        "2026-01-05 09:15", periods=100, freq="min", tz="Asia/Kolkata"
    )
    spot = pd.Series(range(100), dtype=float) + 25000.0
    basis = pd.Series([0.0] * 20 + [float(i - 19) for i in range(20, 100)])
    return pd.DataFrame(
        {
            "timestamp": ts,
            "session_date": "2026-01-05",
            "spot_close": spot,
            "futures_close": spot + basis,
        }
    )


def _inputs():
    aligned = _aligned()
    state = reconstruct_state(aligned, "H1")
    active = state[state["oracle_state"] == True]["timestamp"].tolist()  # noqa: E712
    assert len(active) >= 2
    signal_origin = active[0]
    placebo_origin = active[1]
    assignments = pd.DataFrame(
        [
            {
                "replication_id": 1,
                "signal_trade_id": "S1",
                "signal_origin": signal_origin,
                "matched_placebo_origin": placebo_origin,
            }
        ]
    )
    signal = pd.DataFrame([{"trade_id": "S1", "net_6bps": 12.0}])
    placebo = pd.DataFrame(
        [
            {
                "replication_id": 1,
                "origin_timestamp": placebo_origin,
                "net_6bps": -2.0,
            }
        ]
    )
    return aligned, assignments, signal, placebo


def test_independent_oracle_reconstructs_primary_pairing():
    aligned, assignments, signal, placebo = _inputs()
    primary = reconstruct_per_signal(aligned, assignments, signal, placebo, "H1")
    result = verify_primary_output(
        aligned, assignments, signal, placebo, primary, "H1"
    )
    assert result["verdict"] == "PASS"
    assert result["mismatch_count"] == 0
    assert result["imports_primary_state_builder"] is False
    assert result["imports_primary_pairing_builder"] is False


def test_independent_oracle_detects_delta_mutation():
    aligned, assignments, signal, placebo = _inputs()
    primary = reconstruct_per_signal(aligned, assignments, signal, placebo, "H1")
    primary.loc[0, "delta_net_6bps"] += 0.5
    result = verify_primary_output(
        aligned, assignments, signal, placebo, primary, "H1"
    )
    assert result["verdict"] == "FAIL"
    assert result["mismatch_count"] == 1
    assert result["mismatches_first_20"][0]["reason"] == "DELTA_NET_6BPS_MISMATCH"
