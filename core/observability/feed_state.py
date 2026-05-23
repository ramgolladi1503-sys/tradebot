from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from core.observability.context import ObservabilityContext
from core.observability.events import ObservabilityEvent
from core.observability.ids import ObservabilityIds, build_span_id
from core.observability.json_logger import ObservabilityJsonLogger

_SOURCE = "tradebot.observability.feed_state"
_FALLBACK_STATES = frozenset({"recovered_fallback", "fallback_recovered"})
_STALE_STATES = frozenset({"stale", "stale_feed"})


class FeedStateEventError(ValueError):
    """Raised when a feed-state observability event violates the safety contract."""


@dataclass(frozen=True)
class FeedStateEventEmitter:
    """Read-only feed freshness and quote-source event shell."""

    context: ObservabilityContext
    source: str = _SOURCE

    def feed_fresh(self, *, timestamp: datetime, feed_age_ms: int | float, **attributes: object) -> ObservabilityEvent:
        return self._event(
            event="feed.fresh",
            stage="feed.freshness_check",
            decision="fresh",
            timestamp=timestamp,
            attributes={"feed_age_ms": feed_age_ms, "feed_state": "fresh", **attributes},
        )

    def feed_stale(self, *, timestamp: datetime, feed_age_ms: int | float, reason: str = "STALE_FEED", **attributes: object) -> ObservabilityEvent:
        return self._event(
            event="feed.stale",
            stage="feed.freshness_check",
            decision="blocked",
            timestamp=timestamp,
            reason=reason,
            attributes={"feed_age_ms": feed_age_ms, "feed_state": "stale", **attributes},
        )

    def quote_real(self, *, timestamp: datetime, candidate_id: str | None = None, **attributes: object) -> ObservabilityEvent:
        return self._event(
            event="quote.real",
            stage="quote.source",
            decision="real_quote",
            timestamp=timestamp,
            candidate_id=candidate_id,
            attributes={"quote_source": "real", "fallback_state": "none", **attributes},
        )

    def quote_missing(self, *, timestamp: datetime, reason: str = "QUOTE_MISSING", candidate_id: str | None = None, **attributes: object) -> ObservabilityEvent:
        return self._event(
            event="quote.missing",
            stage="quote.source",
            decision="blocked",
            timestamp=timestamp,
            reason=reason,
            candidate_id=candidate_id,
            attributes={"quote_source": "missing", **attributes},
        )

    def quote_fallback_used(self, *, timestamp: datetime, candidate_id: str | None = None, **attributes: object) -> ObservabilityEvent:
        return self._event(
            event="quote.fallback_used",
            stage="quote.source",
            decision="fallback_used",
            timestamp=timestamp,
            candidate_id=candidate_id,
            attributes={
                "quote_source": "fallback",
                "fallback_state": "recovered_fallback",
                "displayable": True,
                "executable": False,
                **attributes,
            },
        )

    def blocked_fallback(self, *, timestamp: datetime, candidate_id: str, reason: str = "FALLBACK_NOT_EXECUTABLE", **attributes: object) -> ObservabilityEvent:
        return self._event(
            event="execution.blocked_fallback",
            stage="execution.safety_gate",
            decision="blocked",
            timestamp=timestamp,
            reason=reason,
            candidate_id=candidate_id,
            attributes={
                "fallback_state": "recovered_fallback",
                "displayable": True,
                "executable": False,
                **attributes,
            },
        )

    def blocked_stale_feed(self, *, timestamp: datetime, candidate_id: str, feed_age_ms: int | float, reason: str = "STALE_FEED_NOT_EXECUTABLE", **attributes: object) -> ObservabilityEvent:
        return self._event(
            event="execution.blocked_stale_feed",
            stage="execution.safety_gate",
            decision="blocked",
            timestamp=timestamp,
            reason=reason,
            candidate_id=candidate_id,
            attributes={
                "feed_age_ms": feed_age_ms,
                "feed_state": "stale",
                "displayable": True,
                "executable": False,
                **attributes,
            },
        )

    def validate_state(self, *, fallback_state: object = None, feed_state: object = None, decision: object = None, executable: object = None) -> None:
        _validate_state(fallback_state=fallback_state, feed_state=feed_state, decision=decision, executable=executable)

    def write_event(self, logger: ObservabilityJsonLogger, event: ObservabilityEvent) -> dict[str, object]:
        return logger.write_event(event)

    def _event(
        self,
        *,
        event: str,
        stage: str,
        decision: str,
        timestamp: datetime,
        attributes: Mapping[str, object],
        reason: str | None = None,
        candidate_id: str | None = None,
    ) -> ObservabilityEvent:
        if decision == "blocked" and not str(reason or "").strip():
            raise FeedStateEventError("blocked_event_requires_reason")
        _validate_state(
            fallback_state=attributes.get("fallback_state"),
            feed_state=attributes.get("feed_state"),
            decision=decision,
            executable=attributes.get("executable"),
        )
        context = self._context_for(stage=stage, candidate_id=candidate_id, attributes=attributes)
        return ObservabilityEvent.from_context(
            event=event,
            context=context,
            decision=decision,
            timestamp=timestamp,
            reason=reason,
            source=self.source,
        )

    def _context_for(self, *, stage: str, candidate_id: str | None, attributes: Mapping[str, object]) -> ObservabilityContext:
        merged = dict(self.context.attributes)
        merged.update(dict(attributes))
        return ObservabilityContext(
            ids=ObservabilityIds(
                run_id=self.context.ids.run_id,
                cycle_id=self.context.ids.cycle_id,
                trace_id=self.context.ids.trace_id,
                span_id=build_span_id(stage=stage, trace_id=self.context.ids.trace_id),
                candidate_id=candidate_id or self.context.ids.candidate_id,
            ),
            stage=stage,
            execution_mode=self.context.execution_mode,
            attributes=merged,
        )


def _validate_state(*, fallback_state: object, feed_state: object, decision: object, executable: object) -> None:
    decision_is_executable = str(decision or "").strip().lower() == "executable"
    executable_is_true = executable is True or str(executable).strip().lower() == "true"
    fallback_is_recovered = str(fallback_state or "").strip().lower() in _FALLBACK_STATES
    feed_is_stale = str(feed_state or "").strip().lower() in _STALE_STATES

    if fallback_is_recovered and (decision_is_executable or executable_is_true):
        raise FeedStateEventError("fallback_state_cannot_be_executable")
    if feed_is_stale and (decision_is_executable or executable_is_true):
        raise FeedStateEventError("stale_feed_cannot_be_executable")
