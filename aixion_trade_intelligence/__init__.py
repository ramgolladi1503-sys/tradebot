"""Read-only TradeBot evidence and analytics sidecar."""

from .contracts import CanonicalEvent, EventValidationError
from .evidence_search import EvidenceDocument, EvidenceIndex
from .outcomes import MarketObservation, OutcomeContract, build_causal_outcomes
from .publisher import FileEventPublisher, NoOpEventPublisher
from .session import SessionAnalyzer
from .tradebot_adapter import candidate_lineage_to_event, truth_snapshot_to_event

__all__ = [
    "CanonicalEvent",
    "EventValidationError",
    "EvidenceDocument",
    "EvidenceIndex",
    "FileEventPublisher",
    "MarketObservation",
    "NoOpEventPublisher",
    "OutcomeContract",
    "SessionAnalyzer",
    "build_causal_outcomes",
    "candidate_lineage_to_event",
    "truth_snapshot_to_event",
]
