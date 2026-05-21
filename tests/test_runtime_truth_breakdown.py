from __future__ import annotations

import json

from core.runtime_truth_breakdown import build_runtime_truth_breakdown


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def test_truth_breakdown_detects_rest_ok_engine_required_and_ws_error(tmp_path):
    runtime_health = _write_json(
        tmp_path / "runtime_health_latest.json",
        {"mode": "PAPER", "feed": {"ws_connected": False, "subscribed_option_tokens_count": 0}},
    )
    feed_runtime = _write_json(
        tmp_path / "feed_runtime_latest.json",
        {"ws_connected": True, "feed_ok": False, "subscribed_option_tokens_count": 0},
    )
    engine_status = _write_json(
        tmp_path / "engine_cycle_status.json",
        {
            "market_mode": "PAPER",
            "auth_ok": False,
            "auth_state": "AUTH_REQUIRED",
            "auth_reason": "code=1006 connection was closed uncleanly (WebSocket connection upgrade failed (403 - Forbidden))",
            "feed_ok": False,
            "ws_connected": True,
            "subscribed_option_tokens_count": 0,
            "visible_executable_count": 0,
            "primary_blocker": "NO_CANDIDATES",
        },
    )
    auth_health = _write_jsonl(
        tmp_path / "auth_health.jsonl",
        [{"ok": True, "auth_state": "OK", "source": "live", "ts_epoch": 2000.0, "user_id": "U1", "error": ""}],
    )
    auth_events = _write_jsonl(tmp_path / "auth_events.jsonl", [])
    paper_log = tmp_path / "paper_market.log"
    paper_log.write_text("WebSocket connection upgrade failed (403 - Forbidden)\n", encoding="utf-8")

    report = build_runtime_truth_breakdown(
        runtime_health_path=runtime_health,
        feed_runtime_path=feed_runtime,
        engine_status_path=engine_status,
        auth_health_path=auth_health,
        auth_events_path=auth_events,
        paper_log_path=paper_log,
        now_epoch=2100.0,
    )

    assert report["read_only"] is True
    assert report["mode"] == "PAPER"
    assert report["rest_auth"]["latest_ok"] is True
    assert report["engine_truth"]["auth_state"] == "AUTH_REQUIRED"
    assert report["websocket"]["auth_failed"] is True
    assert "rest_auth_ok_but_engine_auth_required" in report["truth_conflicts"]
    assert "runtime_health_ws_disagrees_with_feed_runtime" in report["truth_conflicts"]
    assert report["decision"]["primary_blocker"] == "websocket_auth_failed"
    assert report["decision"]["safe_to_restart_without_fix"] is False


def test_truth_breakdown_flags_stale_feed_runtime_when_engine_is_fresh(tmp_path):
    runtime_health = _write_json(tmp_path / "runtime_health_latest.json", {"mode": "PAPER", "feed": {"ws_connected": False}})
    feed_runtime = _write_json(tmp_path / "feed_runtime_latest.json", {"ws_connected": True, "feed_ok": False})
    engine_status = _write_json(
        tmp_path / "engine_cycle_status.json",
        {"market_mode": "PAPER", "auth_state": "OK", "feed_ok": True, "subscribed_option_tokens_count": 1},
    )
    auth_health = _write_jsonl(tmp_path / "auth_health.jsonl", [{"ok": True, "auth_state": "OK", "ts_epoch": 1000.0}])
    auth_events = _write_jsonl(tmp_path / "auth_events.jsonl", [])
    paper_log = tmp_path / "paper_market.log"
    paper_log.write_text("", encoding="utf-8")

    old = 1000.0
    fresh = 1990.0
    feed_runtime.touch()
    runtime_health.touch()
    engine_status.touch()
    paper_log.touch()

    import os

    os.utime(feed_runtime, (old, old))
    os.utime(engine_status, (fresh, fresh))
    os.utime(runtime_health, (fresh, fresh))
    os.utime(paper_log, (fresh, fresh))

    report = build_runtime_truth_breakdown(
        runtime_health_path=runtime_health,
        feed_runtime_path=feed_runtime,
        engine_status_path=engine_status,
        auth_health_path=auth_health,
        auth_events_path=auth_events,
        paper_log_path=paper_log,
        now_epoch=2000.0,
    )

    assert report["file_freshness"]["feed_runtime"]["fresh"] is False
    assert report["file_freshness"]["engine_status"]["fresh"] is True
    assert "feed_runtime_file_stale_but_engine_status_fresh" in report["truth_conflicts"]
    assert report["decision"]["primary_blocker"] == "stale_feed_runtime_truth"


def test_truth_breakdown_reports_no_option_subscriptions_when_truth_is_otherwise_clean(tmp_path):
    runtime_health = _write_json(
        tmp_path / "runtime_health_latest.json",
        {"mode": "PAPER", "feed": {"ws_connected": True, "subscribed_option_tokens_count": 0}},
    )
    feed_runtime = _write_json(tmp_path / "feed_runtime_latest.json", {"ws_connected": True, "feed_ok": True, "subscribed_option_tokens_count": 0})
    engine_status = _write_json(
        tmp_path / "engine_cycle_status.json",
        {"market_mode": "PAPER", "auth_state": "OK", "feed_ok": True, "subscribed_option_tokens_count": 0},
    )
    auth_health = _write_jsonl(tmp_path / "auth_health.jsonl", [{"ok": True, "auth_state": "OK", "ts_epoch": 1000.0}])
    auth_events = _write_jsonl(tmp_path / "auth_events.jsonl", [])
    paper_log = tmp_path / "paper_market.log"
    paper_log.write_text("", encoding="utf-8")

    report = build_runtime_truth_breakdown(
        runtime_health_path=runtime_health,
        feed_runtime_path=feed_runtime,
        engine_status_path=engine_status,
        auth_health_path=auth_health,
        auth_events_path=auth_events,
        paper_log_path=paper_log,
        now_epoch=1000.0,
    )

    assert report["decision"]["primary_blocker"] == "no_option_subscriptions"
    assert report["decision"]["recommended_next_action"] == "fix_option_token_resolution_and_subscription_before_paper_run"
