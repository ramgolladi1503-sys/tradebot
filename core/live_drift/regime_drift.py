from typing import List
from core.live_drift.drift_models import CertifiedBaseline, LiveSnapshot, DriftObservation
from core.live_drift.drift_types import DriftType


class RegimeDriftChecker:
    """Checks for regime mismatch between baseline and live."""

    @staticmethod
    def check(baseline: CertifiedBaseline, snapshot: LiveSnapshot) -> List[DriftObservation]:
        observations = []
        if baseline.regime_signature != snapshot.current_regime_signature:
            observations.append(DriftObservation(
                drift_type=DriftType.REGIME_DRIFT,
                severity_score=0.6,
                description=f"Regime mismatch: expected {baseline.regime_signature}, got {snapshot.current_regime_signature}"
            ))
        return observations
