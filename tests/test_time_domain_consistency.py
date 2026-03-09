from __future__ import annotations

import json
from datetime import datetime, timezone

from config import config as cfg
import core.governance_gate as governance_gate
import core.readiness_gate as readiness_gate
import core.tick_store as tick_store
from core.time_sanity import check_market_data_time_sanity


def test_time_sanity_normalizes_millis_and_micros():
    result = check_market_data_time_sanity(
        ltp_ts_epoch=1_700_000_090_000.0,  # ms
        candle_ts_epoch=1_700_000_095_000_000.0,  # us
        market_open=True,
        require_live_quotes=True,
        max_ltp_age_sec=20.0,
        max_candle_age_sec=10.0,
        now_epoch=1_700_000_100.0,
    )
    assert result["ok"] is True
    assert abs(float(result["ltp_age_sec"]) - 10.0) < 1e-6
    assert abs(float(result["candle_age_sec"]) - 5.0) < 1e-6


def test_governance_auth_health_normalizes_epoch_units(monkeypatch):
    monkeypatch.setattr(
        governance_gate,
        "_read_last_jsonl",
        lambda _path: {
            "ok": True,
            "auth_state": "OK",
            "ts_epoch": 1_700_000_000_000.0,  # ms
        },
    )
    monkeypatch.setattr(cfg, "GOV_AUTH_MAX_AGE_SEC", 120.0, raising=False)
    payload = governance_gate._load_recent_auth_health(1_700_000_060.0)
    assert payload["ok"] is True
    assert abs(float(payload["age_sec"]) - 60.0) < 1e-6


def test_governance_snapshot_feed_health_converts_depth_epoch(monkeypatch):
    monkeypatch.setattr(cfg, "OFFHOURS_SLA_MAX_DEPTH_AGE_SEC", 900.0, raising=False)
    monkeypatch.setattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 6.0, raising=False)
    payload = governance_gate._snapshot_feed_health(
        market_data={
            "instrument": "OPT",
            "ltp_ts_epoch": 1_700_000_049.5,
            "depth_age_sec": 1_700_000_040_000.0,  # ms epoch, not age
        },
        now_epoch=1_700_000_050.0,
        market_open=True,
        mode="LIVE",
    )
    assert payload is not None
    depth_age = float((payload.get("depth") or {}).get("age_sec"))
    assert abs(depth_age - 10.0) < 1e-6


def test_readiness_decision_rows_normalize_epoch_and_reject_future_skew(monkeypatch, tmp_path):
    gate_file = tmp_path / "gate_status.jsonl"
    rows = [
        {
            "ts_epoch": 1_700_000_000_000.0,  # ms epoch -> valid
            "symbol": "NIFTY",
            "decision_stage": "N2_FEED_FRESH",
            "decision_blockers": [],
            "decision_explain": [],
        },
        {
            "ts_epoch": 1_700_000_090_000.0,  # ms epoch -> 40s future vs now
            "symbol": "BANKNIFTY",
            "decision_stage": "N2_FEED_FRESH",
            "decision_blockers": [],
            "decision_explain": [],
        },
    ]
    gate_file.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(readiness_gate, "gate_status_path", lambda desk_id=None: gate_file)
    monkeypatch.setattr(cfg, "READINESS_DECISION_MAX_AGE_SEC", 120.0, raising=False)
    monkeypatch.setattr(cfg, "MAX_CLOCK_SKEW_SEC", 5.0, raising=False)

    out = readiness_gate._load_recent_decision_rows(now_epoch=1_700_000_050.0)
    assert "NIFTY" in out
    assert "BANKNIFTY" not in out


def test_tick_store_to_epoch_naive_iso_matches_equivalent_epoch():
    # Naive timestamp strings must be interpreted consistently as UTC.
    iso_naive = "2026-03-04 09:20:00"
    epoch_expected = datetime(2026, 3, 4, 9, 20, tzinfo=timezone.utc).timestamp()
    parsed = tick_store._to_epoch(iso_naive)
    assert parsed is not None
    assert abs(float(parsed) - float(epoch_expected)) < 1e-6
