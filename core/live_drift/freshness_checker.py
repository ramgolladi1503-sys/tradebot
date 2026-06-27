from typing import List
from core.live_drift.drift_models import CertifiedBaseline, LiveSnapshot, DriftObservation
from core.live_drift.drift_types import DriftType


class FreshnessChecker:
    """Checks for stale or missing evidence."""

    @staticmethod
    def check(baseline: CertifiedBaseline, snapshot: LiveSnapshot) -> List[DriftObservation]:
        observations = []
        if snapshot.data_freshness_seconds > 86400:  # Older than 24 hours
            observations.append(DriftObservation(
                drift_type=DriftType.DATA_QUALITY_DRIFT,
                severity_score=0.4,
                description=f"Evidence is stale: {snapshot.data_freshness_seconds} seconds old"
            ))
            
        if snapshot.total_observations < 30:  # Minimum statistical sample
            observations.append(DriftObservation(
                drift_type=DriftType.INSUFFICIENT_DATA,
                severity_score=0.2,
                description=f"Insufficient live observations: {snapshot.total_observations}"
            ))
        return observations
