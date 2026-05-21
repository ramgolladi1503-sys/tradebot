from __future__ import annotations

import json
import os

from core.ws_status_provenance_report import build_ws_status_provenance_report


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_text(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_provenance_reports_fresh_ws_attempt_failed_when_proof_and_failure_exist(tmp_path):
    engine = _write_json(
        tmp_path / "engine_cycle_status.json",
        {
            "auth_state": "AUTH_REQUIRED",
            "auth_ok": False,
            "auth_reason": "WebSocket connection upgrade failed (403 - Forbidden)",
            "feed_ok": False,
            "ws_connected": False,
            "ts_epoch": 1000.0,
        },
    )
    suggestions = _write_json(
        tmp_path / "suggestions_status.json",
        {
            "status": "blocked",
            "primary_blocker": "AUTH_REQUIRED",
            "auth_reason": "WebSocket connection upgrade failed (403 - Forbidden)",
            "ts_epoch": 1000.0,
        },
    )
    runtime = _write_json(tmp_path / "runtime_health_latest.json", {"feed": {"feed_ok": False, "ws_connected": False}})
    feed = _write_json(tmp_path / "feed_runtime_latest.json", {"runtime_state": "AUTH_BLOCKED", "ws_connected": False})
    auth_events = _write_text(tmp_path / "auth_events.jsonl", "")
    auth_health = _write_text(tmp_path / "auth_health.jsonl", "")
    depth_log = _write_text(tmp_path / "depth_ws_watchdog.log", "")
    paper_log = _write_text(
        tmp_path / "paper_ws_proof.log",
        "\n".join(
            [
                "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF public_key_tail4=oi2n access_token_tail4=R7J6",
                "kite_ws_created public_key_tail4=oi2n access_token_tail4=R7J6",
                "FEED_WS_AUTH_FAILURE_PROOF code=1006 reason=403",
                "WebSocket connection upgrade failed (403 - Forbidden)",
            ]
        ),
    )
    startup = _write_text(tmp_path / "startup_recovery.jsonl", "")

    report = build_ws_status_provenance_report(
        engine_status_path=engine,
        suggestions_status_path=suggestions,
        runtime_health_path=runtime,
        feed_runtime_path=feed,
        auth_health_path=auth_health,
        auth_events_path=auth_events,
        depth_log_path=depth_log,
        paper_log_path=paper_log,
        startup_recovery_path=startup,
        now_epoch=1010.0,
    )

    assert report["observed_runtime_path"]["fresh_process_reached_start_depth_ws"] is True
    assert report["observed_runtime_path"]["handshake_proof_seen"] is True
    assert report["observed_runtime_path"]["auth_failure_proof_seen"] is True
    assert report["decision"]["primary_conclusion"] == "fresh_ws_attempt_failed"
    assert report["decision"]["safe_to_treat_status_as_fresh_ws_failure"] is True


def test_provenance_reports_status_without_fresh_ws_attempt(tmp_path):
    engine = _write_json(
        tmp_path / "engine_cycle_status.json",
        {
            "auth_state": "AUTH_REQUIRED",
            "auth_ok": False,
            "auth_reason": "WebSocket connection upgrade failed (403 - Forbidden)",
            "feed_ok": False,
            "ws_connected": True,
            "ts_epoch": 1000.0,
        },
    )
    suggestions = _write_json(
        tmp_path / "suggestions_status.json",
        {
            "status": "blocked",
            "primary_blocker": "AUTH_REQUIRED",
            "auth_reason": "WebSocket connection upgrade failed (403 - Forbidden)",
            "ts_epoch": 1000.0,
        },
    )
    runtime = _write_json(tmp_path / "runtime_health_latest.json", {"feed": {"feed_ok": False, "ws_connected": None}})
    feed = _write_json(tmp_path / "feed_runtime_latest.json", {"runtime_state": "RUNNING", "ws_connected": True})
    auth_events = _write_text(tmp_path / "auth_events.jsonl", "")
    auth_health = _write_text(tmp_path / "auth_health.jsonl", "")
    depth_log = _write_text(tmp_path / "depth_ws_watchdog.log", "old feed log with no proof")
    paper_log = _write_text(tmp_path / "paper_ws_proof.log", "BOOT\nexec_mode=PAPER\nPHASE2 no input\n")
    startup = _write_text(tmp_path / "startup_recovery.jsonl", "")

    for path in (engine, suggestions, runtime, feed, paper_log):
        os.utime(path, (1000.0, 1000.0))
    os.utime(depth_log, (700.0, 700.0))

    report = build_ws_status_provenance_report(
        engine_status_path=engine,
        suggestions_status_path=suggestions,
        runtime_health_path=runtime,
        feed_runtime_path=feed,
        auth_health_path=auth_health,
        auth_events_path=auth_events,
        depth_log_path=depth_log,
        paper_log_path=paper_log,
        startup_recovery_path=startup,
        now_epoch=1010.0,
    )

    assert report["observed_runtime_path"]["fresh_process_reached_start_depth_ws"] is False
    assert report["observed_runtime_path"]["handshake_proof_seen"] is False
    assert report["decision"]["primary_conclusion"] == "status_written_without_fresh_ws_attempt"
    assert report["decision"]["safe_to_treat_status_as_fresh_ws_failure"] is False


def test_provenance_reports_stale_status_reused_when_depth_and_paper_logs_are_old(tmp_path):
    engine = _write_json(
        tmp_path / "engine_cycle_status.json",
        {
            "auth_state": "AUTH_REQUIRED",
            "auth_reason": "WebSocket connection upgrade failed (403 - Forbidden)",
            "ts_epoch": 800.0,
        },
    )
    suggestions = _write_json(
        tmp_path / "suggestions_status.json",
        {
            "status": "blocked",
            "primary_blocker": "AUTH_REQUIRED",
            "auth_reason": "WebSocket connection upgrade failed (403 - Forbidden)",
            "ts_epoch": 800.0,
        },
    )
    runtime = _write_json(tmp_path / "runtime_health_latest.json", {})
    feed = _write_json(tmp_path / "feed_runtime_latest.json", {})
    auth_events = _write_text(tmp_path / "auth_events.jsonl", "")
    auth_health = _write_text(tmp_path / "auth_health.jsonl", "")
    depth_log = _write_text(tmp_path / "depth_ws_watchdog.log", "old log")
    paper_log = _write_text(tmp_path / "paper_ws_proof.log", "old paper log")
    startup = _write_text(tmp_path / "startup_recovery.jsonl", "")

    for path in (engine, suggestions, runtime, feed, depth_log, paper_log, startup):
        os.utime(path, (800.0, 800.0))

    report = build_ws_status_provenance_report(
        engine_status_path=engine,
        suggestions_status_path=suggestions,
        runtime_health_path=runtime,
        feed_runtime_path=feed,
        auth_health_path=auth_health,
        auth_events_path=auth_events,
        depth_log_path=depth_log,
        paper_log_path=paper_log,
        startup_recovery_path=startup,
        now_epoch=1200.0,
    )

    assert report["file_freshness"]["paper_log"]["fresh"] is False
    assert report["file_freshness"]["depth_log"]["fresh"] is False
    assert report["decision"]["primary_conclusion"] == "stale_status_reused"
