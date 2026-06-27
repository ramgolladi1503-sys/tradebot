from dataclasses import dataclass, field
from typing import Dict, Optional
from core.strategy_pipeline.pipeline_models import EngineResult, EngineType, PipelineState, FinalDecision

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
            if not self.blocked_at:
                self.blocked_at = engine
        elif result.state == PipelineState.DEGRADED and self.global_state not in (PipelineState.FAILED, PipelineState.BLOCKED):
            self.global_state = PipelineState.DEGRADED
            
    def get_engine_state(self, engine: EngineType) -> PipelineState:
        result = self.engine_results.get(engine)
        return result.state if result else PipelineState.PENDING
