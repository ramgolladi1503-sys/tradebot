"""Read-only TradeBot evidence and analytics sidecar."""

from .certification import (
    REQUIRED_STRATEGY_GATES,
    CertificationDecision,
    CertificationGateResult,
    GateStatus,
    certify_strategy,
)
from .contracts import CanonicalEvent, EventValidationError
from .evidence_search import EvidenceDocument, EvidenceIndex
from .outcomes import MarketObservation, OutcomeContract, build_causal_outcomes
from .publisher import FileEventPublisher, NoOpEventPublisher
from .readiness import CanaryReadiness, evaluate_canary_readiness
from .safe_publish import NonBlockingPublisher, PublisherStats
from .session import SessionAnalyzer
from .tradebot_adapter import candidate_lineage_to_event, truth_snapshot_to_event

__all__ = [
    "REQUIRED_STRATEGY_GATES",
    "CanonicalEvent",
    "CanaryReadiness",
    "CertificationDecision",
    "CertificationGateResult",
    "EventValidationError",
    "EvidenceDocument",
    "EvidenceIndex",
    "FileEventPublisher",
    "GateStatus",
    "MarketObservation",
    "NoOpEventPublisher",
    "NonBlockingPublisher",
    "OutcomeContract",
    "PublisherStats",
    "SessionAnalyzer",
    "build_causal_outcomes",
    "candidate_lineage_to_event",
    "certify_strategy",
    "evaluate_canary_readiness",
    "truth_snapshot_to_event",
]
