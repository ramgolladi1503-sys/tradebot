from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from core.observability.context import ObservabilityContext
from core.observability.events import ObservabilityEvent
from core.observability.ids import ObservabilityIds, build_span_id
from core.observability.json_logger import ObservabilityJsonLogger

_CANDIDATE_SOURCE = "tradebot.observability.candidate_lifecycle"

_TERMINAL_DECISIONS_REQUIRING_REASON = frozenset(
    {
        "blocked",
        "downgraded",
        "ignored",
    }
)


class CandidateLifecycleEventError(ValueError):
    """Raised when a candidate lifecycle event cannot be built safely."""


@dataclass(frozen=True)
class CandidateLifecycleEventEmitter:
    """Read-only candidate lifecycle event shell.

    This emitter only builds validated candidate lifecycle observability events
    and optionally writes them through the structured JSON logger. It does not
    generate candidates, change ranking, evaluate risk, write dashboard state,
    submit paper orders, call brokers, or mutate trading behavior.
    """

    context: ObservabilityContext
    candidate_id: str
    source: str = _CANDIDATE_SOURCE

    def __post_init__(self) -> None:
        if not str(self.candidate_id).strip():
            raise CandidateLifecycleEventError("candidate_id_required")

    def generated(self, *, timestamp: datetime, **attributes: object) -> ObservabilityEvent:
        return self._event(
            stage="candidate.generated",
            decision="generated",
            timestamp=timestamp,
            attributes=attributes,
        )

    def normalized(self, *, timestamp: datetime, **attributes: object) -> ObservabilityEvent:
        return self._event(
            stage="candidate.normalized",
            decision="normalized",
            timestamp=timestamp,
            attributes=attributes,
        )

    def scored(self, *, timestamp: datetime, **attributes: object) -> ObservabilityEvent:
        return self._event(
            stage="candidate.scored",
            decision="scored",
            timestamp=timestamp,
            attributes=attributes,
        )

    def ranked(self, *, timestamp: datetime, **attributes: object) -> ObservabilityEvent:
        return self._event(
            stage="candidate.ranked",
            decision="ranked",
            timestamp=timestamp,
            attributes=attributes,
        )

    def displayed(self, *, timestamp: datetime, **attributes: object) -> ObservabilityEvent:
        return self._event(
            stage="candidate.displayed",
            decision="displayed",
            timestamp=timestamp,
            attributes=attributes,
        )

    def paper_ready(self, *, timestamp: datetime, **attributes: object) -> ObservabilityEvent:
        return self._event(
            stage="candidate.paper_ready",
            decision="paper_ready",
            timestamp=timestamp,
            attributes=attributes,
        )

    def paper_submitted(self, *, timestamp: datetime, **attributes: object) -> ObservabilityEvent:
        return self._event(
            stage="candidate.paper_submitted",
            decision="paper_submitted",
            timestamp=timestamp,
            attributes=attributes,
        )

    def blocked(
        self,
        *,
        timestamp: datetime,
        reason: str,
        **attributes: object,
    ) -> ObservabilityEvent:
        return self._event(
            stage="candidate.blocked",
            decision="blocked",
            timestamp=timestamp,
            reason=reason,
            attributes=attributes,
        )

    def downgraded(
        self,
        *,
        timestamp: datetime,
        reason: str,
        **attributes: object,
    ) -> ObservabilityEvent:
        return self._event(
            stage="candidate.downgraded",
            decision="downgraded",
            timestamp=timestamp,
            reason=reason,
            attributes=attributes,
        )

    def ignored_with_reason(
        self,
        *,
        timestamp: datetime,
        reason: str,
        **attributes: object,
    ) -> ObservabilityEvent:
        return self._event(
            stage="candidate.ignored",
            decision="ignored",
            timestamp=timestamp,
            reason=reason,
            attributes=attributes,
        )

    def write_event(self, logger: ObservabilityJsonLogger, event: ObservabilityEvent) -> dict[str, object]:
        return logger.write_event(event)

    def _event(
        self,
        *,
        stage: str,
        decision: str,
        timestamp: datetime,
        attributes: Mapping[str, object],
        reason: str | None = None,
    ) -> ObservabilityEvent:
        if decision in _TERMINAL_DECISIONS_REQUIRING_REASON and not str(reason or "").strip():
            raise CandidateLifecycleEventError(f"{decision}_requires_reason")
        context = self._candidate_context(stage=stage, attributes=attributes)
        return ObservabilityEvent.from_context(
            event=stage,
            context=context,
            decision=decision,
            timestamp=timestamp,
            reason=reason,
            source=self.source,
        )

    def _candidate_context(
        self,
        *,
        stage: str,
        attributes: Mapping[str, object],
    ) -> ObservabilityContext:
        merged = dict(self.context.attributes)
        merged.update(dict(attributes))
        return ObservabilityContext(
            ids=ObservabilityIds(
                run_id=self.context.ids.run_id,
                cycle_id=self.context.ids.cycle_id,
                trace_id=self.context.ids.trace_id,
                span_id=build_span_id(stage=stage, trace_id=self.context.ids.trace_id),
                candidate_id=self.candidate_id,
            ),
            stage=stage,
            execution_mode=self.context.execution_mode,
            attributes=merged,
        )
