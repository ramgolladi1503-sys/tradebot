from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FastExecutionDecision:
    action: str
    reason: str = ""
    candidate: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


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
            return self.orch._legacy_live_monitoring(run_once=True)
        if action in {"NOOP", "SKIP"}:
            return None
        raise ValueError(f"unsupported fast execution action: {action}")
