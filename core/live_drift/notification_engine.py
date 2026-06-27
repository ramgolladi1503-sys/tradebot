from datetime import datetime
from typing import List
from core.live_drift.drift_models import DriftObservation, NotificationRecord
from core.live_drift.drift_types import ActionRecommendation


class NotificationEngine:
    """Generates recommendations based on observations. NEVER automatically executes."""

    @staticmethod
    def evaluate(strategy_id: str, observations: List[DriftObservation]) -> NotificationRecord:
        highest_severity = 0.0
        reasons = []
        recommendation = ActionRecommendation.NO_ACTION
        
        for obs in observations:
            highest_severity = max(highest_severity, obs.severity_score)
            reasons.append(f"{obs.drift_type.value}: {obs.description}")
            
        if highest_severity >= 0.8:
            recommendation = ActionRecommendation.SUSPEND_RECOMMENDED
        elif highest_severity >= 0.6:
            recommendation = ActionRecommendation.MANUAL_REVIEW
        elif highest_severity >= 0.4:
            recommendation = ActionRecommendation.MONITOR
        elif highest_severity >= 0.2:
            recommendation = ActionRecommendation.COLLECT_MORE_DATA
            
        return NotificationRecord(
            strategy_id=strategy_id,
            timestamp=datetime.utcnow(),
            recommendation=recommendation,
            reasons=reasons
        )
