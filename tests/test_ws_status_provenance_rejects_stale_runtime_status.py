import json
import os
import time
from pathlib import Path

from core.runtime_boot_identity import ENV_BOOT_EPOCH, ENV_RUN_ID
from core.ws_status_provenance_report import build_ws_status_provenance_report


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _current_payload(writer: str, payload: dict | None = None) -> dict:
    boot_epoch = float(os.environ[ENV_BOOT_EPOCH])
    data = dict(payload or {})
    data.update(
        {
            "run_id": os.environ[ENV_RUN_ID],
            "boot_epoch": boot_epoch,
            "pid": os.getpid(),
            "writer": writer,
            "schema_version": 1,
        }
    )
    return data


def test_ws_status_provenance_rejects_unversioned_stale_feed_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-current")
    monkeypatch.setenv(ENV_BOOT_EPOCH, str(time.time()))

    engine = _write_json(
        tmp_path / "engine_cycle_status.json",
        _current_payload(
            "test.engine",
            {
                "auth_state": "OK",
                "auth_ok": True,
                "feed_ok": False,
                "ws_connected": True,
            },
        ),
    )

    suggestions = _write_json(
        tmp_path / "suggestions_status.json",
        _current_payload(
            "test.suggestions",
            {
                "status": "blocked",
                "primary_blocker": "NO_CANDIDATES",
                "subreason": "NO_CANDIDATES",
            },
        ),
    )

    runtime = _write_json(
        tmp_path / "runtime_health_latest.json",
        _current_payload(
            "test.runtime_health",
            {
                "feed": {
                    "ws_connected": False,
                    "feed_ok": False,
                }
            },
        ),
    )

    # This mimics the real bug: old/unversioned feed truth mixed with fresh engine truth.
    feed = _write_json(
        tmp_path / "feed_runtime_latest.json",
        {
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "feed_ok": False,
        },
    )

    auth_events = _write_text(tmp_path / "auth_events.jsonl", "")

    report = build_ws_status_provenance_report(
        engine_status_path=engine,
        suggestions_status_path=suggestions,
        runtime_health_path=runtime,
        feed_runtime_path=feed,
        auth_events_path=auth_events,
        base_logs_dir=tmp_path,
    )

    assert report["runtime_status_freshness"]["feed_runtime_latest"]["is_current_run"] is False
    assert "missing_run_id" in report["runtime_status_freshness"]["feed_runtime_latest"]["freshness_reasons"]
    assert report["decision"]["primary_conclusion"] == "stale_runtime_status_rejected"
    assert report["decision"]["safe_to_treat_status_as_fresh_ws_failure"] is False
