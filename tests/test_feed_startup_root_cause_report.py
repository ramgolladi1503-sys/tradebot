from __future__ import annotations

import json
import os

from core.feed_startup_root_cause_report import build_feed_startup_root_cause_report


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def test_report_detects_ws_rejected_validated_credentials(tmp_path, monkeypatch):
    token = tmp_path / "kite_access_token"
    token.write_text("token-1234567890-R7J6", encoding="utf-8")
    runtime_health = _write_json(tmp_path / "runtime_health_latest.json", {"mode": "PAPER", "feed": {"ws_connected": False, "subscribed_option_tokens_count": 0}})
    feed_runtime = _write_json(tmp_path / "feed_runtime_latest.json", {"runtime_state": "RUNNING", "ws_connected": True, "subscribed_option_tokens_count": 0})
    engine_status = _write_json(
        tmp_path / "engine_cycle_status.json",
        {
            "market_mode": "PAPER",
            "auth_ok": False,
            "auth_state": "AUTH_REQUIRED",
            "auth_reason": "code=1006 connection was closed uncleanly (WebSocket connection upgrade failed (403 - Forbidden))",
            "feed_ok": False,
            "subscribed_option_tokens_count": 0,
        },
    )
    auth_health = _write_jsonl(
        tmp_path / "auth_health.jsonl",
        [{"ok": True, "auth_state": "OK", "source": "live", "access_token_tail4": "R7J6", "api_key_tail4": "oi2n", "ts_epoch": 2000.0}],
    )
    ws_events = _write_jsonl(
        tmp_path / "depth_ws_events.jsonl",
        [{"event": "FEED_CREDENTIAL_STATS", "access_token_tail4": "R7J6", "api_key_tail4": "oi2n"}],
    )
    paper_log = tmp_path / "paper_market.log"
    paper_log.write_text("WebSocket connection upgrade failed (403 - Forbidden)\n", encoding="utf-8")
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)

    report = build_feed_startup_root_cause_report(
        token_path=token,
        runtime_health_path=runtime_health,
        feed_runtime_path=feed_runtime,
        engine_status_path=engine_status,
        auth_health_path=auth_health,
        ws_events_path=ws_events,
        paper_log_path=paper_log,
        now_epoch=2100.0,
    )

    assert report["read_only"] is True
    assert report["mode"] == "PAPER"
    assert report["credential_sources"]["token_file"]["tail4"] == "R7J6"
    assert report["credential_sources"]["env_token"]["present"] is False
    assert report["credential_sources"]["ws_token_tail4_matches_file_token_tail4"] is True
    assert report["websocket_failure"]["error"].endswith("(403 - Forbidden))")
    assert report["decision"]["primary_root_cause"] == "ws_rejected_validated_credentials"
    assert report["decision"]["safe_to_restart_without_fix"] is False


def test_report_detects_ws_credential_mismatch(tmp_path, monkeypatch):
    token = tmp_path / "kite_access_token"
    token.write_text("token-1234567890-R7J6", encoding="utf-8")
    runtime_health = _write_json(tmp_path / "runtime_health_latest.json", {"mode": "PAPER"})
    feed_runtime = _write_json(tmp_path / "feed_runtime_latest.json", {})
    engine_status = _write_json(
        tmp_path / "engine_cycle_status.json",
        {
            "market_mode": "PAPER",
            "auth_state": "AUTH_REQUIRED",
            "auth_reason": "WebSocket connection upgrade failed (403 - Forbidden)",
        },
    )
    auth_health = _write_jsonl(tmp_path / "auth_health.jsonl", [{"ok": True, "auth_state": "OK", "access_token_tail4": "R7J6"}])
    ws_events = _write_jsonl(tmp_path / "depth_ws_events.jsonl", [{"event": "FEED_CREDENTIAL_STATS", "access_token_tail4": "OLD1"}])
    paper_log = tmp_path / "paper_market.log"
    paper_log.write_text("", encoding="utf-8")
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "token-1234567890-OLD1")

    report = build_feed_startup_root_cause_report(
        token_path=token,
        runtime_health_path=runtime_health,
        feed_runtime_path=feed_runtime,
        engine_status_path=engine_status,
        auth_health_path=auth_health,
        ws_events_path=ws_events,
        paper_log_path=paper_log,
        now_epoch=2100.0,
    )

    assert report["credential_sources"]["env_token"]["tail4"] == "OLD1"
    assert report["credential_sources"]["ws_token_tail4_matches_file_token_tail4"] is False
    assert report["decision"]["primary_root_cause"] == "ws_credential_mismatch"
    assert report["decision"]["recommended_next_action"] == "force_websocket_to_use_canonical_file_credentials_and_log_tail_match"


def test_report_detects_latch_blocking_restart_without_new_ws_error(tmp_path, monkeypatch):
    token = tmp_path / "kite_access_token"
    token.write_text("token-1234567890-R7J6", encoding="utf-8")
    runtime_health = _write_json(tmp_path / "runtime_health_latest.json", {"mode": "PAPER"})
    feed_runtime = _write_json(tmp_path / "feed_runtime_latest.json", {})
    engine_status = _write_json(tmp_path / "engine_cycle_status.json", {"market_mode": "PAPER", "auth_state": "OK", "feed_ok": False})
    auth_health = _write_jsonl(tmp_path / "auth_health.jsonl", [{"ok": True, "auth_state": "OK"}])
    ws_events = _write_jsonl(tmp_path / "depth_ws_events.jsonl", [{"event": "FEED_RESTART_BLOCKED_AUTH_REQUIRED", "reason": "auth_required"}])
    paper_log = tmp_path / "paper_market.log"
    paper_log.write_text("", encoding="utf-8")
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)

    report = build_feed_startup_root_cause_report(
        token_path=token,
        runtime_health_path=runtime_health,
        feed_runtime_path=feed_runtime,
        engine_status_path=engine_status,
        auth_health_path=auth_health,
        ws_events_path=ws_events,
        paper_log_path=paper_log,
        now_epoch=2100.0,
    )

    assert report["websocket_failure"]["auth_required_latch_restart_block_seen"] is True
    assert report["decision"]["primary_root_cause"] == "auth_required_latch_blocking_restart"
