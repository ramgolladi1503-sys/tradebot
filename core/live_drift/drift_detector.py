from typing import List
from core.live_drift.drift_models import CertifiedBaseline, LiveSnapshot, DriftObservation
from core.live_drift.drift_types import DriftType
from core.live_drift.performance_drift import PerformanceDriftChecker
from core.live_drift.regime_drift import RegimeDriftChecker
from core.live_drift.execution_drift import ExecutionDriftChecker
from core.live_drift.freshness_checker import FreshnessChecker


class DriftDetector:
    """Aggregates drift observations across all checkers."""

    @staticmethod
    def detect(baseline: CertifiedBaseline, snapshot: LiveSnapshot) -> List[DriftObservation]:
        observations = []
        observations.extend(PerformanceDriftChecker.check(baseline, snapshot))
        observations.extend(RegimeDriftChecker.check(baseline, snapshot))
        observations.extend(ExecutionDriftChecker.check(baseline, snapshot))
        observations.extend(FreshnessChecker.check(baseline, snapshot))
        
        if not observations:
            observations.append(DriftObservation(
                drift_type=DriftType.NO_DRIFT,
                severity_score=0.0,
                description="No drift detected."
            ))
            
        return observations
