from core.feed_health_duration import build_feed_health_duration_artifact
from scripts.monitor_feed_health_duration import run_once


def _snapshot(**overrides):
    payload = {
        "ts_epoch": 100.0,
        "runtime_state": "RUNNING",
        "ws_connected": True,
        "feed_ok": True,
        "feed_truth_state": "LIVE",
        "feed_truth_reason_code": "live",
        "last_tick_age_sec": 0.0,
        "last_depth_age_sec": 0.0,
        "market_open": True,
    }
    payload.update(overrides)
    return payload


def test_health_duration_starts_and_extends_healthy_window():
    first = build_feed_health_duration_artifact(
        _snapshot(ts_epoch=100.0),
        previous=None,
        target_window_sec=3600.0,
    )
    assert first["healthy"] is True
    assert first["current_healthy_since_epoch"] == 100.0
    assert first["current_healthy_duration_sec"] == 0.0
    assert first["target_met"] is False

    second = build_feed_health_duration_artifact(
        _snapshot(ts_epoch=3700.0),
        previous=first,
        target_window_sec=3600.0,
    )
    assert second["healthy"] is True
    assert second["current_healthy_since_epoch"] == 100.0
    assert second["current_healthy_duration_sec"] == 3600.0
    assert second["target_met"] is True
    assert second["longest_healthy_duration_sec"] == 3600.0


def test_health_duration_resets_fail_closed_on_unhealthy_snapshot():
    healthy = build_feed_health_duration_artifact(
        _snapshot(ts_epoch=100.0),
        previous=None,
        target_window_sec=3600.0,
    )
    unhealthy = build_feed_health_duration_artifact(
        _snapshot(
            ts_epoch=130.0,
            feed_ok=False,
            feed_truth_state="RESTART_VERIFY_FAILED",
            feed_truth_reason_code="restart_verify_failed",
        ),
        previous=healthy,
        target_window_sec=3600.0,
    )
    assert unhealthy["healthy"] is False
    assert unhealthy["current_healthy_since_epoch"] is None
    assert unhealthy["current_healthy_duration_sec"] == 0.0
    assert unhealthy["last_unhealthy_epoch"] == 130.0
    assert unhealthy["last_unhealthy_reason"] == "restart_verify_failed"
    assert unhealthy["target_met"] is False

def test_monitor_run_once_writes_duration_artifact(tmp_path):
    snapshot_path = tmp_path / "feed_runtime_latest.json"
    output_path = tmp_path / "feed_health_duration_latest.json"
    snapshot_path.write_text(
        (
            '{"ts_epoch": 100.0, "runtime_state": "RUNNING", "ws_connected": true, '
            '"feed_ok": true, "feed_truth_state": "LIVE", "feed_truth_reason_code": "live"}'
        ),
        encoding="utf-8",
    )

    artifact = run_once(
        snapshot_paths=[snapshot_path],
        output_path=output_path,
        target_window_sec=60.0,
        max_snapshot_age_sec=10_000_000_000.0,
    )

    assert output_path.exists()
    assert artifact["healthy"] is True
    assert artifact["snapshot_path"] == str(snapshot_path)
    assert artifact["is_order_action"] is False
    assert artifact["broker_api_called"] is False


def test_monitor_run_once_fails_closed_on_stale_snapshot(tmp_path):
    snapshot_path = tmp_path / "feed_runtime_latest.json"
    output_path = tmp_path / "feed_health_duration_latest.json"
    snapshot_path.write_text(
        (
            '{"ts_epoch": 100.0, "runtime_state": "RUNNING", "ws_connected": true, '
            '"feed_ok": true, "feed_truth_state": "LIVE", "feed_truth_reason_code": "live"}'
        ),
        encoding="utf-8",
    )

    artifact = run_once(
        snapshot_paths=[snapshot_path],
        output_path=output_path,
        target_window_sec=60.0,
        max_snapshot_age_sec=1.0,
    )

    assert artifact["healthy"] is False
    assert artifact["health_reason"] == "runtime_snapshot_stale"
