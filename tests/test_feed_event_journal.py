from __future__ import annotations

from pathlib import Path

import pytest

from core.feed_event_journal import (
    FEED_EVENT_QUARANTINE,
    FEED_EVENT_RECONNECT,
    FEED_EVENT_RECOVERY,
    FEED_EVENT_SUBSCRIPTION,
    FEED_EVENT_TICK,
    FEED_MODE,
    append_feed_event,
    build_feed_event,
    read_feed_events,
    validate_feed_events,
)


def test_append_and_validate_feed_journal(tmp_path: Path):
    journal = tmp_path / "feed_event.jsonl"

    first = append_feed_event(
        journal,
        event_type=FEED_EVENT_TICK,
        symbol="NIFTY",
        feed_state="healthy",
        payload={"tick": 1},
        event_ts_epoch=100.0,
    )
    second = append_feed_event(
        journal,
        event_type=FEED_EVENT_RECOVERY,
        symbol="NIFTY",
        feed_state="warming_up",
        payload={"cycle": 1},
        event_ts_epoch=101.0,
    )
    third = append_feed_event(
        journal,
        event_type=FEED_EVENT_SUBSCRIPTION,
        symbol="NIFTY",
        feed_state="candidate_ready",
        payload={"subscribed_tokens": 12},
        event_ts_epoch=102.0,
    )
    fourth = append_feed_event(
        journal,
        event_type=FEED_EVENT_QUARANTINE,
        symbol="NIFTY",
        feed_state="blocked",
        payload={"reason": "stale_option_tick"},
        event_ts_epoch=103.0,
    )

    rows = read_feed_events(journal)
    validation = validate_feed_events(rows)

    assert first.sequence == 1
    assert first.event_hash
    assert first.is_order_action is False
    assert first.broker_api_called is False
    assert first.to_payload()["read_only"] is True
    assert first.to_payload()["append"] is True
    assert rows[0]["event_type"] == FEED_EVENT_TICK
    assert rows[0]["symbol"] == "NIFTY"
    assert rows[0]["feed_state"] == "HEALTHY"
    assert second.sequence == 2
    assert second.previous_event_hash == first.event_hash
    assert third.sequence == 3
    assert third.previous_event_hash == second.event_hash
    assert fourth.sequence == 4
    assert fourth.previous_event_hash == third.event_hash
    assert rows[-1]["sequence"] == 4
    assert validation.journal_valid is True
    assert validation.event_count == 4
    assert validation.latest_sequence == 4
    assert "invalid_event_type" not in validation.reasons
    assert rows[0]["event_type"] == FEED_EVENT_TICK
    assert rows[1]["payload"]["cycle"] == 1
    assert rows[2]["feed_state"] == "CANDIDATE_READY"
    assert rows[3]["payload"]["reason"] == "stale_option_tick"


def test_invalid_event_type_is_rejected():
    validation = validate_feed_events(
        (
            {
                "schema_version": 1,
                "source": "feed_event_journal_v1",
                "event_id": "abc",
                "event_type": "UNKNOWN",
                "sequence": 1,
                "event_ts_epoch": 1.0,
                "mode": FEED_MODE,
                "symbol": "NIFTY",
                "feed_state": "HEALTHY",
                "previous_event_hash": "",
                "event_hash": "deadbeef",
                "payload": {},
                "metadata": {},
            },
        )
    )

    assert validation.journal_valid is False
    assert validation.reason_code == "invalid_event_type"
