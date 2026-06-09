"""Append-only feed event journal for FEED-STAB-07.

This module is a local, read-only evidence builder around feed events. It
records deterministic feed observations as JSON Lines so later tooling can
audit reconnects, freshness, subscription changes, and quarantine behavior.
It does not call brokers, place orders, mutate runtime state, or wire into
the live supervisor. It only builds, validates, appends to, and reads a
caller-supplied feed journal file.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FEED_EVENT_JOURNAL_SCHEMA_VERSION = 1
FEED_EVENT_JOURNAL_SOURCE = "feed_event_journal_v1"
FEED_MODE = "FEED"

FEED_EVENT_RECONNECT = "FEED_RECONNECT"
FEED_EVENT_RECOVERY = "FEED_RECOVERY"
FEED_EVENT_SUBSCRIPTION = "FEED_SUBSCRIPTION"
FEED_EVENT_TICK = "FEED_TICK"
FEED_EVENT_DEPTH = "FEED_DEPTH"
FEED_EVENT_QUARANTINE = "FEED_QUARANTINE"

FEED_EVENT_TYPES = frozenset(
    {
        FEED_EVENT_RECONNECT,
        FEED_EVENT_RECOVERY,
        FEED_EVENT_SUBSCRIPTION,
        FEED_EVENT_TICK,
        FEED_EVENT_DEPTH,
        FEED_EVENT_QUARANTINE,
    }
)

VALIDATION_OK = "ok"
MISSING_REQUIRED_FIELD = "missing_required_field"
INVALID_EVENT_TYPE = "invalid_event_type"
INVALID_MODE = "invalid_mode"
INVALID_SEQUENCE = "invalid_sequence"
INVALID_JSON_LINE = "invalid_json_line"
SEQUENCE_GAP = "sequence_gap"
PREVIOUS_HASH_MISMATCH = "previous_hash_mismatch"
EVENT_HASH_MISMATCH = "event_hash_mismatch"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class FeedEvent:
    schema_version: int
    source: str
    event_id: str
    event_type: str
    sequence: int
    event_ts_epoch: float
    mode: str
    symbol: str
    feed_state: str
    previous_event_hash: str
    event_hash: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        out = {
            "schema_version": self.schema_version,
            "source": self.source,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "sequence": self.sequence,
            "event_ts_epoch": self.event_ts_epoch,
            "mode": self.mode,
            "symbol": self.symbol,
            "feed_state": self.feed_state,
            "previous_event_hash": self.previous_event_hash,
            "event_hash": self.event_hash,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
            "read_only": True,
            "append": True,
        }
        out[_ORDER_ACTION_KEY] = False
        out[_BROKER_KEY] = False
        return out

    def to_json(self) -> str:
        return _canonical_json(self.to_payload())


@dataclass(frozen=True)
class FeedEventJournalValidation:
    journal_valid: bool
    reason_code: str
    reasons: tuple[str, ...]
    event_count: int
    latest_sequence: int
    latest_event_hash: str
    read_only: bool = True
    append: bool = False
    source: str = FEED_EVENT_JOURNAL_SOURCE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        out = {
            "schema_version": FEED_EVENT_JOURNAL_SCHEMA_VERSION,
            "source": self.source,
            "journal_valid": self.journal_valid,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "event_count": self.event_count,
            "latest_sequence": self.latest_sequence,
            "latest_event_hash": self.latest_event_hash,
            "read_only": self.read_only,
            "append": self.append,
        }
        out[_ORDER_ACTION_KEY] = False
        out[_BROKER_KEY] = False
        return out


def build_feed_event(
    *,
    event_type: str,
    sequence: int,
    symbol: str,
    feed_state: str,
    payload: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    previous_event_hash: str = "",
    event_ts_epoch: float | None = None,
    mode: str = FEED_MODE,
) -> FeedEvent:
    ts = float(time.time() if event_ts_epoch is None else event_ts_epoch)
    base = {
        "schema_version": FEED_EVENT_JOURNAL_SCHEMA_VERSION,
        "source": FEED_EVENT_JOURNAL_SOURCE,
        "event_type": _text(event_type),
        "sequence": int(sequence),
        "event_ts_epoch": ts,
        "mode": _text(mode).upper(),
        "symbol": _text(symbol).upper(),
        "feed_state": _text(feed_state).upper(),
        "previous_event_hash": _text(previous_event_hash),
        "payload": dict(payload or {}),
        "metadata": _metadata(metadata),
    }
    _validate_event_payload(base, require_event_hash=False)
    event_id = _event_id(base)
    event_hash = _hash_payload({**base, "event_id": event_id})
    return FeedEvent(
        schema_version=FEED_EVENT_JOURNAL_SCHEMA_VERSION,
        source=FEED_EVENT_JOURNAL_SOURCE,
        event_id=event_id,
        event_type=str(base["event_type"]),
        sequence=int(base["sequence"]),
        event_ts_epoch=float(base["event_ts_epoch"]),
        mode=str(base["mode"]),
        symbol=str(base["symbol"]),
        feed_state=str(base["feed_state"]),
        previous_event_hash=str(base["previous_event_hash"]),
        event_hash=event_hash,
        payload=dict(base["payload"]),
        metadata=dict(base["metadata"]),
    )


def append_feed_event(
    journal_path: str | Path,
    *,
    event_type: str,
    symbol: str,
    feed_state: str,
    payload: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    event_ts_epoch: float | None = None,
) -> FeedEvent:
    path = Path(journal_path)
    existing = read_feed_events(path)
    validation = validate_feed_events(existing)
    if not validation.journal_valid:
        raise ValueError(f"feed_event_journal_invalid:{validation.reason_code}")
    previous = existing[-1] if existing else None
    sequence = int(previous["sequence"]) + 1 if previous else 1
    previous_hash = str(previous.get("event_hash") or "") if previous else ""
    event = build_feed_event(
        event_type=event_type,
        sequence=sequence,
        symbol=symbol,
        feed_state=feed_state,
        payload=payload,
        metadata=metadata,
        previous_event_hash=previous_hash,
        event_ts_epoch=event_ts_epoch,
    )
    lines = [row for row in existing]
    lines.append(event.to_payload())
    _write_jsonl(path, lines)
    return event


def read_feed_events(journal_path: str | Path) -> tuple[dict[str, Any], ...]:
    path = Path(journal_path)
    if not path.exists():
        return ()
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if isinstance(row, dict):
            rows.append(row)
    return tuple(rows)


def validate_feed_events(events: Iterable[Mapping[str, Any]]) -> FeedEventJournalValidation:
    rows = [dict(event) for event in events]
    if not rows:
        return FeedEventJournalValidation(
            journal_valid=True,
            reason_code=VALIDATION_OK,
            reasons=(),
            event_count=0,
            latest_sequence=0,
            latest_event_hash="",
        )
    reasons: list[str] = []
    previous_hash = ""
    latest_hash = ""
    latest_sequence = 0
    for index, row in enumerate(rows, start=1):
        event_type = _text(row.get("event_type"))
        if event_type not in FEED_EVENT_TYPES:
            reasons.append(INVALID_EVENT_TYPE)
        mode = _text(row.get("mode")).upper()
        if mode != FEED_MODE:
            reasons.append(INVALID_MODE)
        sequence = _as_int(row.get("sequence"))
        if sequence != index:
            reasons.append(SEQUENCE_GAP)
        if index > 1 and _text(row.get("previous_event_hash")) != previous_hash:
            reasons.append(PREVIOUS_HASH_MISMATCH)
        payload = {
            "schema_version": row.get("schema_version"),
            "source": row.get("source"),
            "event_type": event_type,
            "sequence": sequence,
            "event_ts_epoch": row.get("event_ts_epoch"),
            "mode": mode,
            "symbol": _text(row.get("symbol")),
            "feed_state": _text(row.get("feed_state")),
            "previous_event_hash": _text(row.get("previous_event_hash")),
            "payload": dict(row.get("payload") or {}),
            "metadata": _metadata(row.get("metadata")),
        }
        computed = _hash_payload({**payload, "event_id": _event_id(payload)})
        if _text(row.get("event_hash")) != computed:
            reasons.append(EVENT_HASH_MISMATCH)
        previous_hash = computed
        latest_hash = computed
        latest_sequence = sequence
    if reasons:
        return FeedEventJournalValidation(
            journal_valid=False,
            reason_code=reasons[0],
            reasons=_dedupe(reasons),
            event_count=len(rows),
            latest_sequence=latest_sequence,
            latest_event_hash=latest_hash,
        )
    return FeedEventJournalValidation(
        journal_valid=True,
        reason_code=VALIDATION_OK,
        reasons=(),
        event_count=len(rows),
        latest_sequence=latest_sequence,
        latest_event_hash=latest_hash,
    )


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(_canonical_json(row) for row in rows)
    path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _event_id(base: Mapping[str, Any]) -> str:
    return _hash_payload(base)[:16]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _dedupe(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in (str(value).strip() for value in items) if item))


def _validate_event_payload(payload: Mapping[str, Any], *, require_event_hash: bool) -> None:
    if not _text(payload.get("event_type")):
        raise ValueError("feed_event_missing_event_type")
    if not _text(payload.get("symbol")):
        raise ValueError("feed_event_missing_symbol")
    if not _text(payload.get("feed_state")):
        raise ValueError("feed_event_missing_feed_state")
    if _text(payload.get("mode")).upper() != FEED_MODE:
        raise ValueError("feed_event_invalid_mode")


__all__ = [
    "FEED_EVENT_DEPTH",
    "FEED_EVENT_JOURNAL_SCHEMA_VERSION",
    "FEED_EVENT_JOURNAL_SOURCE",
    "FEED_EVENT_QUARANTINE",
    "FEED_EVENT_RECONNECT",
    "FEED_EVENT_RECOVERY",
    "FEED_EVENT_SUBSCRIPTION",
    "FEED_EVENT_TICK",
    "FeedEvent",
    "FeedEventJournalValidation",
    "append_feed_event",
    "build_feed_event",
    "read_feed_events",
    "validate_feed_events",
]
