from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional

from core.strategy_pipeline.pipeline_models import (
    EngineResult,
    EngineType,
    FinalDecision,
    PipelineState,
)


@dataclass
class PipelineStateTracker:
    strategy_id: str
    global_state: PipelineState = PipelineState.PENDING
    engine_results: Dict[EngineType, EngineResult] = field(default_factory=dict)
    final_decision: Optional[FinalDecision] = None
    blocked_at: Optional[EngineType] = None

    def update_engine_result(self, engine: EngineType, result: EngineResult) -> None:
        self.engine_results[engine] = result
        if result.state == PipelineState.FAILED:
            self.global_state = PipelineState.FAILED
        elif result.state == PipelineState.BLOCKED:
            self.global_state = PipelineState.BLOCKED
            if self.blocked_at is None:
                self.blocked_at = engine
        elif (
            result.state == PipelineState.DEGRADED
            and self.global_state not in (PipelineState.FAILED, PipelineState.BLOCKED)
        ):
            self.global_state = PipelineState.DEGRADED

    def finalize(self, required_engines: Iterable[EngineType]) -> None:
        if self.global_state in (PipelineState.FAILED, PipelineState.BLOCKED):
            return
        states = [self.get_engine_state(engine) for engine in required_engines]
        if any(state == PipelineState.DEGRADED for state in states):
            self.global_state = PipelineState.DEGRADED
        elif states and all(state == PipelineState.SUCCESS for state in states):
            self.global_state = PipelineState.SUCCESS
        else:
            self.global_state = PipelineState.BLOCKED

    def get_engine_state(self, engine: EngineType) -> PipelineState:
        result = self.engine_results.get(engine)
        return result.state if result else PipelineState.PENDING
