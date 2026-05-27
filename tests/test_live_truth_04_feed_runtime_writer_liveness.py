from __future__ import annotations

import json

from core.live_truth_feed_runtime_writer_liveness import (
    FEED_RUNTIME_WRITER_LIVENESS_SOURCE,
    FUTURE_HEARTBEAT_REASON,
    INVALID_CONFIG_REASON,
    INVALID_SNAPSHOT_REASON,
    MISSING_HEARTBEAT_REASON,
    SUBSCRIPTION_RECOVERY_MISSING_REASON,
    WEBSOCKET_RECOVERY_MISSING_REASON,
    WRITER_STATUS_ALIVE,
    WRITER_STATUS_BLOCKED,
    WRITER_STATUS_RECOVERY_MISSING,
    WRITER_STATUS_STALE,
    WRITER_STALE_REASON,
    build_feed_runtime_writer_liveness_report,
    write_feed_runtime_writer_liveness_evidence,
)


def test_reports_writer_alive_when_heartbeat_is_recent_and_recovery_is_clear():
    payload = build_feed_runtime_writer_liveness_report(
        {
            "generated_epoch": 100.0,
            "ws_connected": True,
            "feed_ok": True,
            "subscribed_tokens_count": 69,
            "subscribed_option_tokens_count": 66,
        },
        now_epoch=110.0,
        writer_max_age_sec=30.0,
    ).to_payload()

    assert payload["status"] == WRITER_STATUS_ALIVE
    assert payload["writer_alive"] is True
    assert payload["heartbeat_age_sec"] == 10.0
    assert payload["websocket_recovery_visible"] is True
    assert payload["subscription_recovery_visible"] is True
    assert payload["recovery_issue_count"] == 0
    assert payload["subscribed_tokens_count"] == 69
    assert payload["subscribed_option_tokens_count"] == 66


def test_reports_stale_writer_when_heartbeat_exceeds_age_limit():
    payload = build_feed_runtime_writer_liveness_report(
        {"generated_epoch": 10.0, "ws_connected": True},
        now_epoch=100.0,
        writer_max_age_sec=30.0,
    ).to_payload()

    assert payload["status"] == WRITER_STATUS_STALE
    assert payload["reason_code"] == WRITER_STALE_REASON
    assert payload["writer_alive"] is False
    assert payload["heartbeat_age_sec"] == 90.0


def test_blocks_when_heartbeat_is_missing():
    payload = build_feed_runtime_writer_liveness_report(
        {"ws_connected": True, "feed_ok": True},
        now_epoch=100.0,
    ).to_payload()

    assert payload["status"] == WRITER_STATUS_BLOCKED
    assert payload["reason_code"] == MISSING_HEARTBEAT_REASON
    assert payload["writer_alive"] is False
    assert payload["heartbeat_epoch"] is None


def test_blocks_invalid_snapshot_payload():
    payload = build_feed_runtime_writer_liveness_report(
        ["not", "a", "mapping"],
        now_epoch=100.0,
    ).to_payload()

    assert payload["status"] == WRITER_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_SNAPSHOT_REASON
    assert payload["metadata"]["blocked_before_heartbeat_check"] is True


def test_blocks_future_heartbeat_beyond_tolerance():
    payload = build_feed_runtime_writer_liveness_report(
        {"generated_epoch": 200.0},
        now_epoch=100.0,
        future_skew_tolerance_sec=5.0,
    ).to_payload()

    assert payload["status"] == WRITER_STATUS_BLOCKED
    assert payload["reason_code"] == FUTURE_HEARTBEAT_REASON
    assert payload["heartbeat_age_sec"] < 0


def test_reports_websocket_recovery_missing_when_disconnected_without_recovery():
    payload = build_feed_runtime_writer_liveness_report(
        {
            "generated_epoch": 100.0,
            "ws_connected": False,
            "last_ws_disconnect_epoch": 90.0,
        },
        now_epoch=110.0,
    ).to_payload()

    assert payload["status"] == WRITER_STATUS_RECOVERY_MISSING
    assert payload["reason_code"] == WEBSOCKET_RECOVERY_MISSING_REASON
    assert payload["websocket_recovery_visible"] is False
    assert payload["recovery_issue_count"] == 1


def test_reports_websocket_recovery_visible_when_recovery_follows_disconnect():
    payload = build_feed_runtime_writer_liveness_report(
        {
            "generated_epoch": 100.0,
            "ws_connected": True,
            "last_ws_disconnect_epoch": 80.0,
            "last_ws_reconnect_epoch": 90.0,
        },
        now_epoch=110.0,
        recovery_visibility_max_age_sec=30.0,
    ).to_payload()

    assert payload["status"] == WRITER_STATUS_ALIVE
    assert payload["websocket_recovery_visible"] is True
    assert payload["recovery_issue_count"] == 0


def test_reports_subscription_recovery_missing_when_failure_has_no_success():
    payload = build_feed_runtime_writer_liveness_report(
        {
            "generated_epoch": 100.0,
            "ws_connected": True,
            "last_subscription_failure_epoch": 90.0,
        },
        now_epoch=110.0,
    ).to_payload()

    assert payload["status"] == WRITER_STATUS_RECOVERY_MISSING
    assert SUBSCRIPTION_RECOVERY_MISSING_REASON in payload["reasons"]
    assert payload["subscription_recovery_visible"] is False
    assert payload["recovery_issue_count"] == 1


def test_accepts_iso_timestamps_for_heartbeat_and_recovery():
    payload = build_feed_runtime_writer_liveness_report(
        {
            "generated_at": "2026-05-27T10:00:00Z",
            "last_ws_disconnect_at": "2026-05-27T09:59:00Z",
            "last_ws_reconnect_at": "2026-05-27T10:00:10Z",
        },
        now_epoch=1779876030.0,
        writer_max_age_sec=60.0,
        recovery_visibility_max_age_sec=60.0,
    ).to_payload()

    assert payload["status"] == WRITER_STATUS_ALIVE
    assert payload["heartbeat_key"] == "generated_at"
    assert payload["heartbeat_age_sec"] == 30.0
    assert payload["websocket_recovery_visible"] is True


def test_blocks_invalid_config():
    payload = build_feed_runtime_writer_liveness_report(
        {"generated_epoch": 100.0},
        now_epoch=100.0,
        writer_max_age_sec=0,
    ).to_payload()

    assert payload["status"] == WRITER_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_CONFIG_REASON


def test_writes_read_only_evidence_file(tmp_path):
    target = tmp_path / "feed_runtime_writer_liveness_latest.json"
    report = build_feed_runtime_writer_liveness_report(
        {"generated_epoch": 100.0, "ws_connected": True},
        now_epoch=101.0,
    )

    out = write_feed_runtime_writer_liveness_evidence(report, target)

    assert out == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["source"] == FEED_RUNTIME_WRITER_LIVENESS_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_payload_is_json_serializable_and_non_action():
    payload = build_feed_runtime_writer_liveness_report(
        {"generated_epoch": 100.0},
        now_epoch=101.0,
    ).to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["source"] == FEED_RUNTIME_WRITER_LIVENESS_SOURCE
    assert decoded["read_only"] is True
    assert decoded["append"] is False
    assert decoded["is_order_action"] is False
    assert decoded["broker_api_called"] is False
    assert decoded["live_order_action"] is False
    assert decoded["broker_order_action"] is False
