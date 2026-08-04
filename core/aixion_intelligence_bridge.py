from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class BridgeStatus:
    enabled: bool
    attempted: int
    persisted: int
    duplicates: int
    failed: int
    reason: str


_LOCK = threading.Lock()
_PUBLISHERS: dict[tuple[str, str], Any] = {}
_SEQUENCE: dict[tuple[str, str], int] = {}


def _truthy(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in {"1", "true", "yes", "on"}


def _enabled() -> bool:
    """Direct publishing is explicit and mutually exclusive with file tailing."""
    return _truthy("AIXION_INTELLIGENCE_ENABLED") and _truthy(
        "AIXION_INTELLIGENCE_DIRECT_BRIDGE_ENABLED"
    )


def _mode() -> str:
    return os.getenv("EXECUTION_MODE", "").strip().upper()


def _identity() -> tuple[str, str]:
    session_id = os.getenv("AIXION_INTELLIGENCE_SESSION_ID", "").strip()
    run_id = os.getenv("AIXION_INTELLIGENCE_RUN_ID", "").strip()
    if not session_id or not run_id:
        raise ValueError("missing_aixion_session_or_run_identity")
    return session_id, run_id


def _publisher(session_id: str, run_id: str):
    key = (session_id, run_id)
    with _LOCK:
        publisher = _PUBLISHERS.get(key)
        if publisher is not None:
            return publisher
        from aixion_trade_intelligence.publisher import FileEventPublisher
        from aixion_trade_intelligence.safe_publish import NonBlockingPublisher

        root = Path(
            os.getenv(
                "AIXION_INTELLIGENCE_EVIDENCE_ROOT",
                "runtime/aixion_trade_intelligence/evidence",
            )
        ).expanduser()
        publisher = NonBlockingPublisher(FileEventPublisher(root, fsync=True))
        _PUBLISHERS[key] = publisher
        _SEQUENCE.setdefault(key, 0)
        return publisher


def _next_sequence(key: tuple[str, str]) -> int:
    with _LOCK:
        value = _SEQUENCE.get(key, 0) + 1
        _SEQUENCE[key] = value
        return value


def publish_candidate_lineage_rows(rows: Iterable[Mapping[str, Any]]) -> BridgeStatus:
    materialized = [dict(row) for row in rows if isinstance(row, Mapping)]
    if not _enabled():
        return BridgeStatus(False, 0, 0, 0, 0, "DISABLED")
    mode = _mode()
    if mode not in {"PAPER", "SHADOW"}:
        return BridgeStatus(False, 0, 0, 0, 0, f"MODE_NOT_ALLOWED:{mode or 'UNKNOWN'}")
    try:
        session_id, run_id = _identity()
        key = (session_id, run_id)
        publisher = _publisher(session_id, run_id)
        from aixion_trade_intelligence.tradebot_adapter import candidate_lineage_to_event

        attempted = persisted = duplicates = failed = 0
        for row in materialized:
            attempted += 1
            now = datetime.now(tz=timezone.utc)
            try:
                event = candidate_lineage_to_event(
                    row,
                    session_id=session_id,
                    run_id=run_id,
                    receive_time=now,
                    persist_time=now,
                    producer_sequence=_next_sequence(key),
                )
                if publisher.publish(event):
                    persisted += 1
                else:
                    duplicates += 1
            except Exception:
                failed += 1
        return BridgeStatus(True, attempted, persisted, duplicates, failed, "PUBLISHED")
    except Exception as exc:
        return BridgeStatus(True, len(materialized), 0, 0, len(materialized), f"BRIDGE_FAILURE:{type(exc).__name__}")


def publish_runtime_truth(
    snapshot: Mapping[str, Any],
    *,
    event_type: str,
    source_component: str,
    event_time: datetime | None = None,
) -> BridgeStatus:
    if not _enabled():
        return BridgeStatus(False, 0, 0, 0, 0, "DISABLED")
    mode = _mode()
    if mode not in {"PAPER", "SHADOW"}:
        return BridgeStatus(False, 0, 0, 0, 0, f"MODE_NOT_ALLOWED:{mode or 'UNKNOWN'}")
    try:
        session_id, run_id = _identity()
        key = (session_id, run_id)
        publisher = _publisher(session_id, run_id)
        from aixion_trade_intelligence.tradebot_adapter import truth_snapshot_to_event

        now = datetime.now(tz=timezone.utc)
        occurred = event_time or now
        event = truth_snapshot_to_event(
            snapshot,
            event_type=event_type,
            session_id=session_id,
            run_id=run_id,
            source_component=source_component,
            event_time=occurred,
            receive_time=now,
            persist_time=now,
            producer_sequence=_next_sequence(key),
        )
        if publisher.publish(event):
            return BridgeStatus(True, 1, 1, 0, 0, "PUBLISHED")
        return BridgeStatus(True, 1, 0, 1, 0, "DUPLICATE")
    except Exception as exc:
        return BridgeStatus(True, 1, 0, 0, 1, f"BRIDGE_FAILURE:{type(exc).__name__}")
