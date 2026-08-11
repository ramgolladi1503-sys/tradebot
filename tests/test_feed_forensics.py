import json

from core.feed_forensics import append_event, classify_session


def _write(root, *rows):
    (root / "feed_forensics.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )


def _callback():
    return {"event_type": "WS_CALLBACK", "receipt_epoch": 10.0}


def _progress(event_type, status="PROGRESS"):
    return {"event_type": event_type, "receipt_epoch": 10.0, "status": status}


def test_healthy_session(tmp_path):
    _write(tmp_path, _callback(), _progress("TICK_PERSISTENCE_PROGRESS"),
           _progress("DEPTH_PERSISTENCE_PROGRESS"), _progress("RUNTIME_PERSISTENCE_PROGRESS"))
    assert classify_session(tmp_path)["classification"] == "SESSION_HEALTHY"


def test_missing_ledger_is_unknown(tmp_path):
    assert classify_session(tmp_path)["classification"] == "UNKNOWN"


def test_callback_thread_stall_is_unknown_without_socket_evidence(tmp_path):
    _write(tmp_path, _progress("TICK_PERSISTENCE_PROGRESS"))
    assert classify_session(tmp_path)["classification"] == "UNKNOWN"


def test_tick_writer_stall(tmp_path):
    _write(tmp_path, _callback(), _progress("TICK_PERSISTENCE_PROGRESS", "STALLED"))
    assert classify_session(tmp_path)["classification"] == "CALLBACKS_CONTINUED_BUT_TICK_WRITER_STALLED"


def test_depth_writer_stall(tmp_path):
    _write(tmp_path, _callback(), _progress("TICK_PERSISTENCE_PROGRESS"),
           _progress("DEPTH_PERSISTENCE_PROGRESS", "STALLED"))
    assert classify_session(tmp_path)["classification"] == "DEPTH_WRITER_STALLED"


def test_runtime_writer_stall(tmp_path):
    _write(tmp_path, _callback(), _progress("TICK_PERSISTENCE_PROGRESS"),
           _progress("RUNTIME_PERSISTENCE_PROGRESS", "STALLED"))
    assert classify_session(tmp_path)["classification"] == "RUNTIME_SNAPSHOT_WRITER_STALLED"


def test_watchdog_only_stall(tmp_path):
    _write(tmp_path, _callback(), _progress("TICK_PERSISTENCE_PROGRESS"),
           _progress("RUNTIME_PERSISTENCE_PROGRESS"), _progress("FEED_WATCHDOG", "STALLED"))
    assert classify_session(tmp_path)["classification"] == "WATCHDOG_ONLY_STALLED"


def test_reconnect_success_precedes_other_classification(tmp_path):
    _write(tmp_path, _callback(), {"event_type": "RECOVERY_SUCCEEDED", "receipt_epoch": 11.0})
    assert classify_session(tmp_path)["classification"] == "RECONNECT_TRIGGERED_AND_RECOVERED"


def test_reconnect_failure(tmp_path):
    _write(tmp_path, _callback(), {"event_type": "RECOVERY_FAILED", "receipt_epoch": 11.0})
    assert classify_session(tmp_path)["classification"] == "RECONNECT_TRIGGERED_AND_FAILED"


def test_broker_silence_requires_watchdog_evidence(tmp_path):
    _write(tmp_path, _callback(), {"event_type": "FEED_WATCHDOG", "receipt_epoch": 11.0,
                                   "feed_ok": False, "latest_callback_epoch": 10.0})
    assert classify_session(tmp_path)["classification"] == "BROKER_FEED_STOPPED_DELIVERING"


def test_append_event_is_bounded_and_hashed(tmp_path, monkeypatch):
    monkeypatch.setenv("FEED_FORENSICS_ENABLED", "true")
    monkeypatch.setenv("TRADEBOT_FEED_FORENSICS_ROOT", str(tmp_path))
    monkeypatch.setenv("RUN_ID", "run-1")
    monkeypatch.setenv("TRADEBOT_COMMIT_SHA", "sha-1")
    assert append_event("WS_CALLBACK", receipt_epoch=10.0, callback_sequence=1)
    assert not append_event("WS_CALLBACK", receipt_epoch=10.1, callback_sequence=2)
    row = json.loads((tmp_path / "feed_forensics.jsonl").read_text())
    assert row["session_id"] == "run-1"
    assert row["row_sha256"]
