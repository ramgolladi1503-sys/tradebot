"""Small deterministic orchestration-stage kernel for shadow characterization.

The production Orchestrator is not replaced here. This kernel provides immutable
cycle input, ordered stages, fail-closed critical behavior, and explicit broker
authority boundaries before a safe facade migration.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence


StageCallable = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _deep_freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _mutable_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _mutable_copy(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_mutable_copy(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_mutable_copy(item) for item in value), key=repr)
    return copy.deepcopy(value)


@dataclass(frozen=True)
class PipelineStage:
    name: str
    handler: StageCallable
    critical: bool = True
    permits_broker_action: bool = False


@dataclass(frozen=True)
class StageResult:
    name: str
    ok: bool
    critical: bool
    output: Mapping[str, Any] = field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "critical": self.critical,
            "output": _mutable_copy(self.output),
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class CycleResult:
    cycle_id: str
    status: str
    stages: tuple[StageResult, ...]
    final_context: Mapping[str, Any]
    failed_stage: str | None = None
    is_order_action: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "status": self.status,
            "failed_stage": self.failed_stage,
            "stages": [stage.to_payload() for stage in self.stages],
            "final_context": _mutable_copy(self.final_context),
            "is_order_action": False,
        }


class ShadowStagePipeline:
    def __init__(self, stages: Sequence[PipelineStage]):
        self._stages = tuple(stages)
        names = [stage.name for stage in self._stages]
        if len(names) != len(set(names)):
            raise ValueError("duplicate_pipeline_stage_name")
        broker_stages = [stage.name for stage in self._stages if stage.permits_broker_action]
        if len(broker_stages) > 1:
            raise ValueError("multiple_broker_action_stages")

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(stage.name for stage in self._stages)

    def run(self, cycle_id: str, initial_context: Mapping[str, Any]) -> CycleResult:
        context: dict[str, Any] = _mutable_copy(initial_context)
        frozen_input = _deep_freeze(initial_context)
        context["cycle_id"] = str(cycle_id)
        context["immutable_cycle_input"] = frozen_input
        results: list[StageResult] = []
        failed_stage: str | None = None
        critical_failure = False

        for stage in self._stages:
            stage_input = _deep_freeze(context)
            try:
                output = stage.handler(stage_input)
                output_mapping = dict(output or {})
                if bool(output_mapping.get("is_order_action")) and not stage.permits_broker_action:
                    raise RuntimeError(f"unauthorized_order_action:{stage.name}")
                context.update(_mutable_copy(output_mapping))
                results.append(
                    StageResult(
                        name=stage.name,
                        ok=True,
                        critical=stage.critical,
                        output=_deep_freeze(output_mapping),
                    )
                )
            except Exception as exc:
                failed_stage = failed_stage or stage.name
                results.append(
                    StageResult(
                        name=stage.name,
                        ok=False,
                        critical=stage.critical,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )
                if stage.critical:
                    critical_failure = True
                    break

        status = "BLOCKED" if critical_failure else ("DEGRADED" if failed_stage else "PASS")
        return CycleResult(
            cycle_id=str(cycle_id),
            status=status,
            stages=tuple(results),
            final_context=_deep_freeze(context),
            failed_stage=failed_stage,
        )


__all__ = [
    "CycleResult",
    "PipelineStage",
    "ShadowStagePipeline",
    "StageResult",
]
