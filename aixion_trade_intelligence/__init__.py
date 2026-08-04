"""Read-only TradeBot evidence and analytics sidecar."""

from .contracts import CanonicalEvent, EventValidationError
from .publisher import FileEventPublisher, NoOpEventPublisher
from .session import SessionAnalyzer

__all__ = [
    "CanonicalEvent",
    "EventValidationError",
    "FileEventPublisher",
    "NoOpEventPublisher",
    "SessionAnalyzer",
]
