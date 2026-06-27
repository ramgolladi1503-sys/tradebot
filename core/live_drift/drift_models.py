from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict
from core.live_drift.drift_types import DriftType, LifecycleState, ActionRecommendation


@dataclass(frozen=True)
class CertifiedBaseline:
    strategy_id: str
    certification_id: str
    certified_timestamp: datetime
    expected_expectancy: float
    expected_profit_factor: float
    max_drawdown_limit: float
    regime_signature: str


@dataclass(frozen=True)
class LiveSnapshot:
    strategy_id: str
    snapshot_timestamp: datetime
    observed_expectancy: float
    observed_profit_factor: float
    current_drawdown: float
    current_regime_signature: str
    slippage_ratio: float
    total_observations: int
    data_freshness_seconds: int


@dataclass(frozen=True)
class DriftObservation:
    drift_type: DriftType
    severity_score: float  # 0.0 to 1.0
    description: str


@dataclass(frozen=True)
class DriftReport:
    strategy_id: str
    report_timestamp: datetime
    baseline: CertifiedBaseline
    snapshot: LiveSnapshot
    observations: List[DriftObservation]
    primary_drift: DriftType


@dataclass(frozen=True)
class LifecycleTransition:
    strategy_id: str
    timestamp: datetime
    from_state: LifecycleState
    to_state: LifecycleState
    reason: str


@dataclass(frozen=True)
class NotificationRecord:
    strategy_id: str
    timestamp: datetime
    recommendation: ActionRecommendation
    reasons: List[str]


@dataclass(frozen=True)
class AuditLogEntry:
    entry_id: str
    timestamp: datetime
    strategy_id: str
    event_type: str
    details: Dict[str, str]
