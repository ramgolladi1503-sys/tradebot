from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from core.observability.ids import ObservabilityIds, build_span_id


@dataclass(frozen=True)
class ObservabilityContext:
    """Read-only context payload shared by future observability adapters."""

    ids: ObservabilityIds
    stage: str
    execution_mode: str
    attributes: Mapping[str, object] = field(default_factory=dict)

    def for_stage(self, stage: str, **attributes: object) -> "ObservabilityContext":
        """Return a copied context for a child stage without mutating this one."""

        merged = dict(self.attributes)
        merged.update(attributes)
        return ObservabilityContext(
            ids=ObservabilityIds(
                run_id=self.ids.run_id,
                cycle_id=self.ids.cycle_id,
                trace_id=self.ids.trace_id,
                span_id=build_span_id(stage=stage, trace_id=self.ids.trace_id),
                candidate_id=self.ids.candidate_id,
            ),
            stage=stage,
            execution_mode=self.execution_mode,
            attributes=merged,
        )

    def with_candidate(self, candidate_id: str, **attributes: object) -> "ObservabilityContext":
        """Return a copied context scoped to a candidate."""

        merged = dict(self.attributes)
        merged.update(attributes)
        return ObservabilityContext(
            ids=ObservabilityIds(
                run_id=self.ids.run_id,
                cycle_id=self.ids.cycle_id,
                trace_id=self.ids.trace_id,
                span_id=self.ids.span_id,
                candidate_id=candidate_id,
            ),
            stage=self.stage,
            execution_mode=self.execution_mode,
            attributes=merged,
        )

    def as_dict(self) -> dict[str, object]:
        """Serialize context into a plain dictionary for logs/events later."""

        payload: dict[str, object] = {
            **self.ids.as_dict(),
            "stage": self.stage,
            "execution_mode": self.execution_mode,
            "is_order_action": False,
            "broker_api_called": False,
        }
        payload.update(dict(self.attributes))
        return payload
