from __future__ import annotations

import json
from datetime import datetime, timezone
from io import StringIO

import pytest

from core.observability import (
    ObservabilityContext,
    ObservabilityIds,
    ObservabilityJsonLogger,
    RuntimeCycleEventEmitter,
    RuntimeCycleEventError,
    validate_event_payload,
)


def _timestamp() -> datetime:
    return datetime(2026, 5, 23, 6, 30, 5, tzinfo=timezone.utc)


def _context() -> ObservabilityContext:
    return ObservabilityContext(
        ids=ObservabilityIds(
            run_id="run_obs_04",
            cycle_id="cycle_obs_04_000001",
            trace_id="trace_obs_04",
        ),
        stage="runtime.bootstrap",
        execution_mode="PAPER",
        attributes={"runtime_mode": "dry_run"},
    )


def test_cycle_started_builds_valid_non_action_event() -> None:
    emitter = RuntimeCycleEventEmitter(_context())

    payload = emitter.cycle_started(timestamp=_timestamp(), sequence=1).as_dict()

    assert payload["event"] == "runtime.cycle.started"
    assert payload["stage"] == "runtime.cycle"
    assert payload["decision"] == "started"
    assert payload["run_id"] == "run_obs_04"
    assert payload["cycle_id"] == "cycle_obs_04_000001"
    assert payload["trace_id"] == "trace_obs_04"
    assert payload["span_id"].startswith("span_runtime.cycle_")
    assert payload["execution_mode"] == "PAPER"
    assert payload["runtime_mode"] == "dry_run"
    assert payload["sequence"] == 1
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["source"] == "tradebot.observability.runtime_cycle"
    validate_event_payload(payload)


def test_cycle_completed_preserves_summary_attributes() -> None:
    emitter = RuntimeCycleEventEmitter(_context())

    payload = emitter.cycle_completed(
        timestamp=_timestamp(),
        candidates_seen=12,
        candidates_emitted=3,
    ).as_dict()

    assert payload["event"] == "runtime.cycle.completed"
    assert payload["decision"] == "completed"
    assert payload["candidates_seen"] == 12
    assert payload["candidates_emitted"] == 3
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    validate_event_payload(payload)


def test_cycle_failed_requires_reason() -> None:
    emitter = RuntimeCycleEventEmitter(_context())

    with pytest.raises(RuntimeCycleEventError, match="cycle_failed_requires_reason"):
        emitter.cycle_failed(timestamp=_timestamp(), reason="  ")


def test_cycle_failed_serializes_reason_without_order_action() -> None:
    emitter = RuntimeCycleEventEmitter(_context())

    payload = emitter.cycle_failed(
        timestamp=_timestamp(),
        reason="feed_snapshot_unavailable",
        safe_shutdown=True,
    ).as_dict()

    assert payload["event"] == "runtime.cycle.failed"
    assert payload["decision"] == "failed"
    assert payload["reason"] == "feed_snapshot_unavailable"
    assert payload["safe_shutdown"] is True
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    validate_event_payload(payload)


def test_write_started_uses_json_logger_without_runtime_side_effects() -> None:
    stream = StringIO()
    logger = ObservabilityJsonLogger(stream)
    emitter = RuntimeCycleEventEmitter(_context())

    payload = emitter.write_started(logger, timestamp=_timestamp(), sequence=2)

    assert payload["event"] == "runtime.cycle.started"
    assert stream.getvalue().count("\n") == 1
    written = json.loads(stream.getvalue())
    assert written["event"] == "runtime.cycle.started"
    assert written["sequence"] == 2
    assert written["is_order_action"] is False
    assert written["broker_api_called"] is False


def test_write_failed_rejects_invalid_failed_event_before_write() -> None:
    stream = StringIO()
    logger = ObservabilityJsonLogger(stream)
    emitter = RuntimeCycleEventEmitter(_context())

    with pytest.raises(RuntimeCycleEventError, match="cycle_failed_requires_reason"):
        emitter.write_failed(logger, timestamp=_timestamp(), reason="")

    assert stream.getvalue() == ""
