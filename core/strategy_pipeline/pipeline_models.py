from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List

class PipelineState(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    DEGRADED = "DEGRADED"

class EngineType(Enum):
    RESEARCH = "RESEARCH"
    REGISTRY = "REGISTRY"
    TRUTH = "TRUTH"
    OUTCOMES = "OUTCOMES"
    STATISTICS = "STATISTICS"
    CERTIFICATION = "CERTIFICATION"
    DRIFT = "DRIFT"

@dataclass
class EngineMetrics:
    strategies_loaded: int = 0
    executable_count: int = 0
    rejected_count: int = 0

@dataclass
class EngineResult:
    engine: EngineType
    state: PipelineState
    artifacts_generated: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    cached: bool = False
    created_timestamp: Optional[str] = None
    metrics: EngineMetrics = field(default_factory=EngineMetrics)
    
@dataclass
class FinalDecision:
    strategy_id: str
    certification_status: str
    reason: str
    blockers: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
