import json
import os

import core.feed_startup_lifecycle as lifecycle
from core.runtime_boot_identity import ENV_BOOT_EPOCH, ENV_RUN_ID


def test_lifecycle_event_is_boot_stamped(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-lifecycle-test")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "1000.0")
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)

    payload = lifecycle.record_feed_startup_event(
        "FEED_START_REQUESTED",
        source="unit.test",
        details={"mode": "PAPER"},
        now_epoch=1001.0,
    )

    assert payload["run_id"] == "run-lifecycle-test"
    assert payload["boot_epoch"] == 1000.0
    assert payload["pid"] == os.getpid()
    assert payload["writer"] == "feed_startup_lifecycle"
    assert payload["schema_version"] == 1
    assert payload["state"] == "FEED_START_REQUESTED"
    assert payload["last_event"] == "FEED_START_REQUESTED"
    assert payload["events_count"] == 1

    latest = json.loads((tmp_path / "feed_startup_lifecycle_latest.json").read_text())
    assert latest["last_event"] == "FEED_START_REQUESTED"

    rows = (tmp_path / "feed_startup_lifecycle.jsonl").read_text().splitlines()
    event_rows = [json.loads(row) for row in rows]
    assert [row["event"] for row in event_rows] == ["FEED_START_REQUESTED"]
    assert event_rows[0]["writer"] == "feed_startup_lifecycle.event"


def test_current_run_events_are_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-lifecycle-sequence")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "2000.0")
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)

    lifecycle.record_feed_startup_event("FEED_START_REQUESTED", source="unit", now_epoch=2001.0)
    lifecycle.record_feed_startup_event("KITE_TICKER_CREATE_ATTEMPTED", source="unit", now_epoch=2002.0)
    payload = lifecycle.record_feed_startup_event("KITE_TICKER_CREATED", source="unit", now_epoch=2003.0)

    assert payload["state"] == "KITE_TICKER_CREATED"
    assert payload["events_count"] == 3
    assert [event["event"] for event in payload["events"]] == [
        "FEED_START_REQUESTED",
        "KITE_TICKER_CREATE_ATTEMPTED",
        "KITE_TICKER_CREATED",
    ]


def test_old_lifecycle_events_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-current-lifecycle")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "3000.0")
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)

    (tmp_path / "feed_startup_lifecycle_latest.json").write_text(
        json.dumps(
            {
                "run_id": "old-run",
                "boot_epoch": 1.0,
                "pid": 999,
                "writer": "feed_startup_lifecycle",
                "schema_version": 1,
                "events": [{"event": "OLD_EVENT"}],
            }
        ),
        encoding="utf-8",
    )

    payload = lifecycle.record_feed_startup_event("FEED_START_REQUESTED", source="unit", now_epoch=3001.0)

    assert payload["events_count"] == 1
    assert payload["events"][0]["event"] == "FEED_START_REQUESTED"


def test_snapshot_event_sets_snapshot_written_flag(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-lifecycle-snapshot")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "4000.0")
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)

    payload = lifecycle.record_feed_startup_event(
        "FEED_RUNTIME_SNAPSHOT_WRITTEN",
        source="unit",
        now_epoch=4001.0,
    )

    assert payload["feed_runtime_snapshot_written"] is True
    assert payload["last_event"] == "FEED_RUNTIME_SNAPSHOT_WRITTEN"


def test_token_like_details_are_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-lifecycle-redact")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "5000.0")
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)

    payload = lifecycle.record_feed_startup_event(
        "KITE_TICKER_CREATE_ATTEMPTED",
        source="unit",
        details={
            "access_token": "secret-full-token",
            "access_token_tail4": "OKEN",
            "access_token_len": 17,
            "access_token_present": True,
        },
        now_epoch=5001.0,
    )

    details = payload["events"][0]["details"]
    assert details["access_token"] == "<redacted>"
    assert details["access_token_tail4"] == "OKEN"
    assert details["access_token_len"] == 17
    assert details["access_token_present"] is True
