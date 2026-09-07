from __future__ import annotations

import pandas as pd
import pytest

from research.macd_futures_participation_regime_v1.analysis import (
    CampaignBlocked,
    bind_macd_ledgers,
    build_basis_state,
    prepare_interaction,
    signal_state_support,
    summarize_interaction,
)


def _aligned() -> pd.DataFrame:
    ts = pd.date_range(
        "2026-01-05 09:15",
        periods=80,
        freq="min",
        tz="Asia/Kolkata",
    )
    spot = pd.Series(range(80), dtype=float) + 25000
    basis = pd.Series([0.0] * 16 + [float(i - 15) for i in range(16, 80)])
    return pd.DataFrame(
        {
            "timestamp": ts,
            "session_date": "2026-01-05",
            "spot_close": spot,
            "futures_close": spot + basis,
        }
    )


def test_h1_literal_state_uses_strict_8_5_threshold():
    state = build_basis_state(_aligned())
    assert state["h1_active"].any()
    active = state[state["h1_active"]]
    assert (active["basis_chg_15m"] > 8.5).all()


def test_bind_and_pair_reuses_existing_payoffs():
    state = build_basis_state(_aligned())
    active_ts = state.loc[state["h1_active"], "timestamp"].iloc[0]
    inactive_ts = state.loc[
        state["h1_active"] == False, "timestamp"  # noqa: E712
    ].iloc[0]
    entry_ts = active_ts + pd.Timedelta(minutes=15)

    assignments = pd.DataFrame(
        [
            {
                "replication_id": 1,
                "signal_trade_id": "S1",
                "signal_origin": active_ts,
                "matched_placebo_origin": active_ts,
            },
            {
                "replication_id": 2,
                "signal_trade_id": "S1",
                "signal_origin": active_ts,
                "matched_placebo_origin": inactive_ts,
            },
        ]
    )
    signals = pd.DataFrame(
        [{"trade_id": "S1", "entry_timestamp": entry_ts, "net_6bps": 12.0}]
    )
    placebo = pd.DataFrame(
        [
            {
                "replication_id": 1,
                "origin_timestamp": active_ts,
                "net_6bps": -2.0,
            },
            {
                "replication_id": 2,
                "origin_timestamp": inactive_ts,
                "net_6bps": 50.0,
            },
        ]
    )
    sig, ass = bind_macd_ledgers(assignments, signals, placebo)
    ps = prepare_interaction(sig, ass, state, "h1_active")
    assert len(ps) == 1
    assert ps.iloc[0]["compatible_placebo_n"] == 1
    assert ps.iloc[0]["delta_net_6bps"] == pytest.approx(14.0)


def test_duplicate_placebo_key_blocks():
    t = pd.Timestamp("2026-01-05 10:00", tz="Asia/Kolkata")
    assignments = pd.DataFrame(
        [
            {
                "replication_id": 1,
                "signal_trade_id": "S1",
                "signal_origin": t,
                "matched_placebo_origin": t,
            }
        ]
    )
    signals = pd.DataFrame(
        [{"trade_id": "S1", "entry_timestamp": t, "net_6bps": 1.0}]
    )
    placebo = pd.DataFrame(
        [
            {"replication_id": 1, "origin_timestamp": t, "net_6bps": 0.0},
            {"replication_id": 1, "origin_timestamp": t, "net_6bps": 1.0},
        ]
    )
    with pytest.raises(CampaignBlocked, match="PLACEBO_PAYOFF_DUPLICATE_KEY"):
        bind_macd_ledgers(assignments, signals, placebo)


def test_summary_is_descriptive_and_does_not_certify_edge():
    per_signal = pd.DataFrame(
        {
            "signal_trade_id": ["A", "B"],
            "signal_origin": pd.to_datetime(
                ["2026-01-05 10:00", "2026-01-06 10:00"]
            ).tz_localize("Asia/Kolkata"),
            "signal_session_date": ["2026-01-05", "2026-01-06"],
            "signal_state": [True, False],
            "signal_net_6bps": [10.0, 2.0],
            "compatible_placebo_n": [100, 100],
            "placebo_mean_net_6bps": [-2.0, 1.0],
            "delta_net_6bps": [12.0, 1.0],
        }
    )
    out = summarize_interaction(per_signal)
    assert out["active_signal_sessions"] == 1
    assert "structural_edge_certified" not in out


def test_signal_state_support_is_pre_payoff_and_counts_sessions():
    state = build_basis_state(_aligned())
    active_ts = state.loc[
        state["h1_active"] == True, "timestamp"  # noqa: E712
    ].iloc[0]
    signals = pd.DataFrame(
        [
            {
                "trade_id": "S1",
                "signal_trade_id": "S1",
                "signal_origin": active_ts,
                "entry_timestamp": active_ts + pd.Timedelta(minutes=15),
                "net_6bps": 9999.0,
            }
        ]
    )
    support = signal_state_support(signals, state, "h1_active")
    assert support["active_signal_sessions"] == 1
    assert support["support_gate_pass"] is False


def test_unknown_trailing_state_blocks_exact_membership():
    state = build_basis_state(_aligned())
    early_ts = state["timestamp"].iloc[0]
    signals = pd.DataFrame(
        [
            {
                "trade_id": "S0",
                "signal_trade_id": "S0",
                "signal_origin": early_ts,
                "entry_timestamp": early_ts + pd.Timedelta(minutes=15),
                "net_6bps": 0.0,
            }
        ]
    )
    with pytest.raises(CampaignBlocked, match="STATE_UNAVAILABLE"):
        signal_state_support(signals, state, "h1_active")
