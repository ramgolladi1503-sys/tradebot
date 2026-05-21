import json
import os
from pathlib import Path

from core.runtime_boot_identity import ENV_BOOT_EPOCH, ENV_RUN_ID
from core.ws_status_provenance_report import build_ws_status_provenance_report


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _current_payload(payload: dict, *, writer: str) -> dict:
    data = dict(payload)
    data.update(
        {
            "run_id": os.environ[ENV_RUN_ID],
            "boot_epoch": float(os.environ[ENV_BOOT_EPOCH]),
            "pid": os.getpid(),
            "writer": writer,
            "schema_version": 1,
        }
    )
    return data


def test_ws_status_provenance_includes_feed_startup_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-provenance-lifecycle")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "5000.0")

    _write_json(
        tmp_path / "engine_cycle_status.json",
        _current_payload({"feed_ok": False, "ws_connected": False}, writer="test.engine"),
    )
    _write_json(
        tmp_path / "suggestions_status.json",
        _current_payload({"status": "blocked"}, writer="test.suggestions"),
    )
    _write_json(
        tmp_path / "runtime_health_latest.json",
        _current_payload({"feed": {"feed_ok": False, "ws_connected": False}}, writer="test.runtime_health"),
    )
    _write_json(
        tmp_path / "feed_runtime_latest.json",
        _current_payload({"feed_ok": False, "ws_connected": False}, writer="test.feed_runtime"),
    )
    _write_json(
        tmp_path / "feed_startup_lifecycle_latest.json",
        _current_payload(
            {
                "state": "START_DEPTH_WS_ENTERED",
                "last_event": "START_DEPTH_WS_ENTERED",
                "events_count": 2,
                "feed_runtime_snapshot_written": False,
                "events": [
                    {"event": "FEED_START_REQUESTED", "source": "unit", "ts_epoch": 5001.0},
                    {"event": "START_DEPTH_WS_ENTERED", "source": "unit", "ts_epoch": 5002.0},
                ],
            },
            writer="feed_startup_lifecycle",
        ),
    )

    report = build_ws_status_provenance_report(base_logs_dir=tmp_path)

    assert report["source"]["feed_startup_lifecycle_path"].endswith("feed_startup_lifecycle_latest.json")
    assert report["file_freshness"]["feed_startup_lifecycle"]["exists"] is True
    assert report["feed_startup_lifecycle"]["state"] == "START_DEPTH_WS_ENTERED"
    assert report["feed_startup_lifecycle"]["last_event"] == "START_DEPTH_WS_ENTERED"
    assert report["feed_startup_lifecycle"]["feed_runtime_snapshot_written"] is False
