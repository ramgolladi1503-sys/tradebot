import json
import logging
from datetime import datetime

import core.readiness_gate as readiness_gate
from core.readiness_state import ReadinessState
from core.telemetry_streams import decisions_stream_path


def _patch_common_ok(monkeypatch):
    monkeypatch.setattr(readiness_gate.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(readiness_gate.risk_halt, "is_halted", lambda: False)
    monkeypatch.setattr(readiness_gate, "verify_audit_chain", lambda: (True, "ok", 0))
    monkeypatch.setattr(readiness_gate, "_check_kite_auth", lambda: (True, "ok", "OK"))
    monkeypatch.setattr(readiness_gate, "_check_trade_identity_schema", lambda: (True, "ok"))
    monkeypatch.setattr(readiness_gate, "_disk_free_gb", lambda _=".": 10.0)
    monkeypatch.setattr(
        readiness_gate,
        "feed_breaker_maybe_auto_clear",
        lambda _state=None: {"tripped": False, "cleared": False, "reason": None},
    )
    monkeypatch.setattr(readiness_gate, "now_ist", lambda: datetime(2026, 2, 10, 10, 0, 0))
    monkeypatch.setattr(readiness_gate, "is_market_open_ist", lambda now=None: True)


def test_readiness_cannot_be_ready_when_any_decision_has_feed_stale(monkeypatch, tmp_path):
    _patch_common_ok(monkeypatch)
    monkeypatch.setattr(readiness_gate.cfg, "READINESS_REQUIRE_DECISION_GATE", True, raising=False)
    now_epoch = datetime(2026, 2, 10, 10, 0, 0).timestamp()

    gate_file = tmp_path / "gate_status.jsonl"
    monkeypatch.setattr(readiness_gate, "gate_status_path", lambda desk_id=None: gate_file)
    monkeypatch.setattr(readiness_gate, "decisions_stream_path", lambda desk_id=None: tmp_path / "decisions.jsonl")

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
    assert "decision_gate_missing" not in result.blockers
    assert any(str(reason).startswith("feed_health:feed_stale:") for reason in result.blockers)


def test_readiness_logs_feed_stale_evidence_from_decision_rows(monkeypatch, tmp_path, caplog):
    _patch_common_ok(monkeypatch)
    monkeypatch.setattr(readiness_gate.cfg, "READINESS_REQUIRE_DECISION_GATE", True, raising=False)
    monkeypatch.setattr(readiness_gate.cfg, "FEED_STALE_EVIDENCE_LOG_ENABLE", True, raising=False)
    now_epoch = datetime(2026, 2, 10, 10, 0, 0).timestamp()

    gate_file = tmp_path / "gate_status.jsonl"
    monkeypatch.setattr(readiness_gate, "gate_status_path", lambda desk_id=None: gate_file)
    monkeypatch.setattr(readiness_gate, "decisions_stream_path", lambda desk_id=None: tmp_path / "decisions.jsonl")

    rows = [
        {
            "ts_epoch": now_epoch - 1.0,
            "symbol": "BANKNIFTY",
            "decision_stage": "N2_FEED_FRESH",
            "decision_blockers": ["FEED_STALE"],
            "decision_explain": [],
            "gate_allowed": False,
            "feed_health_snapshot": {"is_fresh": False, "ltp_age_sec": 12.0, "depth_age_sec": 0.1},
        }
    ]
    gate_file.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    caplog.set_level(logging.WARNING, logger="core.readiness_gate")
    result = readiness_gate.run_readiness_state(write_log=False)
    assert result.state == ReadinessState.BLOCKED
    assert "FEED_STALE_EVIDENCE symbol=BANKNIFTY source=readiness_decision_rows" in caplog.text


def test_readiness_blocks_on_quote_invalid_without_feed_stale(monkeypatch, tmp_path):
    _patch_common_ok(monkeypatch)
    monkeypatch.setattr(readiness_gate.cfg, "READINESS_REQUIRE_DECISION_GATE", True, raising=False)
    now_epoch = datetime(2026, 2, 10, 10, 0, 0).timestamp()

    gate_file = tmp_path / "gate_status.jsonl"
    monkeypatch.setattr(readiness_gate, "gate_status_path", lambda desk_id=None: gate_file)
    monkeypatch.setattr(readiness_gate, "decisions_stream_path", lambda desk_id=None: tmp_path / "decisions.jsonl")

    rows = [
        {
            "ts_epoch": now_epoch - 1.0,
            "symbol": "NIFTY",
            "decision_stage": "N4_QUOTE_OK",
            "decision_blockers": ["QUOTE_INVALID"],
            "decision_explain": [],
            "gate_allowed": False,
            "feed_health_snapshot": {"is_fresh": True, "ltp_age_sec": 0.2, "depth_age_sec": None},
        }
    ]
    gate_file.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    result = readiness_gate.run_readiness_state(write_log=False)
    assert result.state == ReadinessState.READY
    assert result.can_trade is True
    assert "decision_gate_missing" not in result.blockers
    assert not any(str(reason).startswith("feed_health:feed_stale:") for reason in result.blockers)


def test_readiness_reports_insufficient_sample_when_no_decision_evaluations(monkeypatch, tmp_path):
    _patch_common_ok(monkeypatch)
    monkeypatch.setattr(readiness_gate.cfg, "READINESS_REQUIRE_DECISION_GATE", True, raising=False)

    gate_file = tmp_path / "gate_status.jsonl"
    monkeypatch.setattr(readiness_gate, "gate_status_path", lambda desk_id=None: gate_file)
    monkeypatch.setattr(readiness_gate, "decisions_stream_path", lambda desk_id=None: tmp_path / "decisions.jsonl")
    gate_file.write_text("", encoding="utf-8")

    result = readiness_gate.run_readiness_state(write_log=False)
    decision_gate = dict(result.checks.get("decision_gate") or {})
    assert decision_gate.get("status") == "INSUFFICIENT_SAMPLE"
    assert decision_gate.get("reason") == "DECISION_ROWS_STALE_OR_MISSING"
    assert "decision_engine_inactive" not in result.blockers


def test_readiness_in_sim_does_not_block_on_missing_decisions(monkeypatch, tmp_path):
    _patch_common_ok(monkeypatch)
    monkeypatch.setattr(readiness_gate.cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(readiness_gate.cfg, "READINESS_REQUIRE_DECISION_GATE", True, raising=False)

    gate_file = tmp_path / "gate_status.jsonl"
    monkeypatch.setattr(readiness_gate, "gate_status_path", lambda desk_id=None: gate_file)
    monkeypatch.setattr(readiness_gate, "decisions_stream_path", lambda desk_id=None: tmp_path / "decisions.jsonl")
    gate_file.write_text("", encoding="utf-8")

    result = readiness_gate.run_readiness_state(write_log=False)
    assert "decision_engine_inactive" not in result.blockers


def test_readiness_marks_decision_engine_active_from_decisions_stream(monkeypatch, tmp_path):
    _patch_common_ok(monkeypatch)
    monkeypatch.setattr(readiness_gate.cfg, "READINESS_REQUIRE_DECISION_GATE", True, raising=False)
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setattr(readiness_gate.cfg, "DESK_ID", "DEFAULT", raising=False)

    path = decisions_stream_path("DEFAULT")
    monkeypatch.setattr(readiness_gate, "decisions_stream_path", lambda desk_id=None: path)
    path.parent.mkdir(parents=True, exist_ok=True)
    now_epoch = datetime(2026, 2, 10, 10, 0, 0).timestamp()
    payload = {
        "event_type": "decision_evaluated",
        "candidate_id": "cand_test",
        "symbol": "NIFTY",
        "allowed": False,
        "decision_stage": "N4_QUOTE_OK",
        "blockers": ["QUOTE_INVALID"],
        "ts_epoch": now_epoch - 1.0,
        "ts_ist": "2026-02-10T10:00:00+05:30",
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    result = readiness_gate.run_readiness_state(write_log=False)
    decision_gate = dict(result.checks.get("decision_gate") or {})
    assert decision_gate.get("decision_engine_active") is True
    assert "decision_engine_inactive" not in result.blockers
