from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from .contracts import CanonicalEvent, EventValidationError


_STAGE_EVENT_TYPES = {
    "strategy_evaluated": "STRATEGY_EVALUATED",
    "signal_generated": "SIGNAL_GENERATED",
    "candidate_created": "CANDIDATE_CREATED",
    "candidate_blocked": "CANDIDATE_BLOCKED",
    "candidate_ranked": "CANDIDATE_RANKED",
    "approval_requested": "APPROVAL_REQUESTED",
    "approval_decided": "APPROVAL_DECIDED",
    "order_event": "ORDER_EVENT",
    "fill_event": "FILL_EVENT",
    "position_event": "POSITION_EVENT",
    "outcome_label": "OUTCOME_LABEL",
}

_RAW_STAGE_DEFAULT_EVENTS = {
    "generated": "SIGNAL_GENERATED",
    "strategy": "STRATEGY_EVALUATED",
    "strategy_generation": "STRATEGY_EVALUATED",
    "tradebuilder": "CANDIDATE_CREATED",
    "trade_builder": "CANDIDATE_CREATED",
    "phase2": "CANDIDATE_RANKED",
    "phase_2": "CANDIDATE_RANKED",
    "ranking": "CANDIDATE_RANKED",
    "ranked": "CANDIDATE_RANKED",
    "top_opportunity": "CANDIDATE_RANKED",
    "top opportunity": "CANDIDATE_RANKED",
}


def _required_text(row: Mapping[str, Any], name: str) -> str:
    value = str(row.get(name) or "").strip()
    if not value:
        raise EventValidationError(f"adapter_missing_{name}")
    return value


def _timestamp(row: Mapping[str, Any], name: str) -> datetime:
    value = row.get(name)
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw > 1_000_000_000_000:
            raw /= 1000.0
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise EventValidationError(f"adapter_naive_{name}")
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise EventValidationError(f"adapter_invalid_{name}") from exc
        if parsed.tzinfo is None:
            raise EventValidationError(f"adapter_naive_{name}")
        return parsed.astimezone(timezone.utc)
    raise EventValidationError(f"adapter_missing_{name}")


def _event_id(row: Mapping[str, Any], *, session_id: str, event_type: str) -> str:
    explicit = str(row.get("event_id") or "").strip()
    if explicit:
        return explicit
    identity = {
        "session_id": session_id,
        "event_type": event_type,
        "cycle_id": str(row.get("cycle_id") or ""),
        "candidate_id": str(row.get("candidate_id") or ""),
        "stage": str(row.get("stage") or ""),
        "stage_status": str(row.get("stage_status") or ""),
        "timestamp": str(row.get("timestamp") or row.get("event_time") or ""),
        "source_component": str(row.get("source_file_or_component") or row.get("source_component") or ""),
    }
    if not identity["timestamp"]:
        raise EventValidationError("adapter_missing_event_identity_timestamp")
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _resolve_candidate_event_type(row: Mapping[str, Any]) -> str:
    stage = _required_text(row, "stage").lower()
    event_type = _STAGE_EVENT_TYPES.get(stage)
    if event_type is not None:
        return event_type
    event_type = _RAW_STAGE_DEFAULT_EVENTS.get(stage)
    if event_type is None:
        raise EventValidationError(f"adapter_unsupported_stage={stage}")
    status = str(row.get("stage_status") or row.get("status") or "").strip().lower()
    if status == "blocked":
        return "CANDIDATE_BLOCKED"
    if status == "selected" and stage in {"ranking", "ranked", "top_opportunity", "top opportunity"}:
        return "CANDIDATE_RANKED"
    return event_type


def candidate_lineage_to_event(
    row: Mapping[str, Any],
    *,
    session_id: str,
    run_id: str,
    receive_time: datetime,
    persist_time: datetime,
    producer_sequence: int,
) -> CanonicalEvent:
    event_type = _resolve_candidate_event_type(row)
    event_time = _timestamp(row, "timestamp")
    available_value = row.get("available_time") or row.get("timestamp")
    source_value = row.get("source_time") or row.get("timestamp")
    source_component = str(
        row.get("source_file_or_component")
        or row.get("source_component")
        or "core.candidate_lineage_ledger"
    ).strip()
    quality = str(row.get("data_quality_state") or "VALID").strip().upper()
    authority = str(row.get("authority_class") or "TRADEBOT_DERIVED").strip().upper()
    candidate_id = str(row.get("candidate_id") or "").strip()
    if event_type in {
        "CANDIDATE_CREATED",
        "CANDIDATE_BLOCKED",
        "CANDIDATE_RANKED",
        "APPROVAL_REQUESTED",
        "APPROVAL_DECIDED",
        "ORDER_EVENT",
        "FILL_EVENT",
        "POSITION_EVENT",
        "OUTCOME_LABEL",
    } and not candidate_id:
        raise EventValidationError("adapter_missing_candidate_id")
    return CanonicalEvent(
        event_id=_event_id(row, session_id=session_id, event_type=event_type),
        event_type=event_type,
        schema_version="1.0.0",
        session_id=session_id,
        run_id=run_id,
        cycle_id=str(row.get("cycle_id") or ""),
        trace_id=str(row.get("trace_id") or ""),
        event_time=event_time,
        source_time=_timestamp({"source_time": source_value}, "source_time"),
        receive_time=receive_time,
        available_time=_timestamp({"available_time": available_value}, "available_time"),
        parse_time=receive_time,
        persist_time=persist_time,
        source_provider="TRADEBOT",
        source_component=source_component,
        authority_class=authority,
        data_quality_state=quality,
        instrument_key=str(row.get("instrument_id") or row.get("instrument_key") or ""),
        strategy_id=str(row.get("strategy_name") or row.get("strategy_id") or ""),
        strategy_version=str(row.get("strategy_version") or ""),
        candidate_id=candidate_id,
        producer_sequence=producer_sequence,
        payload=dict(row),
    )


def truth_snapshot_to_event(
    snapshot: Mapping[str, Any],
    *,
    event_type: str,
    session_id: str,
    run_id: str,
    source_component: str,
    event_time: datetime,
    receive_time: datetime,
    persist_time: datetime,
    producer_sequence: int,
) -> CanonicalEvent:
    if event_type not in {
        "FEED_TRUTH_UPDATED",
        "RUNTIME_HEALTH_UPDATED",
        "RISK_STATE_CHANGED",
        "INCIDENT_RAISED",
        "SESSION_STARTED",
        "SESSION_ENDED",
    }:
        raise EventValidationError("adapter_unsupported_truth_event_type")
    quality = str(snapshot.get("data_quality_state") or "VALID").strip().upper()
    return CanonicalEvent(
        event_id=_event_id(
            {"timestamp": event_time.isoformat(), "source_component": source_component},
            session_id=session_id,
            event_type=event_type,
        ),
        event_type=event_type,
        schema_version="1.0.0",
        session_id=session_id,
        run_id=run_id,
        event_time=event_time,
        source_time=event_time,
        receive_time=receive_time,
        available_time=event_time,
        parse_time=receive_time,
        persist_time=persist_time,
        source_provider="TRADEBOT",
        source_component=source_component,
        authority_class="TRADEBOT_RUNTIME_TRUTH",
        data_quality_state=quality,
        producer_sequence=producer_sequence,
        payload=dict(snapshot),
    )
