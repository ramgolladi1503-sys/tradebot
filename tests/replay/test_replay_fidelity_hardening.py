#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from core.candidate_audits.intraday_opening_drive import IST_TZ, CANDIDATE_ID as OPENING_DRIVE_ID
from core.replay.governed_market_replay import (
    DualReplayReconciler,
    GovernedMarketReplayEngine,
    ReplayEvent,
    ReplayMode,
    UpstoxTickReplaySource,
    assess_opening_drive_replay_capability,
)


def test_upstox_loader_never_fabricates_depth_qty_or_latency(tmp_path: Path):
    t = datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ)
    p = tmp_path / "ticks.parquet"
    pd.DataFrame([{
        "ts": t.timestamp(),
        "token": "x",
        "symbol": "NIFTY 25050 CE 24 SEP 26",
        "ltp": 121.0,
        "bid": 120.0,
        "ask": 122.0,
        "depth": "{not-json}",
    }]).to_parquet(p, index=False)

    events = list(UpstoxTickReplaySource(p).stream_events())
    assert len(events) == 1
    d = events[0].symbol_data
    assert d["bid_qty"] is None
    assert d["ask_qty"] is None
    assert d["option_last_tick_age_sec"] is None
    assert d["receipt_timestamp_authority"] == "UNAVAILABLE"
    assert d["depth_quantity_authority"] == "UNAVAILABLE"


def test_upstox_loader_uses_recorded_receipt_latency_when_present(tmp_path: Path):
    src = datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ)
    receipt = src + timedelta(milliseconds=275)
    p = tmp_path / "ticks.parquet"
    pd.DataFrame([{
        "ts": src.timestamp(),
        "received_epoch": receipt.timestamp(),
        "token": "x",
        "symbol": "NIFTY 25050 CE 24 SEP 26",
        "ltp": 121.0,
        "bid": 120.0,
        "ask": 122.0,
        "depth": '{"bids":[{"quantity":11}],"asks":[{"quantity":13}]}',
    }]).to_parquet(p, index=False)

    ev = list(UpstoxTickReplaySource(p).stream_events())[0]
    assert ev.available_timestamp_ist == receipt
    assert ev.symbol_data["bid_qty"] == 11
    assert ev.symbol_data["ask_qty"] == 13
    assert ev.symbol_data["receipt_timestamp_authority"] == "RECORDED"
    assert ev.symbol_data["option_last_tick_age_sec"] == pytest.approx(0.275, abs=1e-6)


def test_opening_drive_capability_blocks_manual_priming_when_primitives_missing():
    t = datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ)
    option_only = [ReplayEvent(
        event_timestamp_ist=t,
        available_timestamp_ist=t,
        symbol_data={
            "symbol": "NIFTY 25050 CE 24 SEP 26",
            "instrument_type": "OPT",
            "segment": "NFO-OPT",
        },
    )]
    report = assess_opening_drive_replay_capability(option_only)
    assert report.full_end_to_end_available is False
    assert "FUTURES_0915_BAR" in report.missing_primitives
    assert "FUTURES_0920_BAR" in report.missing_primitives
    assert "SPOT_0920_BAR" in report.missing_primitives


def test_independent_reconciliation_calls_frozen_reference_runner(tmp_path: Path, monkeypatch):
    session_date = "2026-09-22"
    prev_key = "NIFTY26SEPFUT"

    prev_df = pd.DataFrame([{
        "date": "2026-09-21",
        "time_str": "15:29:00",
        "open": 24995.0,
        "close": 25000.0,
        "selected_futures_contract_key": prev_key,
    }])
    curr_df = pd.DataFrame([
        {"date": session_date, "time_str": "09:15:00", "open": 25050.0, "close": 25055.0, "selected_futures_contract_key": prev_key},
        {"date": session_date, "time_str": "09:20:00", "open": 25070.0, "close": 25080.0, "selected_futures_contract_key": prev_key},
        {"date": session_date, "time_str": "09:21:00", "open": 25078.0, "close": 25082.0, "selected_futures_contract_key": prev_key},
        {"date": session_date, "time_str": "11:00:00", "open": 25100.0, "close": 25120.0, "selected_futures_contract_key": prev_key},
    ])

    day = tmp_path / session_date
    day.mkdir(parents=True)
    pd.DataFrame([{
        "symbol": "NIFTY 50",
        "timestamp": f"{session_date} 09:20:00+05:30",
        "close": 25065.0,
    }]).to_parquet(day / "indices_1m_20260922.parquet", index=False)

    entry_t = datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ)
    exit_t = datetime(2026, 9, 22, 11, 1, 5, tzinfo=IST_TZ)
    option_symbol = "NIFTY 25050 CE 24 SEP 26"
    pd.DataFrame([
        {"symbol": option_symbol, "ts": entry_t.timestamp(), "bid": 120.0, "ask": 122.0},
        {"symbol": option_symbol, "ts": exit_t.timestamp(), "bid": 145.0, "ask": 147.0},
    ]).to_parquet(day / "upstox_full_ticks_20260922_stitched.parquet", index=False)

    import core.paper_shadow.run_intraday_opening_drive_shadow as refmod
    monkeypatch.setattr(refmod, "get_authoritative_option_lot_size", lambda symbol: (65, "TEST_AUTHORITY"))

    events = [
        ReplayEvent(
            event_timestamp_ist=datetime(2026,9,22,9,15,tzinfo=IST_TZ),
            available_timestamp_ist=datetime(2026,9,22,9,16,tzinfo=IST_TZ),
            symbol_data={"symbol":prev_key,"instrument_type":"FUT","segment":"NFO-FUT","selected_futures_contract_key":prev_key,
                         "bar_open":25050.0,"bar_close":25055.0,"bar_timestamp_epoch":datetime(2026,9,22,9,15,tzinfo=IST_TZ).timestamp(),
                         "exchange_timestamp":datetime(2026,9,22,9,16,tzinfo=IST_TZ).isoformat(),"option_last_tick_age_sec":0.05},
        ),
        ReplayEvent(
            event_timestamp_ist=datetime(2026,9,22,9,20,tzinfo=IST_TZ),
            available_timestamp_ist=datetime(2026,9,22,9,21,tzinfo=IST_TZ),
            symbol_data={"symbol":prev_key,"instrument_type":"FUT","segment":"NFO-FUT","selected_futures_contract_key":prev_key,
                         "bar_open":25070.0,"bar_close":25080.0,"bar_timestamp_epoch":datetime(2026,9,22,9,20,tzinfo=IST_TZ).timestamp(),
                         "exchange_timestamp":datetime(2026,9,22,9,21,tzinfo=IST_TZ).isoformat(),"option_last_tick_age_sec":0.05},
        ),
        ReplayEvent(
            event_timestamp_ist=datetime(2026,9,22,9,20,tzinfo=IST_TZ),
            available_timestamp_ist=datetime(2026,9,22,9,21,tzinfo=IST_TZ),
            symbol_data={"symbol":"NIFTY 50","instrument_type":"INDEX","segment":"INDICES",
                         "bar_open":25060.0,"bar_close":25065.0,"bar_timestamp_epoch":datetime(2026,9,22,9,20,tzinfo=IST_TZ).timestamp(),
                         "exchange_timestamp":datetime(2026,9,22,9,21,tzinfo=IST_TZ).isoformat(),"option_last_tick_age_sec":0.05},
        ),
        ReplayEvent(
            event_timestamp_ist=entry_t, available_timestamp_ist=entry_t,
            symbol_data={"symbol":option_symbol,"instrument_type":"OPT","segment":"NFO-OPT","underlying":"NIFTY",
                         "strike_price":25050.0,"option_type":"CE","expiry":"24 SEP 26",
                         "best_bid":120.0,"best_ask":122.0,"bid_qty":10,"ask_qty":10,
                         "exchange_timestamp":entry_t.isoformat(),"option_last_tick_age_sec":0.05},
        ),
        ReplayEvent(
            event_timestamp_ist=exit_t, available_timestamp_ist=exit_t,
            symbol_data={"symbol":option_symbol,"instrument_type":"OPT","segment":"NFO-OPT","underlying":"NIFTY",
                         "strike_price":25050.0,"option_type":"CE","expiry":"24 SEP 26",
                         "best_bid":145.0,"best_ask":147.0,"bid_qty":10,"ask_qty":10,
                         "exchange_timestamp":exit_t.isoformat(),"option_last_tick_age_sec":0.05},
        ),
    ]

    engine = GovernedMarketReplayEngine(
        session_id="RECON",
        source_sha="test",
        evidence_root=tmp_path / "evidence",
        mode=ReplayMode.EXACT_REPLAY,
        opening_drive_prev_contract_key=prev_key,
        opening_drive_prev_close_1529=25000.0,
        opening_drive_target_expiry="24 SEP 26",
    )
    summary = engine.replay_session(events)
    assert len(summary.observations_captured) == 1
    online = summary.observations_captured[0]

    matched, discrepancies, reference = DualReplayReconciler.reconcile_opening_drive_against_reference_runner(
        online_obs=online,
        prev_session_df=prev_df,
        curr_session_df=curr_df,
        capture_dir=str(tmp_path),
    )
    assert reference is not None
    assert matched is True, discrepancies
