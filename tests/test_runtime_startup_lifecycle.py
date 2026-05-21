import json
import os

import core.runtime_startup_lifecycle as lifecycle
from core.runtime_boot_identity import ENV_BOOT_EPOCH, ENV_RUN_ID


def test_runtime_startup_event_is_boot_stamped(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-runtime-startup-test")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "1000.0")
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)

    payload = lifecycle.record_runtime_startup_event(
        "MAIN_BOOT_STARTED",
        source="unit.test",
        details={"mode": "PAPER"},
        now_epoch=1001.0,
    )

    assert payload["run_id"] == "run-runtime-startup-test"
    assert payload["boot_epoch"] == 1000.0
    assert payload["pid"] == os.getpid()
    assert payload["writer"] == "runtime_startup_lifecycle"
    assert payload["schema_version"] == 1
    assert payload["state"] == "MAIN_BOOT_STARTED"
    assert payload["last_event"] == "MAIN_BOOT_STARTED"
    assert payload["events_count"] == 1
    assert payload["is_order_action"] is False
    assert payload["proof_flags"]["main_boot_started"] is True

    latest = json.loads((tmp_path / "runtime_startup_lifecycle_latest.json").read_text())
    assert latest["last_event"] == "MAIN_BOOT_STARTED"
    assert latest["is_order_action"] is False

    rows = (tmp_path / "runtime_startup_lifecycle.jsonl").read_text().splitlines()
    event_rows = [json.loads(row) for row in rows]
    assert [row["event"] for row in event_rows] == ["MAIN_BOOT_STARTED"]
    assert event_rows[0]["writer"] == "runtime_startup_lifecycle.event"
    assert event_rows[0]["is_order_action"] is False


def test_current_run_events_are_preserved_and_flags_accumulate(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-runtime-startup-sequence")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "2000.0")
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)

    lifecycle.record_runtime_startup_event("MAIN_BOOT_STARTED", source="unit", now_epoch=2001.0)
    lifecycle.record_runtime_startup_event("MAIN_SAFETY_VALIDATED", source="unit", now_epoch=2002.0)
    payload = lifecycle.record_runtime_startup_event("ORCHESTRATOR_CYCLE_STARTED", source="unit", now_epoch=2003.0)

    assert payload["state"] == "ORCHESTRATOR_CYCLE_STARTED"
    assert payload["events_count"] == 3
    assert [event["event"] for event in payload["events"]] == [
        "MAIN_BOOT_STARTED",
        "MAIN_SAFETY_VALIDATED",
        "ORCHESTRATOR_CYCLE_STARTED",
    ]
    assert payload["proof_flags"]["main_boot_started"] is True
    assert payload["proof_flags"]["main_safety_validated"] is True


def test_old_runtime_startup_events_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-current-runtime-startup")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "3000.0")
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)

    (tmp_path / "runtime_startup_lifecycle_latest.json").write_text(
        json.dumps(
            {
                "run_id": "old-run",
                "boot_epoch": 1.0,
                "pid": 999,
                "writer": "runtime_startup_lifecycle",
                "schema_version": 1,
                "events": [{"event": "OLD_EVENT"}],
            }
        ),
        encoding="utf-8",
    )

    payload = lifecycle.record_runtime_startup_event("MAIN_BOOT_STARTED", source="unit", now_epoch=3001.0)

    assert payload["events_count"] == 1
    assert payload["events"][0]["event"] == "MAIN_BOOT_STARTED"


def test_failure_event_sets_failure_flag(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-runtime-startup-failure")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "4000.0")
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)

    payload = lifecycle.record_runtime_startup_event(
        "ORCHESTRATOR_CYCLE_FAILED",
        source="unit",
        error="RuntimeError:boom",
        now_epoch=4001.0,
    )

    assert payload["last_event"] == "ORCHESTRATOR_CYCLE_FAILED"
    assert payload["last_error"] == "RuntimeError:boom"
    assert payload["proof_flags"]["failure_seen"] is True


def test_secret_like_details_are_redacted_but_metadata_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-runtime-startup-redact")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "5000.0")
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)

    payload = lifecycle.record_runtime_startup_event(
        "MAIN_AUTH_VALIDATED",
        source="unit",
        details={
            "access_token": "secret-full-token",
            "access_token_tail4": "OKEN",
            "access_token_len": 17,
            "api_key": "full-api-key",
            "api_key_tail4": "IKEY",
            "password": "bad",
        },
        now_epoch=5001.0,
    )

    details = payload["events"][0]["details"]
    assert details["access_token"] == "<redacted>"
    assert details["access_token_tail4"] == "OKEN"
    assert details["access_token_len"] == 17
    assert details["api_key"] == "<redacted>"
    assert details["api_key_tail4"] == "IKEY"
    assert details["password"] == "<redacted>"
