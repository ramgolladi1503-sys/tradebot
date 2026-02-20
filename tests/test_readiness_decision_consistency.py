import json
from datetime import datetime

import core.readiness_gate as readiness_gate
from core.readiness_state import ReadinessState


def _patch_common_ok(monkeypatch):
    monkeypatch.setattr(readiness_gate.risk_halt, "is_halted", lambda: False)
    monkeypatch.setattr(readiness_gate, "verify_audit_chain", lambda: (True, "ok", 0))
    monkeypatch.setattr(readiness_gate, "_check_kite_auth", lambda: (True, "ok", "OK"))
    monkeypatch.setattr(readiness_gate, "_check_trade_identity_schema", lambda: (True, "ok"))
    monkeypatch.setattr(readiness_gate, "_disk_free_gb", lambda _=".": 10.0)
    monkeypatch.setattr(readiness_gate, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(readiness_gate, "now_ist", lambda: datetime(2026, 2, 10, 10, 0, 0))
    monkeypatch.setattr(readiness_gate, "is_market_open_ist", lambda now=None: True)


def test_readiness_cannot_be_ready_when_any_decision_has_feed_stale(monkeypatch, tmp_path):
    _patch_common_ok(monkeypatch)
    monkeypatch.setattr(readiness_gate.cfg, "READINESS_REQUIRE_DECISION_GATE", True, raising=False)
    now_epoch = datetime(2026, 2, 10, 10, 0, 0).timestamp()

    gate_file = tmp_path / "gate_status.jsonl"
    monkeypatch.setattr(readiness_gate, "gate_status_path", lambda desk_id=None: gate_file)

    rows = [
        {
            "ts_epoch": now_epoch - 2.0,
            "symbol": "NIFTY",
            "decision_stage": "N9_FINAL_DECISION",
            "decision_blockers": [],
            "decision_explain": [],
            "gate_allowed": True,
            "feed_health_snapshot": {"is_fresh": True, "ltp_age_sec": 0.1, "depth_age_sec": 0.2},
        },
        {
            "ts_epoch": now_epoch - 1.0,
            "symbol": "BANKNIFTY",
            "decision_stage": "N2_FEED_FRESH",
            "decision_blockers": ["FEED_STALE"],
            "decision_explain": [],
            "gate_allowed": False,
            "feed_health_snapshot": {"is_fresh": False, "ltp_age_sec": 12.0, "depth_age_sec": 0.1},
        },
        # Non-decision row must be ignored by readiness.
        {
            "ts_epoch": now_epoch,
            "symbol": "NIFTY",
            "stage": "trade_builder_gate",
            "gate_allowed": False,
            "gate_reasons": ["missing_live_bidask"],
        },
    ]
    gate_file.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    result = readiness_gate.run_readiness_state(write_log=False)
    assert result.state == ReadinessState.BLOCKED
    assert result.can_trade is False
    assert "decision_gate_blocked" in result.blockers
    assert any(str(reason).startswith("feed_health:feed_stale:") for reason in result.blockers)
