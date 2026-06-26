from enum import Enum
from dataclasses import dataclass
from typing import Any

class CalibrationStatus(Enum):
    CALIBRATED = "CALIBRATED"
    UNCALIBRATED = "UNCALIBRATED"
    INVALIDATED = "INVALIDATED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

class FactorOrigin(Enum):
    MEASURED = "MEASURED"
    CONFIGURED = "CONFIGURED"
    INFERRED = "INFERRED"
    CALIBRATED = "CALIBRATED"

ALLOWED_FACTOR_NAMES = {
    "source_authority", "freshness_delta_seconds", "extraction_completeness",
    "explicit_entity_mentions", "entity_resolver_confidence", "duplicate_status",
    "document_category", "source_health", "historical_replay_impact",
    "market_session_context", "replay_sample_size"
}

@dataclass(frozen=True)
class Factor:
    """
    WHY IT EXISTS: To strictly bound, type-check, and trace intelligence data points preventing hallucinated heuristics.
    WHEN TO USE IT: Used to wrap physical or parsed intelligence signals before context injection.
    LIMITATIONS: Cannot sum 'confidence'. Only represents single-dimensional bounds.
    CALIBRATION STATUS: Explicitly governed by `calibration_status` field.
    EXECUTION INFLUENCE: Structurally disabled unless proven by Offline Replay. Overridden if `stale_status=True`.
    
    ARCHITECTURAL ROLE: The base atomic unit of Market Intelligence context.
    DEPENDENCIES: `core.intelligence.config`
    EXTENSION POINTS: None. Banned from extension.
    """
    name: str
    value: Any
    unit: str
    origin: FactorOrigin
    evidence_pointer: str
    reason: str
    measurement_method: str
    calibration_status: CalibrationStatus
    stale_status: bool
    execution_influence_allowed: bool
    ranking_influence_allowed: bool

    def __post_init__(self):
        # Validate allowed name
        if self.name not in ALLOWED_FACTOR_NAMES:
            raise ValueError(f"Factor name {self.name} is not in ALLOWED_FACTOR_NAMES")

        # Enforce Anti-Heuristic Rule:
        if self.calibration_status != CalibrationStatus.CALIBRATED:
            # Bypass frozen nature safely
            object.__setattr__(self, 'execution_influence_allowed', False)
            object.__setattr__(self, 'ranking_influence_allowed', False)

        if self.stale_status:
            object.__setattr__(self, 'execution_influence_allowed', False)
            object.__setattr__(self, 'ranking_influence_allowed', False)

def build_uncalibrated_factor(name: str, value: Any, unit: str, reason: str, evidence: str) -> Factor:
    return Factor(
        name=name,
        value=value,
        unit=unit,
        origin=FactorOrigin.INFERRED,
        evidence_pointer=evidence,
        reason=reason,
        measurement_method="inferred_uncalibrated",
        calibration_status=CalibrationStatus.UNCALIBRATED,
        stale_status=False,
        execution_influence_allowed=False,
        ranking_influence_allowed=False
    )
