from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import uuid

import pytest

from aixion_trade_intelligence.contracts import CanonicalEvent, EventValidationError


def make_event(**overrides):
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    values = {
        "event_id": str(uuid.uuid4()),
        "event_type": "SESSION_STARTED",
        "session_id": "session-1",
        "source_component": "test",
        "producer_id": "producer",
        "producer_sequence": 1,
        "event_time": now,
        "source_time": now,
        "receive_time": now + timedelta(milliseconds=1),
        "available_time": now + timedelta(milliseconds=1),
        "parse_time": now + timedelta(milliseconds=2),
        "persist_time": now + timedelta(milliseconds=3),
        "payload": {"value": 1.0},
    }
    values.update(overrides)
    return CanonicalEvent(**values)


def test_round_trip_is_canonical():
    event = make_event()
    restored = CanonicalEvent.from_json(event.to_json())
    assert restored == event
    assert json.loads(event.to_json())["payload_hash"] == event.payload_hash


def test_payload_hash_is_verified():
    with pytest.raises(EventValidationError, match="payload_hash"):
        make_event(payload_hash="0" * 64)


def test_naive_timestamp_is_rejected():
    with pytest.raises(EventValidationError, match="timezone"):
        make_event(event_time=datetime(2026, 8, 4))


def test_nonfinite_payload_is_rejected():
    with pytest.raises(EventValidationError, match="non-finite"):
        make_event(payload={"bad": float("nan")})


def test_available_time_cannot_precede_event():
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    with pytest.raises(EventValidationError, match="available_time"):
        make_event(event_time=now, available_time=now - timedelta(seconds=1))
