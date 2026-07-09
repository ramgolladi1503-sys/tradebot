from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class StageTiming:
    stage: str
    elapsed_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeCycleContext:
    cycle_id: str
    feed_truth: Mapping[str, Any] | None = None
    stage_timings: tuple[StageTiming, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "feed_truth": dict(self.feed_truth or {}),
            "stage_timings": [item.to_dict() for item in self.stage_timings],
            "metadata": dict(self.metadata),
        }


def add_stage_timing(
    context: RuntimeCycleContext,
    *,
    stage: str,
    elapsed_ms: float,
    metadata: Mapping[str, Any] | None = None,
) -> RuntimeCycleContext:
    return RuntimeCycleContext(
        cycle_id=context.cycle_id,
        feed_truth=context.feed_truth,
        stage_timings=context.stage_timings + (StageTiming(stage=str(stage), elapsed_ms=float(elapsed_ms), metadata=dict(metadata or {})),),
        metadata=dict(context.metadata),
    )


__all__ = ["RuntimeCycleContext", "StageTiming", "add_stage_timing"]
