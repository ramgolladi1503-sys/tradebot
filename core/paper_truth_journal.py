"""Canonical paper-truth journal foundation for EDGE-83.

The journal is a local, paper-mode-only evidence log. It records deterministic
paper events as JSON Lines so later reducers can derive state from the journal.
This module does not call brokers, place live trades, score candidates, rank
candidates, or wire runtime behavior. It only builds, validates, appends to,
and reads a caller-supplied paper journal file.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from core.log_writer import get_jsonl_writer

PAPER_TRUTH_JOURNAL_SCHEMA_VERSION = 1
PAPER_TRUTH_JOURNAL_SOURCE = "paper_truth_journal_v1"
PAPER_MODE = "PAPER"

PAPER_EVENT_CANDIDATE_ACCEPTED = "PAPER_CANDIDATE_ACCEPTED"
PAPER_EVENT_ENTRY_RECORDED = "PAPER_ENTRY_RECORDED"
PAPER_EVENT_EXIT_RECORDED = "PAPER_EXIT_RECORDED"
PAPER_EVENT_REJECTED = "PAPER_REJECTED"
PAPER_EVENT_NOTE_RECORDED = "PAPER_NOTE_RECORDED"

PAPER_EVENT_TYPES = frozenset(
    {
        PAPER_EVENT_CANDIDATE_ACCEPTED,
        PAPER_EVENT_ENTRY_RECORDED,
        PAPER_EVENT_EXIT_RECORDED,
        PAPER_EVENT_REJECTED,
        PAPER_EVENT_NOTE_RECORDED,
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

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class PaperTruthEvent:
    """One immutable paper-truth journal event."""

    schema_version: int
    source: str
    event_id: str
    event_type: str
    sequence: int
    event_ts_epoch: float
    mode: str
    candidate_id: str
    strategy_id: str
    symbol: str
    side: str
    quantity: float | None
    price: float | None
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

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
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
            "candidate_id": self.candidate_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "previous_event_hash": self.previous_event_hash,
            "event_hash": self.event_hash,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
            "read_only": True,
            "append": True,
        }
        _mark_non_action(out)
        return out

    def to_json(self) -> str:
        return _canonical_json(self.to_payload())


@dataclass(frozen=True)
class PaperTruthJournalValidation:
    """Validation result for a paper-truth journal file or event stream."""

    journal_valid: bool
    reason_code: str
    reasons: tuple[str, ...]
    event_count: int
    latest_sequence: int
    latest_event_hash: str
    read_only: bool = True
    append: bool = False
    source: str = PAPER_TRUTH_JOURNAL_SOURCE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        out = {
            "schema_version": PAPER_TRUTH_JOURNAL_SCHEMA_VERSION,
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
        _mark_non_action(out)
        return out


def build_paper_truth_event(
    *,
    event_type: str,
    sequence: int,
    candidate_id: str,
    strategy_id: str,
    symbol: str,
    side: str,
    quantity: float | int | str | None = None,
    price: float | int | str | None = None,
    payload: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    previous_event_hash: str = "",
    event_ts_epoch: float | None = None,
    mode: str = PAPER_MODE,
) -> PaperTruthEvent:
    """Build a deterministic paper-truth event and compute its hash."""

    ts = float(time.time() if event_ts_epoch is None else event_ts_epoch)
    base = {
        "schema_version": PAPER_TRUTH_JOURNAL_SCHEMA_VERSION,
        "source": PAPER_TRUTH_JOURNAL_SOURCE,
        "event_type": _text(event_type),
        "sequence": int(sequence),
        "event_ts_epoch": ts,
        "mode": _text(mode).upper(),
        "candidate_id": _text(candidate_id),
        "strategy_id": _text(strategy_id),
        "symbol": _text(symbol).upper(),
        "side": _text(side).upper(),
        "quantity": _optional_float(quantity),
        "price": _optional_float(price),
        "previous_event_hash": _text(previous_event_hash),
        "payload": dict(payload or {}),
        "metadata": _metadata(metadata),
    }
    _validate_event_payload(base, require_event_hash=False)
    event_id = _event_id(base)
    hash_input = dict(base)
    hash_input["event_id"] = event_id
    event_hash = _hash_payload(hash_input)
    return PaperTruthEvent(
        schema_version=PAPER_TRUTH_JOURNAL_SCHEMA_VERSION,
        source=PAPER_TRUTH_JOURNAL_SOURCE,
        event_id=event_id,
        event_type=str(base["event_type"]),
        sequence=int(base["sequence"]),
        event_ts_epoch=float(base["event_ts_epoch"]),
        mode=str(base["mode"]),
        candidate_id=str(base["candidate_id"]),
        strategy_id=str(base["strategy_id"]),
        symbol=str(base["symbol"]),
        side=str(base["side"]),
        quantity=base["quantity"],
        price=base["price"],
        previous_event_hash=str(base["previous_event_hash"]),
        event_hash=event_hash,
        payload=dict(base["payload"]),
        metadata=dict(base["metadata"]),
    )


def append_paper_truth_event(
    journal_path: str | Path,
    *,
    event_type: str,
    candidate_id: str,
    strategy_id: str,
    symbol: str,
    side: str,
    quantity: float | int | str | None = None,
    price: float | int | str | None = None,
    payload: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    event_ts_epoch: float | None = None,
) -> PaperTruthEvent:
    """Append one validated paper event to a caller-supplied JSONL journal."""

    path = Path(journal_path)
    existing = read_paper_truth_events(path)
    validation = validate_paper_truth_events(existing)
    if not validation.journal_valid:
        raise ValueError(f"paper_truth_journal_invalid:{validation.reason_code}")
    previous = existing[-1] if existing else None
    sequence = int(previous["sequence"]) + 1 if previous else 1
    previous_hash = str(previous.get("event_hash") or "") if previous else ""
    event = build_paper_truth_event(
        event_type=event_type,
        sequence=sequence,
        candidate_id=candidate_id,
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        payload=payload,
        metadata=metadata,
        previous_event_hash=previous_hash,
        event_ts_epoch=event_ts_epoch,
        mode=PAPER_MODE,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if not get_jsonl_writer(path).write(json.loads(event.to_json())):
        raise OSError("bounded_paper_truth_write_rejected")
    return event


def read_paper_truth_events(journal_path: str | Path) -> tuple[dict[str, Any], ...]:
    """Read paper-truth journal events from JSON Lines without side effects."""

    path = Path(journal_path)
    if not path.exists():
        return ()
    events: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{INVALID_JSON_LINE}:{line_number}") from exc
        if not isinstance(loaded, Mapping):
            raise ValueError(f"{INVALID_JSON_LINE}:{line_number}")
        events.append(dict(loaded))
    return tuple(events)


def validate_paper_truth_journal(journal_path: str | Path) -> PaperTruthJournalValidation:
    """Validate a paper-truth journal file."""

    return validate_paper_truth_events(read_paper_truth_events(journal_path))


def validate_paper_truth_events(events: Iterable[Mapping[str, Any]]) -> PaperTruthJournalValidation:
    """Validate sequence continuity and hash-chain integrity for events."""

    materialized = tuple(dict(event) for event in events)
    reasons: list[str] = []
    expected_sequence = 1
    previous_hash = ""
    latest_sequence = 0
    latest_hash = ""

    for event in materialized:
        event_reasons = _event_validation_reasons(event)
        reasons.extend(event_reasons)
        sequence = _safe_int(event.get("sequence"), default=-1)
        if sequence != expected_sequence:
            reasons.append(SEQUENCE_GAP)
        if str(event.get("previous_event_hash") or "") != previous_hash:
            reasons.append(PREVIOUS_HASH_MISMATCH)
        expected_hash = _recompute_event_hash(event)
        if str(event.get("event_hash") or "") != expected_hash:
            reasons.append(EVENT_HASH_MISMATCH)
        latest_sequence = sequence if sequence > latest_sequence else latest_sequence
        latest_hash = str(event.get("event_hash") or "")
        previous_hash = latest_hash
        expected_sequence += 1

    clean_reasons = _dedupe(reasons)
    valid = not clean_reasons
    return PaperTruthJournalValidation(
        journal_valid=valid,
        reason_code=VALIDATION_OK if valid else clean_reasons[0],
        reasons=clean_reasons,
        event_count=len(materialized),
        latest_sequence=latest_sequence,
        latest_event_hash=latest_hash,
    )


def _event_validation_reasons(event: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field_name in ("event_type", "sequence", "candidate_id", "strategy_id", "symbol", "side", "mode", "event_hash"):
        if not _text(event.get(field_name)):
            reasons.append(f"{MISSING_REQUIRED_FIELD}:{field_name}")
    event_type = _text(event.get("event_type"))
    if event_type and event_type not in PAPER_EVENT_TYPES:
        reasons.append(INVALID_EVENT_TYPE)
    mode = _text(event.get("mode")).upper()
    if mode and mode != PAPER_MODE:
        reasons.append(INVALID_MODE)
    if _safe_int(event.get("sequence"), default=0) <= 0:
        reasons.append(INVALID_SEQUENCE)
    return reasons


def _validate_event_payload(payload: Mapping[str, Any], *, require_event_hash: bool) -> None:
    event = dict(payload)
    if require_event_hash and not _text(event.get("event_hash")):
        raise ValueError(f"{MISSING_REQUIRED_FIELD}:event_hash")
    reasons = _event_validation_reasons(event)
    hash_reason = f"{MISSING_REQUIRED_FIELD}:event_hash"
    if not require_event_hash:
        reasons = [reason for reason in reasons if reason != hash_reason]
    if reasons:
        raise ValueError(reasons[0])


def _metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    out = dict(value or {})
    out.setdefault("journal", PAPER_TRUTH_JOURNAL_SOURCE)
    out.setdefault("paper_only", True)
    out.setdefault("read_only_replayable", True)
    return out


def _event_id(payload: Mapping[str, Any]) -> str:
    identity = {
        "candidate_id": payload.get("candidate_id"),
        "event_ts_epoch": payload.get("event_ts_epoch"),
        "event_type": payload.get("event_type"),
        "sequence": payload.get("sequence"),
        "source": PAPER_TRUTH_JOURNAL_SOURCE,
        "strategy_id": payload.get("strategy_id"),
        "symbol": payload.get("symbol"),
    }
    return "paper_evt_" + _hash_payload(identity)[:24]


def _recompute_event_hash(event: Mapping[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_hash", None)
    for key in (_ACTION_KEY, _BROKER_KEY, "live_order_action", "broker_order_action", "read_only", "append"):
        payload.pop(key, None)
    return _hash_payload(payload)


def _hash_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_numeric_value") from exc


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value or "").strip()}))


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "EVENT_HASH_MISMATCH",
    "INVALID_EVENT_TYPE",
    "INVALID_JSON_LINE",
    "INVALID_MODE",
    "INVALID_SEQUENCE",
    "MISSING_REQUIRED_FIELD",
    "PAPER_EVENT_CANDIDATE_ACCEPTED",
    "PAPER_EVENT_ENTRY_RECORDED",
    "PAPER_EVENT_EXIT_RECORDED",
    "PAPER_EVENT_NOTE_RECORDED",
    "PAPER_EVENT_REJECTED",
    "PAPER_EVENT_TYPES",
    "PAPER_MODE",
    "PAPER_TRUTH_JOURNAL_SCHEMA_VERSION",
    "PAPER_TRUTH_JOURNAL_SOURCE",
    "PREVIOUS_HASH_MISMATCH",
    "SEQUENCE_GAP",
    "VALIDATION_OK",
    "PaperTruthEvent",
    "PaperTruthJournalValidation",
    "append_paper_truth_event",
    "build_paper_truth_event",
    "read_paper_truth_events",
    "validate_paper_truth_events",
    "validate_paper_truth_journal",
]
