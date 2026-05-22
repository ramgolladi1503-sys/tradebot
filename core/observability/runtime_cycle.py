from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from core.observability.context import ObservabilityContext
from core.observability.events import ObservabilityEvent
from core.observability.json_logger import ObservabilityJsonLogger

_RUNTIME_CYCLE_STAGE = "runtime.cycle"
_RUNTIME_CYCLE_SOURCE = "tradebot.observability.runtime_cycle"


class RuntimeCycleEventError(ValueError):
    """Raised when a runtime-cycle observability event cannot be emitted safely."""


@dataclass(frozen=True)
class RuntimeCycleEventEmitter:
    """Read-only runtime-cycle event shell.

    This emitter only builds validated observability events and optionally writes
    them through the structured JSON logger. It is intentionally not wired into
    live runtime startup, broker paths, strategy selection, risk, ranking, or
    dashboard behavior.
    """

    context: ObservabilityContext
    source: str = _RUNTIME_CYCLE_SOURCE

    def cycle_started(
        self,
        *,
        timestamp: datetime,
        **attributes: object,
    ) -> ObservabilityEvent:
        return self._event(
            suffix="started",
            decision="started",
            timestamp=timestamp,
            attributes=attributes,
        )

    def cycle_completed(
        self,
        *,
        timestamp: datetime,
        **attributes: object,
    ) -> ObservabilityEvent:
        return self._event(
            suffix="completed",
            decision="completed",
            timestamp=timestamp,
            attributes=attributes,
        )

    def cycle_failed(
        self,
        *,
        timestamp: datetime,
        reason: str,
        **attributes: object,
    ) -> ObservabilityEvent:
        if not str(reason).strip():
            raise RuntimeCycleEventError("cycle_failed_requires_reason")
        return self._event(
            suffix="failed",
            decision="failed",
            timestamp=timestamp,
            reason=reason,
            attributes=attributes,
        )

    def write_started(
        self,
        logger: ObservabilityJsonLogger,
        *,
        timestamp: datetime,
        **attributes: object,
    ) -> dict[str, object]:
        return logger.write_event(self.cycle_started(timestamp=timestamp, **attributes))

    def write_completed(
        self,
        logger: ObservabilityJsonLogger,
        *,
        timestamp: datetime,
        **attributes: object,
    ) -> dict[str, object]:
        return logger.write_event(self.cycle_completed(timestamp=timestamp, **attributes))

    def write_failed(
        self,
        logger: ObservabilityJsonLogger,
        *,
        timestamp: datetime,
        reason: str,
        **attributes: object,
    ) -> dict[str, object]:
        return logger.write_event(
            self.cycle_failed(timestamp=timestamp, reason=reason, **attributes)
        )

    def _event(
        self,
        *,
        suffix: str,
        decision: str,
        timestamp: datetime,
        attributes: Mapping[str, object],
        reason: str | None = None,
    ) -> ObservabilityEvent:
        context = self.context.for_stage(_RUNTIME_CYCLE_STAGE, **dict(attributes))
        return ObservabilityEvent.from_context(
            event=f"runtime.cycle.{suffix}",
            context=context,
            decision=decision,
            timestamp=timestamp,
            reason=reason,
            source=self.source,
        )
