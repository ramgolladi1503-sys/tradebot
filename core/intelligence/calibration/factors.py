from enum import Enum
from dataclasses import dataclass
from typing import Any

class CalibrationStatus(Enum):
    CALIBRATED = "CALIBRATED"
    UNCALIBRATED = "UNCALIBRATED"
    INVALIDATED = "INVALIDATED"

@dataclass(frozen=True)
class Factor:
    """Strictly constrained intelligence factor. No fake edge allowed."""
    name: str # e.g. "source_freshness", "replay-calibrated forward volatility impact"
    value: Any
    unit: str # e.g. "seconds", "points", "boolean"
    origin: str
    evidence_pointer: str
    reason: str
    measurement_method: str
    calibration_status: CalibrationStatus
    execution_influence_allowed: bool
    ranking_influence_allowed: bool

    def __post_init__(self):
        # Enforce Anti-Heuristic Rule:
        if self.calibration_status != CalibrationStatus.CALIBRATED:
            # Bypass frozen nature using object.__setattr__
            object.__setattr__(self, 'execution_influence_allowed', False)
            object.__setattr__(self, 'ranking_influence_allowed', False)

def build_uncalibrated_factor(name: str, value: Any, unit: str, reason: str, evidence: str) -> Factor:
    """Helper to safely construct uncalibrated factors that cannot influence execution."""
    return Factor(
        name=name,
        value=value,
        unit=unit,
        origin="IntelligencePipeline",
        evidence_pointer=evidence,
        reason=reason,
        measurement_method="inferred_uncalibrated",
        calibration_status=CalibrationStatus.UNCALIBRATED,
        execution_influence_allowed=False,
        ranking_influence_allowed=False
    )
