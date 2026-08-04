"""Read-only TradeBot evidence and analytics sidecar.

The package initializer intentionally exports only the lightweight evidence
kernel. Research, RAG, dashboard, and agent modules must be imported directly so
TradeBot startup never loads them merely by enabling the observer.
"""

from .contracts import CanonicalEvent, EventValidationError
from .outcomes import MarketObservation, OutcomeContract, build_causal_outcomes
from .publisher import FileEventPublisher, NoOpEventPublisher
from .safe_publish import NonBlockingPublisher, PublisherStats
from .session import SessionAnalyzer
from .tradebot_adapter import candidate_lineage_to_event, truth_snapshot_to_event

__all__ = [
    "CanonicalEvent",
    "EventValidationError",
    "FileEventPublisher",
    "MarketObservation",
    "NoOpEventPublisher",
    "NonBlockingPublisher",
    "OutcomeContract",
    "PublisherStats",
    "SessionAnalyzer",
    "build_causal_outcomes",
    "candidate_lineage_to_event",
    "truth_snapshot_to_event",
]
