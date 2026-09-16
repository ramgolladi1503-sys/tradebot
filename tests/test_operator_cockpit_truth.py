from pathlib import Path

from dashboard.operator_truth import pipeline_pulse
from core.upstox_ui_snapshot import build_option_chain_snapshot, write_snapshot_atomic


def test_pipeline_pulse_fails_closed_without_runtime_sources():
    rows = pipeline_pulse(feed_status="missing", risk_status="missing", market_state={}, metrics={})
    states = {row["stage"]: row["state"] for row in rows}
    assert states["KITE FEED"] == "BLOCKED"
    assert states["MARKET STATE"] == "BLOCKED"
    assert states["RISK"] == "BLOCKED"
    assert states["NORMALIZE"] == "UNKNOWN"


def test_upstox_snapshot_builder_keeps_ce_pe_at_same_strike(tmp_path: Path):
    payload = build_option_chain_snapshot(
        latest_by_key={
            "ce": {"ltp": 10.0, "bid": 9.9, "ask": 10.1, "received_epoch": 100.0},
            "pe": {"ltp": 12.0, "bid": 11.9, "ask": 12.1, "received_epoch": 101.0},
        },
        metadata_by_key={
            "ce": {"root": "NIFTY", "side": "CE", "strike": 25000, "expiry": "2026-09-22"},
            "pe": {"root": "NIFTY", "side": "PE", "strike": 25000, "expiry": "2026-09-22"},
        },
        subscribed_count=2,
        written_epoch=102.0,
    )
    row = payload["chains"]["NIFTY"]["rows"][0]
    assert row["ce_ltp"] == 10.0
    assert row["pe_ltp"] == 12.0
    assert payload["broker_write_authority"] is False
    assert payload["order_authority"] is False
    target = tmp_path / "snapshot.json"
    write_snapshot_atomic(target, payload)
    assert target.exists()
