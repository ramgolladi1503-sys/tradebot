from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class OrchestratorStageResult:
    context: Any
    completed_stages: tuple[str, ...]


class OrchestratorStagePipeline:
    """Behavior-neutral seam for extracting orchestration stages one at a time."""

    def __init__(self, stages: Iterable[tuple[str, Callable[[Any], Any]]] = ()) -> None:
        self._stages = tuple(stages)

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self._stages)

    def run(self, context: Any) -> OrchestratorStageResult:
        current = context
        completed: list[str] = []
        for name, stage in self._stages:
            current = stage(current)
            completed.append(name)
        return OrchestratorStageResult(context=current, completed_stages=tuple(completed))

    @classmethod
    def passthrough(cls) -> "OrchestratorStagePipeline":
        return cls(())


__all__ = ["OrchestratorStagePipeline", "OrchestratorStageResult"]
