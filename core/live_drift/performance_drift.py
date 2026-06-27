from typing import List
from core.live_drift.drift_models import CertifiedBaseline, LiveSnapshot, DriftObservation
from core.live_drift.drift_types import DriftType


class PerformanceDriftChecker:
    """Checks for expectancy and profit factor collapse."""

    @staticmethod
    def check(baseline: CertifiedBaseline, snapshot: LiveSnapshot) -> List[DriftObservation]:
        observations = []
        
        # Expectancy collapse
        # (Using configured threshold simulation, e.g., < 50% of expected)
        if snapshot.observed_expectancy < (baseline.expected_expectancy * 0.5):
            observations.append(DriftObservation(
                drift_type=DriftType.EXPECTANCY_DRIFT,
                severity_score=0.8,
                description=f"Expectancy collapsed from {baseline.expected_expectancy} to {snapshot.observed_expectancy}"
            ))

        # Profit Factor collapse
        if snapshot.observed_profit_factor < (baseline.expected_profit_factor * 0.7):
            observations.append(DriftObservation(
                drift_type=DriftType.PROFIT_FACTOR_DRIFT,
                severity_score=0.7,
                description=f"Profit Factor collapsed from {baseline.expected_profit_factor} to {snapshot.observed_profit_factor}"
            ))
            
        # Drawdown drift
        if snapshot.current_drawdown > baseline.max_drawdown_limit:
            observations.append(DriftObservation(
                drift_type=DriftType.DRAWDOWN_DRIFT,
                severity_score=0.9,
                description=f"Drawdown {snapshot.current_drawdown} exceeded limit {baseline.max_drawdown_limit}"
            ))

        return observations
