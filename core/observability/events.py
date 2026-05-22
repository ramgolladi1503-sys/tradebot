from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping

from core.observability.context import ObservabilityContext
from core.observability.ids import ObservabilityIds

REQUIRED_EVENT_FIELDS = (
    "event",
    "run_id",
    "cycle_id",
    "trace_id",
    "stage",
    "decision",
    "timestamp",
    "is_order_action",
    "broker_api_called",
    "source",
)

_TERMINAL_DECISIONS_REQUIRING_REASON = frozenset({
    "blocked",
    "downgraded",
    "rejected",
    "suppressed",
    "ignored",
})

_CANDIDATE_EVENT_PREFIXES = ("candidate.",)
_DEFAULT_SOURCE = "tradebot.observability.events"


class ObservabilityEventError(ValueError):
    """Raised when an observability event violates the schema contract."""


@dataclass(frozen=True)
class ObservabilityEvent:
    """Validated read-only observability event payload.

    This schema is intentionally independent from runtime wiring. It only
    validates and serializes decision events for future logging, tracing, and
    evidence adapters.
    """

    event: str
    ids: ObservabilityIds
    stage: str
    decision: str
    timestamp: datetime
    source: str = _DEFAULT_SOURCE
    reason: str | None = None
    execution_mode: str | None = None
    attributes: Mapping[str, object] = field(default_factory=dict)
    is_order_action: bool = False
    broker_api_called: bool = False

    @classmethod
    def from_context(
        cls,
        *,
        event: str,
        context: ObservabilityContext,
        decision: str,
        timestamp: datetime,
        reason: str | None = None,
        source: str = _DEFAULT_SOURCE,
        **attributes: object,
    ) -> "ObservabilityEvent":
        """Create an event from an existing observability context."""

        merged = dict(context.attributes)
        merged.update(attributes)
        return cls(
            event=event,
            ids=context.ids,
            stage=context.stage,
            decision=decision,
            timestamp=timestamp,
            source=source,
            reason=reason,
            execution_mode=context.execution_mode,
            attributes=merged,
        )

    def validate(self) -> None:
        """Fail closed on missing identity, reason, or safety fields."""

        _require_non_empty("event", self.event)
        _require_non_empty("run_id", self.ids.run_id)
        _require_non_empty("cycle_id", self.ids.cycle_id)
        _require_non_empty("trace_id", self.ids.trace_id)
        _require_non_empty("stage", self.stage)
        _require_non_empty("decision", self.decision)
        _require_non_empty("source", self.source)

        if self._is_candidate_event() and not self.ids.candidate_id:
            raise ObservabilityEventError("candidate_event_requires_candidate_id")

        if self._decision_requires_reason() and not str(self.reason or "").strip():
            raise ObservabilityEventError("decision_requires_reason")

        if self.is_order_action:
            raise ObservabilityEventError("observability_event_cannot_be_order_action")
        if self.broker_api_called:
            raise ObservabilityEventError("observability_event_cannot_call_broker_api")

    def as_dict(self) -> dict[str, object]:
        """Return a validated plain dictionary for logs or evidence files."""

        self.validate()
        payload: dict[str, object] = {
            "event": self.event,
            **self.ids.as_dict(),
            "stage": self.stage,
            "decision": self.decision,
            "timestamp": _format_timestamp(self.timestamp),
            "is_order_action": False,
            "broker_api_called": False,
            "source": self.source,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.execution_mode is not None:
            payload["execution_mode"] = self.execution_mode
        payload.update(dict(self.attributes))
        return payload

    def _is_candidate_event(self) -> bool:
        return self.event.startswith(_CANDIDATE_EVENT_PREFIXES)

    def _decision_requires_reason(self) -> bool:
        return self.decision.strip().lower() in _TERMINAL_DECISIONS_REQUIRING_REASON


def validate_event_payload(payload: Mapping[str, object]) -> None:
    """Validate a serialized event payload from tests or adapters."""

    for field_name in REQUIRED_EVENT_FIELDS:
        if field_name not in payload:
            raise ObservabilityEventError(f"required_field_missing:{field_name}")
        if field_name not in {"is_order_action", "broker_api_called"} and not str(payload[field_name]).strip():
            raise ObservabilityEventError(f"required_field_empty:{field_name}")

    if payload.get("is_order_action") is not False:
        raise ObservabilityEventError("is_order_action_must_be_false")
    if payload.get("broker_api_called") is not False:
        raise ObservabilityEventError("broker_api_called_must_be_false")

    event_name = str(payload.get("event", ""))
    if event_name.startswith(_CANDIDATE_EVENT_PREFIXES) and not str(payload.get("candidate_id", "")).strip():
        raise ObservabilityEventError("candidate_event_requires_candidate_id")

    decision = str(payload.get("decision", "")).strip().lower()
    if decision in _TERMINAL_DECISIONS_REQUIRING_REASON and not str(payload.get("reason", "")).strip():
        raise ObservabilityEventError("decision_requires_reason")


def _require_non_empty(field_name: str, value: str) -> None:
    if not str(value).strip():
        raise ObservabilityEventError(f"required_field_empty:{field_name}")


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
