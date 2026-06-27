from dataclasses import dataclass, field
from typing import List, Dict
from datetime import datetime

from core.strategy_certification.certification_types import CertificationState, GateStatus

@dataclass(frozen=True)
class GateResult:
    status: GateStatus
    reason: str
    blockers: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class StrategyCertificationReport:
    strategy_id: str
    strategy_version: str
    timestamp: datetime
    initial_state: CertificationState
    final_state: CertificationState
    gate_results: Dict[str, GateResult]
    aggregated_blockers: List[str]
    aggregated_limitations: List[str]
