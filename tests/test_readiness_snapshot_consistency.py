from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import core.readiness_gate as readiness_gate
from core.readiness_state import ReadinessState


def _common_ok(monkeypatch):
    monkeypatch.setattr(readiness_gate.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(readiness_gate.risk_halt, "is_halted", lambda: False)
    monkeypatch.setattr(readiness_gate, "verify_audit_chain", lambda: (True, "ok", 0))
    monkeypatch.setattr(readiness_gate, "_check_kite_auth", lambda: (True, "ok", "OK"))
    monkeypatch.setattr(
        readiness_gate,
        "run_preopen_auth_warm_check",
        lambda **_kwargs: {"degrade_to_planning": False, "reason": "ok"},
    )
    monkeypatch.setattr(readiness_gate, "_check_trade_identity_schema", lambda: (True, "ok"))
    monkeypatch.setattr(readiness_gate, "_disk_free_gb", lambda _=".": 10.0)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_run_readiness_state_blocks_on_fresh_feed_runtime_failure(monkeypatch, tmp_path):
    _common_ok(monkeypatch)
    now_dt = datetime(2026, 2, 10, 10, 0, 0)
    monkeypatch.setattr(readiness_gate, "now_ist", lambda: now_dt)
    monkeypatch.setattr(readiness_gate, "is_market_open_ist", lambda now=None: True)
    monkeypatch.setattr(
        readiness_gate,
        "_decision_gate_health",
        lambda now_epoch, market_open, execution_mode=None: {
            "ok": True,
            "feed_ok": True,
            "blockers": [],
            "reasons": [],
            "symbols": ["NIFTY"],
            "allowed_symbols": ["NIFTY"],
            "blocked_symbols": [],
            "blockers_by_symbol": {"NIFTY": []},
            "rows": {},
            "ltp_age_sec": 0.4,
            "depth_age_sec": 0.9,
            "latest_explain": [],
        },
    )
    monkeypatch.setattr(readiness_gate, "get_feed_debug", lambda now_epoch=None: {})
    monkeypatch.setattr(readiness_gate.cfg, "READINESS_FEED_RUNTIME_MAX_AGE_SEC", 300.0, raising=False)
    monkeypatch.setattr(readiness_gate, "logs_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(readiness_gate, "runtime_dir", lambda: tmp_path / "runtime")

    _write_json(
        tmp_path / "logs" / "feed_runtime_latest.json",
        {
            "ts_epoch": now_dt.timestamp(),
            "ws_connected": False,
            "runtime_state": "SUBSCRIBE_FAILED",
            "intended_tokens_count": 74,
            "subscribed_option_tokens_count": 0,
            "option_feed_block_reason_by_symbol": {
                "NIFTY": "NO_LIVE_OPTION_FEED",
            },
        },
    )

    result = readiness_gate.run_readiness_state(write_log=False)
    assert result.state == ReadinessState.BLOCKED
    assert any(
        str(code).startswith("feed_health:") and "NO_LIVE_OPTION_FEED" in str(code)
        for code in result.blockers
    )
    snapshot = result.checks.get("feed_runtime_snapshot") or {}
    assert snapshot.get("present") is True
    assert "NO_LIVE_OPTION_FEED" in list(snapshot.get("derived_reasons") or [])


def test_log_state_transition_refreshes_state_file_without_transition(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness_gate, "logs_dir", lambda: tmp_path)

    payload1 = {
        "ts_epoch": 1000.0,
        "ts_ist": "2026-02-10T10:00:00+05:30",
        "state": "READY",
        "blockers": [],
        "warnings": [],
        "market_open": True,
        "checks": {
            "feed_runtime_snapshot": {
                "mtime_epoch": 500.0,
                "runtime_state": "OK",
                "ws_connected": True,
                "path": str(tmp_path / "feed_runtime_latest.json"),
                "age_sec": 0.2,
                "derived_reasons": [],
            }
        },
    }
    readiness_gate._log_state_transition(payload1)

    payload2 = {
        "ts_epoch": 1001.0,
        "ts_ist": "2026-02-10T10:00:01+05:30",
        "state": "READY",
        "blockers": [],
        "warnings": [],
        "market_open": True,
        "checks": {
            "feed_runtime_snapshot": {
                "mtime_epoch": 501.0,
                "runtime_state": "SUBSCRIBE_FAILED",
                "ws_connected": False,
                "path": str(tmp_path / "feed_runtime_latest.json"),
                "age_sec": 0.1,
                "derived_reasons": ["NO_LIVE_OPTION_FEED"],
            }
        },
    }
    readiness_gate._log_state_transition(payload2)

    state_path = tmp_path / "readiness_state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload.get("computed_at") == 1001.0
    assert payload.get("source_feed_runtime_state") == "SUBSCRIBE_FAILED"
    assert payload.get("source_ws_connected") is False
    assert payload.get("source_feed_mtime") == 501.0

    log_lines = (tmp_path / "readiness_state.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len([line for line in log_lines if line.strip()]) == 1


def test_load_or_recompute_readiness_state_recomputes_when_snapshot_is_stale(monkeypatch, tmp_path):
    logs = tmp_path / "logs"
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(readiness_gate, "logs_dir", lambda: logs)
    monkeypatch.setattr(readiness_gate, "runtime_dir", lambda: runtime)
    monkeypatch.setattr(readiness_gate.cfg, "READINESS_STATE_STALE_MARGIN_SEC", 0.0, raising=False)

    state_path = logs / "readiness_state.json"
    feed_path = logs / "feed_runtime_latest.json"
    _write_json(state_path, {"state": "READY", "can_trade": True})
    _write_json(feed_path, {"ts_epoch": 2000.0, "ws_connected": False, "runtime_state": "SUBSCRIBE_FAILED"})

    os.utime(state_path, (1000.0, 1000.0))
    os.utime(feed_path, (2000.0, 2000.0))

    monkeypatch.setattr(
        readiness_gate,
        "run_readiness_check",
        lambda write_log=True: {"state": "BLOCKED", "can_trade": False, "blockers": ["feed_health:NO_LIVE_OPTION_FEED"]},
    )

    payload = readiness_gate.load_or_recompute_readiness_state(write_log=False)
    assert payload.get("state") == "BLOCKED"
    assert payload.get("can_trade") is False
