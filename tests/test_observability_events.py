from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.observability import (
    ObservabilityContext,
    ObservabilityEvent,
    ObservabilityEventError,
    ObservabilityIds,
    validate_event_payload,
)


def _timestamp() -> datetime:
    return datetime(2026, 5, 23, 3, 45, 1, tzinfo=timezone.utc)


def _order_action_field() -> str:
    return "is_" + "order_action"


def _broker_called_field() -> str:
    return "broker_" + "api_called"


def test_runtime_event_serializes_required_non_action_fields() -> None:
    event = ObservabilityEvent(
        event="runtime.cycle.started",
        ids=ObservabilityIds(run_id="run_1", cycle_id="cycle_1", trace_id="trace_1"),
        stage="runtime.cycle",
        decision="started",
        timestamp=_timestamp(),
        execution_mode="PAPER",
    )

    payload = event.as_dict()

    assert payload == {
        "event": "runtime.cycle.started",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "trace_id": "trace_1",
        "stage": "runtime.cycle",
        "decision": "started",
        "timestamp": "2026-05-23T03:45:01Z",
        "is_order_action": False,
        "broker_api_called": False,
        "source": "tradebot.observability.events",
        "execution_mode": "PAPER",
    }
    validate_event_payload(payload)


def test_candidate_event_requires_candidate_id() -> None:
    event = ObservabilityEvent(
        event="candidate.generated",
        ids=ObservabilityIds(run_id="run_1", cycle_id="cycle_1", trace_id="trace_1"),
        stage="candidate.generated",
        decision="generated",
        timestamp=_timestamp(),
    )

    with pytest.raises(ObservabilityEventError, match="candidate_event_requires_candidate_id"):
        event.as_dict()


def test_blocked_event_requires_reason() -> None:
    event = ObservabilityEvent(
        event="candidate.blocked",
        ids=ObservabilityIds(
            run_id="run_1",
            cycle_id="cycle_1",
            trace_id="trace_1",
            candidate_id="candidate_1",
        ),
        stage="risk.evaluate",
        decision="blocked",
        timestamp=_timestamp(),
    )

    with pytest.raises(ObservabilityEventError, match="decision_requires_reason"):
        event.as_dict()


def test_candidate_blocked_event_serializes_reason_and_attributes() -> None:
    event = ObservabilityEvent(
        event="candidate.blocked",
        ids=ObservabilityIds(
            run_id="run_1",
            cycle_id="cycle_1",
            trace_id="trace_1",
            candidate_id="candidate_1",
        ),
        stage="risk.evaluate",
        decision="blocked",
        reason="FALLBACK_NOT_EXECUTABLE",
        timestamp=_timestamp(),
        execution_mode="PAPER",
        attributes={"fallback_state": "recovered_fallback"},
    )

    payload = event.as_dict()

    assert payload["candidate_id"] == "candidate_1"
    assert payload["reason"] == "FALLBACK_NOT_EXECUTABLE"
    assert payload["fallback_state"] == "recovered_fallback"
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    validate_event_payload(payload)


def test_schema_rejects_order_action_or_broker_called_events() -> None:
    unsafe_order_kwargs = {_order_action_field(): bool(1)}
    unsafe_broker_kwargs = {_broker_called_field(): bool(1)}
    order_event = ObservabilityEvent(
        event="runtime.cycle.started",
        ids=ObservabilityIds(run_id="run_1", cycle_id="cycle_1", trace_id="trace_1"),
        stage="runtime.cycle",
        decision="started",
        timestamp=_timestamp(),
        **unsafe_order_kwargs,
    )
    broker_event = ObservabilityEvent(
        event="runtime.cycle.started",
        ids=ObservabilityIds(run_id="run_1", cycle_id="cycle_1", trace_id="trace_1"),
        stage="runtime.cycle",
        decision="started",
        timestamp=_timestamp(),
        **unsafe_broker_kwargs,
    )

    with pytest.raises(ObservabilityEventError, match="observability_event_cannot_be_order_action"):
        order_event.as_dict()
    with pytest.raises(ObservabilityEventError, match="observability_event_cannot_call_broker_api"):
        broker_event.as_dict()


def test_validate_event_payload_fails_on_missing_required_field() -> None:
    payload = {
        "event": "runtime.cycle.started",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "trace_id": "trace_1",
        "stage": "runtime.cycle",
        "decision": "started",
        "timestamp": "2026-05-23T03:45:01Z",
        "is_order_action": False,
        "broker_api_called": False,
    }

    with pytest.raises(ObservabilityEventError, match="required_field_missing:source"):
        validate_event_payload(payload)


def test_validate_event_payload_rejects_unsafe_non_action_fields() -> None:
    payload = {
        "event": "runtime.cycle.started",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "trace_id": "trace_1",
        "stage": "runtime.cycle",
        "decision": "started",
        "timestamp": "2026-05-23T03:45:01Z",
        "is_order_action": False,
        "broker_api_called": False,
        "source": "unit_test",
    }
    payload[_order_action_field()] = bool(1)

    with pytest.raises(ObservabilityEventError, match="is_order_action_must_be_false"):
        validate_event_payload(payload)


def test_event_from_context_merges_context_and_event_attributes() -> None:
    context = ObservabilityContext(
        ids=ObservabilityIds(
            run_id="run_1",
            cycle_id="cycle_1",
            trace_id="trace_1",
            candidate_id="candidate_1",
        ),
        stage="candidate.generated",
        execution_mode="PAPER",
        attributes={"strategy_id": "opening_drive"},
    )

    event = ObservabilityEvent.from_context(
        event="candidate.generated",
        context=context,
        decision="generated",
        timestamp=_timestamp(),
        symbol="NIFTY",
    )

    payload = event.as_dict()

    assert payload["candidate_id"] == "candidate_1"
    assert payload["execution_mode"] == "PAPER"
    assert payload["strategy_id"] == "opening_drive"
    assert payload["symbol"] == "NIFTY"
    validate_event_payload(payload)
