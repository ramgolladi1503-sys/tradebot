from __future__ import annotations

import json
from pathlib import Path

from core.event_integrity import repair_events_file, validate_events_file
from core.event_state import build_state_from_events
from core.events import append_event, write_json_atomic


def _write_crash_simulated_events(path: Path) -> None:
    rows = [
        {
            "ts": "2026-03-03T09:15:00Z",
            "type": "order_submitted",
            "payload": {"event_id": "evt_1", "order_id": "ord_1", "trade_id": "trd_1"},
        },
        {
            "ts": "2026-03-03T09:15:01Z",
            "type": "fill",
            "payload": {"event_id": "evt_2", "order_id": "ord_1", "trade_id": "trd_1"},
        },
    ]
    with path.open("wb") as handle:
        for row in rows:
            handle.write((json.dumps(row, sort_keys=True) + "\n").encode("utf-8"))
        # Truncated crash tail: incomplete JSON object at EOF.
        handle.write(b'{"ts":"2026-03-03T09:15:02Z","type":"fill","payload":{"event_id":"evt_bad"')


def test_event_integrity_crash_recovery(tmp_path, monkeypatch):
    events_file = tmp_path / "events.jsonl"
    _write_crash_simulated_events(events_file)

    validation = validate_events_file(events_file)
    assert validation["ok"] is False
    assert validation["truncated_tail"] is True
    assert validation["last_good_offset"] > 0

    repair = repair_events_file(events_file)
    assert repair["repaired"] is True
    assert repair["bytes_trimmed"] > 0

    # File should now contain only valid JSON lines.
    with events_file.open("r", encoding="utf-8") as handle:
        repaired_rows = [json.loads(line) for line in handle if line.strip()]
    assert len(repaired_rows) == 2
    assert all(isinstance(row, dict) for row in repaired_rows)

    # Append duplicate event payload (same event_id) twice; state rebuild must dedupe.
    duplicate_payload = {"event_id": "dup_evt", "order_id": "ord_dup", "trade_id": "trd_dup"}
    append_event("fill", duplicate_payload, path=events_file, session_id="s1")
    append_event("fill", duplicate_payload, path=events_file, session_id="s1")

    monkeypatch.setattr("core.event_state.logs_dir", lambda: tmp_path)
    state = build_state_from_events("DEFAULT")
    assert "evt_1" in state.seen_event_ids
    assert "evt_2" in state.seen_event_ids
    assert "dup_evt" in state.seen_event_ids
    # dup_evt should be present once in idempotent state.
    assert len([x for x in state.seen_event_ids if x == "dup_evt"]) == 1


def test_write_json_atomic_redacts_secret_like_fields(tmp_path):
    path = tmp_path / "snapshot.json"
    write_json_atomic(
        path,
        {
            "ok": True,
            "token": "secret-token-value",
            "nested": {"password": "pw123", "safe": "value"},
        },
    )

    content = path.read_text(encoding="utf-8")
    assert "secret-token-value" not in content
    assert "pw123" not in content
    assert "[REDACTED]" in content
