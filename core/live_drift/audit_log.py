from typing import List, Optional
from core.live_drift.drift_models import AuditLogEntry


class AuditLog:
    """Append-only history log of drift checks and lifecycle events."""

    def __init__(self):
        self._entries: List[AuditLogEntry] = []

    def append(self, entry: AuditLogEntry) -> None:
        self._entries.append(entry)

    def get_entries(self, strategy_id: Optional[str] = None) -> List[AuditLogEntry]:
        if strategy_id:
            return [e for e in self._entries if e.strategy_id == strategy_id]
        return self._entries.copy()
