from core.runtime_auth_freshness import (
    STALE_AUTH_SUPERSEDED_BY_HEALTH,
    resolve_runtime_auth_snapshot,
)


def test_newer_auth_health_ok_supersedes_stale_auth_required():
    snapshot = resolve_runtime_auth_snapshot(
        {
            "status": "AUTH_REQUIRED",
            "reason": "WebSocket connection upgrade failed (403 - Forbidden)",
            "source": "old_ws_failure",
            "ts_epoch": 100.0,
        },
        latest_health_payload={
            "ok": True,
            "auth_state": "OK",
            "source": "live",
            "ts_epoch": 200.0,
        },
    )

    assert snapshot["auth_ok"] is True
    assert snapshot["auth_state"] == "OK"
    assert snapshot["auth_reason"] == ""
    assert snapshot["auth_stale_reason"] == STALE_AUTH_SUPERSEDED_BY_HEALTH
    assert snapshot["stale_auth_reason"] == "WebSocket connection upgrade failed (403 - Forbidden)"


def test_older_auth_health_does_not_override_newer_auth_required():
    snapshot = resolve_runtime_auth_snapshot(
        {
            "status": "AUTH_REQUIRED",
            "reason": "fresh ws failure",
            "source": "kite_depth_ws_error",
            "ts_epoch": 300.0,
        },
        latest_health_payload={
            "ok": True,
            "auth_state": "OK",
            "source": "live",
            "ts_epoch": 200.0,
        },
    )

    assert snapshot["auth_ok"] is False
    assert snapshot["auth_state"] == "AUTH_REQUIRED"
    assert snapshot["auth_reason"] == "fresh ws failure"
    assert snapshot["auth_stale_reason"] == ""


def test_missing_auth_state_remains_unknown_without_fake_failure():
    snapshot = resolve_runtime_auth_snapshot({}, latest_health_payload={})

    assert snapshot["auth_ok"] is True
    assert snapshot["auth_state"] == "UNKNOWN"
    assert snapshot["auth_reason"] == ""
