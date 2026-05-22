from __future__ import annotations

import json
from datetime import datetime, timezone
from io import StringIO

import pytest

from core.observability import (
    ObservabilityEvent,
    ObservabilityEventError,
    ObservabilityIds,
    ObservabilityJsonLogError,
    ObservabilityJsonLogger,
    event_to_json_line,
    payload_to_json_line,
)


def _timestamp() -> datetime:
    return datetime(2026, 5, 23, 4, 15, 2, tzinfo=timezone.utc)


def _event() -> ObservabilityEvent:
    return ObservabilityEvent(
        event="candidate.generated",
        ids=ObservabilityIds(
            run_id="run_1",
            cycle_id="cycle_1",
            trace_id="trace_1",
            candidate_id="candidate_1",
        ),
        stage="candidate.generated",
        decision="generated",
        timestamp=_timestamp(),
        execution_mode="PAPER",
        attributes={"symbol": "NIFTY", "score": 0.72},
    )


def test_event_to_json_line_returns_deterministic_jsonl() -> None:
    line = event_to_json_line(_event())

    assert line.endswith("\n")
    payload = json.loads(line)
    assert payload["event"] == "candidate.generated"
    assert payload["candidate_id"] == "candidate_1"
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["timestamp"] == "2026-05-23T04:15:02Z"
    assert list(json.loads(line).keys()) == sorted(payload.keys())


def test_payload_to_json_line_validates_raw_payload() -> None:
    payload = _event().as_dict()

    line = payload_to_json_line(payload)

    assert json.loads(line)["trace_id"] == "trace_1"


def test_payload_to_json_line_rejects_invalid_payload() -> None:
    payload = _event().as_dict()
    payload.pop("source")

    with pytest.raises(ObservabilityEventError, match="required_field_missing:source"):
        payload_to_json_line(payload)


def test_json_logger_writes_and_flushes_one_line() -> None:
    stream = StringIO()
    logger = ObservabilityJsonLogger(stream)

    payload = logger.write_event(_event())

    assert payload["candidate_id"] == "candidate_1"
    assert stream.getvalue().count("\n") == 1
    assert json.loads(stream.getvalue())["symbol"] == "NIFTY"


def test_json_logger_requires_stream() -> None:
    with pytest.raises(ObservabilityJsonLogError, match="stream_required"):
        ObservabilityJsonLogger(None)  # type: ignore[arg-type]


def test_json_logger_rejects_invalid_event_before_write() -> None:
    stream = StringIO()
    logger = ObservabilityJsonLogger(stream)
    invalid_event = ObservabilityEvent(
        event="candidate.generated",
        ids=ObservabilityIds(run_id="run_1", cycle_id="cycle_1", trace_id="trace_1"),
        stage="candidate.generated",
        decision="generated",
        timestamp=_timestamp(),
    )

    with pytest.raises(ObservabilityEventError, match="candidate_event_requires_candidate_id"):
        logger.write_event(invalid_event)
    assert stream.getvalue() == ""
