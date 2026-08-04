from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol

from .contracts import CanonicalEvent


class PublisherLike(Protocol):
    def publish(self, event: CanonicalEvent) -> bool: ...


@dataclass(frozen=True)
class PublisherStats:
    attempted: int
    persisted: int
    duplicates: int
    failures: int
    last_error: str


class NonBlockingPublisher:
    """Failure-isolating wrapper for future read-only runtime adapters.

    The wrapper never raises publisher failures into TradeBot. It records the
    failure so the resulting session can be marked incomplete or invalid after
    the run. This class does not create threads or queues and therefore cannot
    reorder events; future async transport must preserve the same contract.
    """

    def __init__(self, publisher: PublisherLike) -> None:
        self._publisher = publisher
        self._lock = threading.Lock()
        self._attempted = 0
        self._persisted = 0
        self._duplicates = 0
        self._failures = 0
        self._last_error = ""

    def publish(self, event: CanonicalEvent) -> bool:
        with self._lock:
            self._attempted += 1
        try:
            persisted = bool(self._publisher.publish(event))
        except Exception as exc:  # fail isolation is the purpose of this boundary
            with self._lock:
                self._failures += 1
                self._last_error = f"{type(exc).__name__}:{exc}"
            return False
        with self._lock:
            if persisted:
                self._persisted += 1
            else:
                self._duplicates += 1
        return persisted

    def stats(self) -> PublisherStats:
        with self._lock:
            return PublisherStats(
                attempted=self._attempted,
                persisted=self._persisted,
                duplicates=self._duplicates,
                failures=self._failures,
                last_error=self._last_error,
            )

    @property
    def evidence_complete(self) -> bool:
        stats = self.stats()
        return stats.failures == 0 and stats.attempted == stats.persisted + stats.duplicates
