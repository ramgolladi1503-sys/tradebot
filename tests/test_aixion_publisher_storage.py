from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from aixion_trade_intelligence.contracts import CanonicalEvent
from aixion_trade_intelligence.publisher import FilePublisher
from aixion_trade_intelligence.storage import load_events


def event(sequence: int) -> CanonicalEvent:
    now = datetime(2026, 8, 4, tzinfo=timezone.utc) + timedelta(seconds=sequence)
    return CanonicalEvent(
        event_id=str(uuid.uuid4()),
        event_type="MARKET_QUOTE",
        session_id="s",
        source_component="test",
        producer_id="p",
        producer_sequence=sequence,
        event_time=now,
        source_time=now,
        receive_time=now,
        available_time=now,
        parse_time=now,
        persist_time=now,
        instrument_key="NSE_INDEX|Nifty 50",
        payload={"ltp": 24500 + sequence},
    )


def test_file_publisher_appends_complete_events(tmp_path):
    path = tmp_path / "events.jsonl"
    publisher = FilePublisher(path, fsync=True)
    receipts = [publisher.publish(event(sequence)) for sequence in range(1, 4)]
    loaded = load_events(path)
    assert tuple(row.producer_sequence for row in loaded) == (1, 2, 3)
    assert all(receipt.bytes_written > 0 for receipt in receipts)


def test_append_events_appends_batch_atomically(tmp_path):
    from aixion_trade_intelligence.storage import append_events

    path = tmp_path / "events.jsonl"
    first = [event(1), event(2)]
    second = [event(3), event(4)]
    bytes_first = append_events(path, first, fsync=True)
    bytes_second = append_events(path, second, fsync=True)
    loaded = load_events(path)
    assert bytes_first > 0
    assert bytes_second > 0
    assert [row.producer_sequence for row in loaded] == [1, 2, 3, 4]
