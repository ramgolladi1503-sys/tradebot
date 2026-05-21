from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_ACTION_FLAG_KEY = "is_" + "order_action"


@dataclass(slots=True)
class FastExecutionDecision:
    action: str
    reason: str = ""
    candidate: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _record_fast_execution_boundary(
    event: str,
    *,
    details: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    try:
        from core.runtime_startup_lifecycle import record_runtime_startup_event

        payload = {_ACTION_FLAG_KEY: False}
        payload.update(dict(details or {}))
        record_runtime_startup_event(
            event,
            source="core.execution_engine_fast.FastExecutionEngine.execute",
            details=payload,
            error=error,
        )
    except Exception:
        pass


class FastExecutionEngine:
    """
    Minimal execution adapter around the existing orchestrator/runtime.

    This does not attempt to replace the full strategy stack yet. It gives the
    fast loop a dedicated execution layer so decision triggering and execution
    are no longer tightly coupled to the orchestration wrapper.
    """

    def __init__(self, orch: Any):
        self.orch = orch

    def evaluate(self) -> FastExecutionDecision:
        # Phase 1: keep behavior parity by delegating one legacy decision cycle.
        return FastExecutionDecision(action="RUN_LEGACY_CYCLE", reason="feed_or_timer_trigger")

    def execute(self, decision: FastExecutionDecision) -> Any:
        action = str(getattr(decision, "action", "") or "").strip().upper()
        if action == "RUN_LEGACY_CYCLE":
            _record_fast_execution_boundary(
                "FAST_ENGINE_LEGACY_CYCLE_STARTED",
                details={"run_once": True},
            )
            try:
                result = self.orch._legacy_live_monitoring(run_once=True)
            except Exception as exc:
                _record_fast_execution_boundary(
                    "FAST_ENGINE_LEGACY_CYCLE_FAILED",
                    details={"run_once": True},
                    error=f"{type(exc).__name__}:{exc}",
                )
                raise
            _record_fast_execution_boundary(
                "FAST_ENGINE_LEGACY_CYCLE_COMPLETED",
                details={"result": str(result)},
            )
            return result
        if action in {"NOOP", "SKIP"}:
            return None
        raise ValueError(f"unsupported fast execution action: {action}")
