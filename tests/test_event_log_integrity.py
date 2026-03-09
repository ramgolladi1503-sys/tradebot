from __future__ import annotations

import json
from pathlib import Path

from core.event_log import build_state_from_events, iter_events, validate_and_repair


def _write_rows_with_truncated_tail(path: Path) -> None:
    rows = [
        {
            "ts": "2026-03-04T09:15:00Z",
            "type": "trade_intent_created",
            "payload": {"event_id": "evt_1", "trade_id": "trd_1", "order_id": "ord_1"},
        },
        {
            "ts": "2026-03-04T09:15:02Z",
            "type": "order_submitted",
            "payload": {"event_id": "evt_2", "trade_id": "trd_2", "order_id": "ord_2"},
        },
    ]
    with path.open("wb") as handle:
        for row in rows:
            handle.write((json.dumps(row, sort_keys=True) + "\n").encode("utf-8"))
        handle.write(b'{"ts":"2026-03-04T09:15:03Z","type":"fill","payload":{"event_id":"evt_bad"')


def test_validate_and_repair_truncated_tail(tmp_path):
    events_path = tmp_path / "events.jsonl"
    _write_rows_with_truncated_tail(events_path)

    result = validate_and_repair(events_path)
    assert result["repaired"] is True
    assert result["bytes_trimmed"] > 0
    assert result["ok"] is True
    assert result["truncated_tail"] is False

    rows = list(iter_events(events_path))
    assert len(rows) == 2
    assert rows[0]["payload"]["event_id"] == "evt_1"
    assert rows[1]["payload"]["event_id"] == "evt_2"


def test_build_state_from_events_ignores_duplicate_trade_events(tmp_path):
    events_path = tmp_path / "events.jsonl"
    rows = [
        {
            "ts": "2026-03-04T09:16:00Z",
            "type": "trade_intent_created",
            "payload": {"event_id": "evt_1", "trade_id": "trd_dup", "order_id": "ord_1"},
        },
        {
            # Duplicate trade event (same trade_id + type) should be ignored.
            "ts": "2026-03-04T09:16:01Z",
            "type": "trade_intent_created",
            "payload": {"event_id": "evt_2", "trade_id": "trd_dup", "order_id": "ord_2"},
        },
        {
            "ts": "2026-03-04T09:16:02Z",
            "type": "fill",
            "payload": {"event_id": "evt_3", "trade_id": "trd_dup", "order_id": "ord_3"},
        },
        {
            "ts": "2026-03-04T09:16:03Z",
            "type": "trade_intent_created",
            "payload": {"event_id": "evt_4", "trade_id": "trd_2", "order_id": "ord_4"},
        },
    ]
    with events_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    state = build_state_from_events(events_path)
    assert state.seen_trade_ids == {"trd_dup", "trd_2"}
    # evt_2 is duplicate of evt_1 by trade_id + type and should be skipped.
    kept_event_ids = [row["payload"]["event_id"] for row in state.unique_events]
    assert kept_event_ids == ["evt_1", "evt_3", "evt_4"]
    assert state.duplicate_count == 1
