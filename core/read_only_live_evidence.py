"""Append-only evidence contracts for the governed Kite read-only observer.

This module is deliberately independent of broker and execution modules.  It
turns already-measured runtime facts into durable authority and Market Event
Graph ledgers without changing strategy, risk, feed, or order behavior.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def semantic_sha256(payload: Mapping[str, Any], *, exclude: Sequence[str] = ()) -> str:
    excluded = set(exclude)
    semantic = {key: value for key, value in payload.items() if key not in excluded}
    return hashlib.sha256(_canonical_json(semantic)).hexdigest()


def append_jsonl_record(path: Path, payload: Mapping[str, Any], *, hash_field: str) -> dict[str, Any]:
    row = dict(payload)
    row[hash_field] = semantic_sha256(row, exclude=(hash_field,))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return row


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def count_jsonl(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for raw in handle if raw.strip())


def _last_jsonl_mapping(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    last: dict[str, Any] | None = None
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            text = raw.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except Exception:
                continue
            if isinstance(value, Mapping):
                last = dict(value)
    return last


def extract_candidate_rows(runtime_outputs: Any) -> list[dict[str, Any]]:
    if not isinstance(runtime_outputs, Mapping):
        return []
    advisory = runtime_outputs.get("advisory_latest")
    if not isinstance(advisory, Mapping):
        return []
    rows = advisory.get("rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _authority_row(candidate: Mapping[str, Any]) -> dict[str, Any]:
    from core.runtime_authority_cutover import apply_runtime_authority

    source = dict(candidate)
    stamped = apply_runtime_authority(source, mode="SIM")
    row = dict(stamped) if isinstance(stamped, Mapping) else source
    row.update(
        {
            "candidate_id": row.get("candidate_id") or row.get("trade_id") or row.get("symbol"),
            "read_only": True,
            "is_order_action": False,
            "broker_write_authority": False,
            "order_authority": False,
            "allowed_for_live_execution": False,
            "allowed_for_paper_execution": False,
        }
    )
    return row


def write_authority_snapshot_bundle(
    candidates: Sequence[Mapping[str, Any]],
    *,
    ledger_path: Path,
    latest_path: Path,
    run_id: str,
    session_date: str,
    interval_identity: str,
    interval_end_epoch: float | None,
    cycle_count: int,
    producer_commit: str = "",
) -> dict[str, Any]:
    top_executable: list[dict[str, Any]] = []
    top_advisory: list[dict[str, Any]] = []
    blocked_debug: list[dict[str, Any]] = []
    for candidate in candidates:
        row = _authority_row(candidate)
        state = str(row.get("authority_state") or "").strip().upper()
        bucket = str(row.get("operator_bucket") or "").strip().upper()
        allowed = row.get("authority_allowed") is True
        if state == "EXECUTABLE" or bucket == "TOP_EXECUTABLE" or allowed:
            top_executable.append(row)
        elif state == "ADVISORY_ONLY" or bucket == "ADVISORY_ONLY":
            top_advisory.append(row)
        else:
            blocked_debug.append(row)

    payload = {
        "schema_version": 1,
        "authority_snapshot": True,
        "snapshot_kind": "KITE_READ_ONLY_INTERVAL_AUTHORITY",
        "run_id": str(run_id),
        "session_date": str(session_date),
        "source_interval_identity": str(interval_identity),
        "source_interval_end_epoch": interval_end_epoch,
        "snapshot_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cycle_count": int(cycle_count),
        "producer_commit": str(producer_commit),
        "top_executable": top_executable,
        "top_advisory": top_advisory,
        "blocked_debug": blocked_debug,
        "candidate_count": len(top_executable) + len(top_advisory) + len(blocked_debug),
        "executable_count": len(top_executable),
        "advisory_only_count": len(top_advisory),
        "blocked_count": len(blocked_debug),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "broker_write_authority": False,
        "order_authority": False,
        "allowed_for_live_execution": False,
        "allowed_for_paper_execution": False,
    }
    stored = append_jsonl_record(ledger_path, payload, hash_field="snapshot_sha256")
    write_json_atomic(latest_path, stored)
    return stored


@dataclass
class MegIntervalScheduler:
    """Bound repeated MEG evaluation to one completed index interval at a time."""

    max_attempts: int = 8
    retry_interval_seconds: float = 0.5
    retryable_reasons: frozenset[str] = frozenset(
        {
            "SNAPSHOT_INCOMPLETE",
            "INDEX_INTERVAL_MISALIGNED",
            "LIVE_BAR_PROVENANCE_UNPROVEN",
            "POST_MODE_CALLBACK_NOT_OBSERVED",
            "INDEX_FULL_PACKET_NOT_OBSERVED",
            "EQUITY_FULL_DEPTH_NOT_OBSERVED",
        }
    )
    attempts: dict[float, int] = field(default_factory=dict)
    last_attempt_monotonic: dict[float, float] = field(default_factory=dict)
    terminal: set[float] = field(default_factory=set)

    def should_attempt(self, interval_end_epoch: float | None, *, now_monotonic: float | None = None) -> bool:
        if interval_end_epoch is None:
            return False
        interval = float(interval_end_epoch)
        if interval in self.terminal:
            return False
        count = int(self.attempts.get(interval, 0))
        if count >= int(self.max_attempts):
            self.terminal.add(interval)
            return False
        now_value = time.monotonic() if now_monotonic is None else float(now_monotonic)
        previous = self.last_attempt_monotonic.get(interval)
        return previous is None or now_value - previous >= float(self.retry_interval_seconds)

    def record(
        self,
        interval_end_epoch: float,
        *,
        reason: str,
        exported: bool,
        now_monotonic: float | None = None,
    ) -> None:
        interval = float(interval_end_epoch)
        self.attempts[interval] = int(self.attempts.get(interval, 0)) + 1
        self.last_attempt_monotonic[interval] = time.monotonic() if now_monotonic is None else float(now_monotonic)
        normalized = str(reason or "").strip().upper()
        if exported or normalized == "DUPLICATE_INTERVAL":
            self.terminal.add(interval)
        elif normalized not in self.retryable_reasons:
            self.terminal.add(interval)
        elif self.attempts[interval] >= int(self.max_attempts):
            self.terminal.add(interval)


def latest_completed_index_interval(bridge: Any, *, cycle_cutoff: datetime) -> float | None:
    try:
        contract, _ = bridge._load_universe_contract()
        if contract is None:
            return None
        bar = bridge._completed_bar_for(contract.index_symbol, cycle_cutoff=cycle_cutoff)
        if not isinstance(bar, Mapping):
            return None
        for field in ("source_bar_end_epoch", "bar_end_epoch", "end_epoch", "ts_epoch"):
            value = bar.get(field)
            if value is not None:
                return float(value)
        ts = bar.get("ts")
        if isinstance(ts, datetime):
            return float((ts + __import__("datetime").timedelta(minutes=1)).timestamp())
    except Exception:
        return None
    return None


def persist_meg_cycle(
    *,
    bridge: Any,
    result: Any,
    summary_path: Path,
    traversal_path: Path,
    export_ledger_path: Path,
    cycle_count: int,
    session_date: str,
    run_id: str,
    interval_end_epoch: float | None,
    producer_commit: str = "",
) -> dict[str, Any]:
    contract, _ = bridge._load_universe_contract()
    audit = dict(getattr(result, "audit", {}) or {})
    subscription = dict(audit.get("subscription_evidence") or {})
    reason = str(getattr(result, "reason", ""))
    exported = bool(getattr(result, "exported", False))
    accepted = int(getattr(result, "accepted_constituent_count", 0) or 0)
    interval_identity = (
        f"{session_date}:{int(float(interval_end_epoch))}"
        if interval_end_epoch is not None
        else f"{session_date}:unresolved:{int(cycle_count)}"
    )
    traversal_payload = {
        "schema_version": 1,
        "proof_kind": "PR763_LIVE_ACCEPTANCE",
        "evidence_kind": "MEG_TRAVERSAL_EVENT",
        "run_id": str(run_id),
        "session_date": str(session_date),
        "event_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_interval_identity": interval_identity,
        "source_interval_end_epoch": interval_end_epoch,
        "cycle_count": int(cycle_count),
        "attempted": bool(getattr(result, "attempted", False)),
        "exported": exported,
        "rejected": not exported,
        "duplicate": reason.upper() == "DUPLICATE_INTERVAL",
        "reason_code": reason,
        "accepted_constituent_count": accepted,
        "market_event_graph_traversal": exported,
        "market_event_graph_traversal_count": 1 if exported else 0,
        "universe_hash": getattr(contract, "canonical_sha256", "") if contract is not None else "",
        "feed_session_id": subscription.get("feed_session_id"),
        "reconnect_generation": subscription.get("reconnect_generation"),
        "subscription_evidence": subscription,
        "producer_commit": str(producer_commit),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "broker_write_authority": False,
        "order_authority": False,
        "allowed_for_live_execution": False,
        "allowed_for_paper_execution": False,
    }
    traversal_row = append_jsonl_record(
        traversal_path,
        traversal_payload,
        hash_field="event_sha256",
    )

    export_row: dict[str, Any] | None = None
    if exported:
        source_path = Path(str(getattr(getattr(bridge, "exporter", None), "path", "")))
        source_row = _last_jsonl_mapping(source_path) or {}
        export_payload = {
            "schema_version": 1,
            "proof_kind": "PR763_LIVE_ACCEPTANCE",
            "evidence_kind": "MEG_LIVE_SOURCE_EXPORT",
            "run_id": str(run_id),
            "session_date": str(session_date),
            "export_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "source_interval_identity": interval_identity,
            "source_interval_end_epoch": interval_end_epoch,
            "accepted_constituent_count": accepted,
            "constituent_detail_count": len(source_row.get("constituent_bar_details") or []),
            "source": "kite",
            "live_source": True,
            "market_event_graph_traversal": True,
            "market_event_graph_traversal_count": 1,
            "input_provenance": {
                "feed_session_id": subscription.get("feed_session_id"),
                "reconnect_generation": subscription.get("reconnect_generation"),
                "universe_hash": getattr(contract, "canonical_sha256", "") if contract is not None else "",
                "captured_metadata_path": str(source_path),
                "captured_metadata_row_sha256": semantic_sha256(source_row) if source_row else "",
            },
            "producer_commit": str(producer_commit),
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "broker_write_authority": False,
            "order_authority": False,
            "allowed_for_live_execution": False,
            "allowed_for_paper_execution": False,
        }
        export_row = append_jsonl_record(
            export_ledger_path,
            export_payload,
            hash_field="row_sha256",
        )

    summary = {
        **traversal_row,
        "attempted_cycle_count": count_jsonl(traversal_path),
        "exported_cycle_count": count_jsonl(export_ledger_path),
        "rejected_cycle_count": sum(
            1
            for raw in traversal_path.read_text(encoding="utf-8").splitlines()
            if raw.strip() and not bool(json.loads(raw).get("exported"))
        ),
        "last_reason": reason,
        "latest_cycle_exported": exported,
        "cumulative_session_export_count": count_jsonl(export_ledger_path),
        "latest_export": export_row,
    }
    write_json_atomic(summary_path, summary)
    return summary


__all__ = [
    "MegIntervalScheduler",
    "append_jsonl_record",
    "count_jsonl",
    "extract_candidate_rows",
    "latest_completed_index_interval",
    "persist_meg_cycle",
    "semantic_sha256",
    "write_authority_snapshot_bundle",
    "write_json_atomic",
]
