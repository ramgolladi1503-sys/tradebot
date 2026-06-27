from core.strategy_pipeline.pipeline_models import EngineType, PipelineState
from core.strategy_pipeline.pipeline_state import PipelineStateTracker

class DependencyResolver:
    """Ensures each engine only runs if its prerequisites have succeeded."""
    
    def __init__(self):
        self.dependencies = {
            EngineType.RESEARCH: [],
            EngineType.REGISTRY: [EngineType.RESEARCH],
            EngineType.TRUTH: [EngineType.REGISTRY],
            EngineType.OUTCOMES: [EngineType.TRUTH],
            EngineType.STATISTICS: [EngineType.OUTCOMES],
            EngineType.CERTIFICATION: [EngineType.STATISTICS, EngineType.TRUTH],
            EngineType.DRIFT: [EngineType.CERTIFICATION]
        }
        
    def can_run(self, engine: EngineType, tracker: PipelineStateTracker) -> bool:
        deps = self.dependencies.get(engine, [])
        for dep in deps:
            if tracker.get_engine_state(dep) != PipelineState.SUCCESS:
                return False
        return True
