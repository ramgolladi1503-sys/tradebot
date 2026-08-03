import json

import core.feed.runtime_store as store
import core.feed_startup_lifecycle as lifecycle
from core.runtime_boot_identity import ENV_BOOT_EPOCH, ENV_RUN_ID


def test_write_runtime_snapshot_records_start_and_snapshot_events(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-runtime-store-lifecycle")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "6000.0")
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "runtime.db")

    ok = store.write_runtime_snapshot(
        {
            "ts_epoch": 6001.0,
            "ws_connected": None,
            "subscribed_tokens_count": 0,
            "intended_tokens_count": 10,
            "subscribed_tokens_sample": [],
            "source": "start_depth_ws:starting",
            "runtime_state": "STARTING",
            "last_error": "",
        }
    )

    assert ok is True
    store.shutdown_runtime_persistence()
    latest = json.loads((tmp_path / "feed_startup_lifecycle_latest.json").read_text())
    assert latest["run_id"] == "run-runtime-store-lifecycle"
    assert latest["last_event"] == "FEED_RUNTIME_SNAPSHOT_WRITTEN"
    assert latest["feed_runtime_snapshot_written"] is True
    assert [event["event"] for event in latest["events"]] == [
        "START_DEPTH_WS_ENTERED",
        "FEED_RUNTIME_SNAPSHOT_WRITTEN",
    ]
    assert latest["events"][0]["details"]["runtime_state"] == "STARTING"
    assert latest["events"][0]["details"]["intended_tokens_count"] == 10


def test_write_runtime_snapshot_records_auth_blocked_event(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-runtime-store-auth")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "7000.0")
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "runtime.db")

    ok = store.write_runtime_snapshot(
        {
            "ts_epoch": 7001.0,
            "ws_connected": False,
            "subscribed_tokens_count": 0,
            "intended_tokens_count": 10,
            "subscribed_tokens_sample": [],
            "source": "start_depth_ws:auth_blocked",
            "runtime_state": "AUTH_BLOCKED",
            "last_error": "missing_access_token",
        }
    )

    assert ok is True
    store.shutdown_runtime_persistence()
    latest = json.loads((tmp_path / "feed_startup_lifecycle_latest.json").read_text())
    assert [event["event"] for event in latest["events"]] == [
        "AUTH_BLOCKED",
        "FEED_RUNTIME_SNAPSHOT_WRITTEN",
    ]
    assert latest["events"][0]["error"] == "missing_access_token"
