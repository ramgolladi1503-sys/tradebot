from typing import List
from core.live_drift.drift_models import CertifiedBaseline, LiveSnapshot, DriftObservation
from core.live_drift.drift_types import DriftType


class ExecutionDriftChecker:
    """Checks for execution degradation."""

    @staticmethod
    def check(baseline: CertifiedBaseline, snapshot: LiveSnapshot) -> List[DriftObservation]:
        observations = []
        # Hardcoded configuration rule: slippage > 2.0x is execution drift
        if snapshot.slippage_ratio > 2.0:
            observations.append(DriftObservation(
                drift_type=DriftType.EXECUTION_DRIFT,
                severity_score=0.5,
                description=f"High slippage ratio detected: {snapshot.slippage_ratio}"
            ))
        return observations
