from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class StageResult:
    value: Any
    stage_names: tuple[str, ...]


class TradeBuilderStagePipeline:
    """Compatibility seam for incremental TradeBuilder extraction.

    No production stage is moved here until a golden-master test proves the
    extracted callable preserves the existing facade's output.
    """

    def __init__(self, stages: Iterable[tuple[str, Callable[[Any], Any]]] = ()) -> None:
        self._stages = tuple(stages)

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self._stages)

    def run(self, value: Any) -> StageResult:
        current = value
        completed: list[str] = []
        for name, stage in self._stages:
            current = stage(current)
            completed.append(name)
        return StageResult(value=current, stage_names=tuple(completed))

    @classmethod
    def passthrough(cls) -> "TradeBuilderStagePipeline":
        return cls(())


__all__ = ["StageResult", "TradeBuilderStagePipeline"]
