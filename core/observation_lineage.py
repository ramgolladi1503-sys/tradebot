"""Read-only lineage envelope joining observed ticks, pulses and outputs."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from core.causal_pulse import NativePulse, derive_pulse_id, sha256_canonical

MAX_SNAPSHOT_TICK_ROWS = 2_000
MAX_TICK_LINEAGE_BYTES = 512 * 1024


def _event_payload_matches(*, token: int, last_price: Any, source_timestamp_epoch: Any,
                           timestamp_source_field: Any, event_id: Any,
                           event_sha: Any, event_payload: Any) -> bool:
    if (not isinstance(event_id, str) or not event_id
            or not isinstance(event_sha, str) or len(event_sha) != 64
            or not isinstance(event_payload, Mapping)):
        return False
    try:
        encoded = json.dumps(event_payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return (
            hashlib.sha256(encoded).hexdigest() == event_sha
            and int(event_payload.get("instrument_token")) == int(token)
            and float(event_payload.get("last_price")) == float(last_price)
            and float(event_payload.get("source_timestamp_epoch")) == float(source_timestamp_epoch)
            and event_payload.get("source_timestamp_field") == timestamp_source_field
            and event_id.endswith(f":{int(token)}:{event_sha[:16]}")
        )
    except (TypeError, ValueError, OverflowError):
        return False


def snapshot_tick_lineage(market_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return bounded exact tick identities present in the consumed snapshot."""
    ticks = market_snapshot.get("ticks")
    if not isinstance(ticks, Mapping):
        return {"status": "MISSING_TICK_SECTION", "ticks": {}}
    found: dict[str, Any] = {}
    row_count = 0
    lineage_bytes = 0
    for group_name in ("index", "options"):
        group = ticks.get(group_name)
        rows = group.items() if isinstance(group, Mapping) and group_name == "options" else [(group_name, group)]
        for token_key, row in rows:
            if not isinstance(row, Mapping):
                continue
            token = row.get("instrument_token", token_key if str(token_key).isdigit() else None)
            if token is None:
                continue
            row_count += 1
            if row_count > MAX_SNAPSHOT_TICK_ROWS:
                return {"status": "LINEAGE_TICK_BOUND_EXCEEDED", "ticks": {}}
            event_id = row.get("source_event_id")
            event_sha = row.get("source_event_sha256")
            event_payload = row.get("source_event_payload")
            valid_event = _event_payload_matches(
                token=int(token), last_price=row.get("last_price"),
                source_timestamp_epoch=row.get("source_timestamp_epoch"),
                timestamp_source_field=row.get("timestamp_source_field"),
                event_id=event_id, event_sha=event_sha, event_payload=event_payload,
            )
            status = "VERIFIED_EVENT_PAYLOAD" if valid_event else "UNKNOWN_EVENT_ID_UNAVAILABLE" if not event_id else "INVALID_EVENT_PAYLOAD_BINDING"
            found[str(int(token))] = {
                "event_identity_status": status,
                "source_event_id": event_id if valid_event else None,
                "source_event_sha256": event_sha if valid_event else None,
                "source_event_payload": dict(event_payload) if valid_event else None,
                "timestamp_epoch": row.get("timestamp_epoch"),
                "last_price": row.get("last_price"),
                "timestamp_authority": row.get("timestamp_authority"),
                "timestamp_source_field": row.get("timestamp_source_field"),
                "source_timestamp_epoch": row.get("source_timestamp_epoch"),
                "receive_timestamp_epoch": row.get("receive_timestamp_epoch"),
                "timestamp_fallback_used": row.get("timestamp_fallback_used"),
            }
            lineage_bytes += len(json.dumps(found[str(int(token))], sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))
            if lineage_bytes > MAX_TICK_LINEAGE_BYTES:
                return {"status": "LINEAGE_TICK_BYTE_BOUND_EXCEEDED", "ticks": {}}
    return {"status": "TICK_IDENTITIES_PRESENT" if found else "NO_TICK_ROWS", "ticks": found}


def current_tick_store_lineage(tokens: list[int] | tuple[int, ...]) -> dict[str, Any]:
    """Read only the current process cache; never flush SQLite from a pulse."""
    from core.tick_store import get_last_tick

    token_rows: dict[str, Any] = {}
    lineage_bytes = 0
    requested_tokens = list(tokens)
    bounded_tokens = requested_tokens[:MAX_SNAPSHOT_TICK_ROWS]
    for raw_token in bounded_tokens:
        try:
            token = int(raw_token)
        except (TypeError, ValueError, OverflowError):
            continue
        row = get_last_tick(token, allow_db=False, include_provenance=True)
        if not isinstance(row, Mapping):
            token_rows[str(token)] = {"status": "NO_PROCESS_LOCAL_TICK"}
            continue
        provenance = dict(row.get("_provenance") or {})
        payload = provenance.get("source_event_payload")
        event_id = provenance.get("source_event_id")
        event_sha = provenance.get("source_event_sha256")
        identity_status = "UNKNOWN_EVENT_ID_UNAVAILABLE"
        if event_id:
            identity_status = "VERIFIED_EVENT_PAYLOAD" if _event_payload_matches(
                token=token, last_price=row.get("ltp"),
                source_timestamp_epoch=provenance.get("source_timestamp_epoch"),
                timestamp_source_field=provenance.get("timestamp_source_field"),
                event_id=event_id, event_sha=event_sha, event_payload=payload,
            ) else "INVALID_EVENT_PAYLOAD_BINDING"
        token_rows[str(token)] = {
            "status": "OBSERVED_PROCESS_LOCAL_TICK",
            "event_identity_status": identity_status,
            "source_event_id": event_id if identity_status == "VERIFIED_EVENT_PAYLOAD" else None,
            "source_event_sha256": event_sha if identity_status == "VERIFIED_EVENT_PAYLOAD" else None,
            "source_event_payload": dict(payload) if identity_status == "VERIFIED_EVENT_PAYLOAD" else None,
            "last_price": row.get("ltp"), "timestamp_epoch": row.get("ts_epoch"),
            "timestamp_authority": provenance.get("timestamp_authority"),
            "timestamp_source_field": provenance.get("timestamp_source_field"),
            "source_timestamp_epoch": provenance.get("source_timestamp_epoch"),
            "receive_timestamp_epoch": provenance.get("receive_timestamp_epoch"),
            "timestamp_fallback_used": provenance.get("timestamp_fallback_used"),
        }
        lineage_bytes += len(json.dumps(token_rows[str(token)], sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))
        if lineage_bytes > MAX_TICK_LINEAGE_BYTES:
            return {
                "status": "LINEAGE_TICK_BYTE_BOUND_EXCEEDED",
                "read_source": "tick_store_memory_no_db_fallback",
                "intended_token_count": len(requested_tokens),
                "sampled_token_count": len(bounded_tokens),
                "observed_token_count": 0,
                "tokens": {},
                "strategy_input_correlation": "UNKNOWN_LINEAGE_BOUND_EXCEEDED",
            }
    return {
        "status": "TOKEN_BOUND_EXCEEDED" if len(requested_tokens) > MAX_SNAPSHOT_TICK_ROWS else "PROCESS_LOCAL_CACHE_ONLY",
        "read_source": "tick_store_memory_no_db_fallback",
        "intended_token_count": len(requested_tokens),
        "sampled_token_count": len(bounded_tokens),
        "observed_token_count": sum(row.get("status") == "OBSERVED_PROCESS_LOCAL_TICK" for row in token_rows.values()),
        "tokens": token_rows,
        "strategy_input_correlation": "UNKNOWN_UNLESS_SHARED_EVENT_ID_PRESENT",
    }


def compare_snapshot_tick_event_ids(snapshot_lineage: Mapping[str, Any],
                                    process_local_lineage: Mapping[str, Any]) -> dict[str, Any]:
    snapshot_rows = snapshot_lineage.get("ticks") if isinstance(snapshot_lineage, Mapping) else None
    process_rows = process_local_lineage.get("tokens") if isinstance(process_local_lineage, Mapping) else None
    matches: list[str] = []
    mismatches: list[str] = []
    if not isinstance(snapshot_rows, Mapping) or not isinstance(process_rows, Mapping):
        return {"status": "UNKNOWN_LINEAGE_MISSING", "matched_token_count": 0, "mismatched_token_count": 0, "matched_tokens": [], "mismatched_tokens": []}
    for token in sorted(set(snapshot_rows) & set(process_rows)):
        snap = snapshot_rows.get(token)
        cached = process_rows.get(token)
        if (not isinstance(snap, Mapping) or not isinstance(cached, Mapping)
                or snap.get("event_identity_status") != "VERIFIED_EVENT_PAYLOAD"
                or cached.get("event_identity_status") != "VERIFIED_EVENT_PAYLOAD"):
            continue
        if (snap.get("source_event_id") == cached.get("source_event_id")
                and snap.get("source_event_sha256") == cached.get("source_event_sha256")):
            matches.append(str(token))
        else:
            mismatches.append(str(token))
    status = "EVENT_ID_MISMATCH" if mismatches else "VERIFIED_SHARED_EVENT_IDS" if matches else "UNKNOWN_NO_SHARED_VERIFIABLE_EVENT_IDS"
    return {"status": status, "matched_token_count": len(matches),
        "mismatched_token_count": len(mismatches), "matched_tokens": matches,
        "mismatched_tokens": mismatches}


def build_observation_lineage_record(
    *, pulse: NativePulse, pulse_input: Mapping[str, Any], market_snapshot: Mapping[str, Any],
    feed_health_truth: Mapping[str, Any], process_local_tick_lineage: Mapping[str, Any],
    strategy_result: Any, decision_result: Any,
    trade_truth_record: Any,
) -> dict[str, Any]:
    """Bind inputs and read-only outputs to one verified pulse identifier."""
    if not pulse.verify_integrity():
        raise ValueError("LINEAGE_PULSE_INTEGRITY_INVALID")
    pulse_payload_hash = sha256_canonical(pulse_input)
    candidates = [row.to_dict() for row in strategy_result.candidates]
    candidate_ids = [row.get("candidate_id") for row in candidates]
    if any(row.get("pulse_id") != pulse.pulse_id for row in candidates):
        raise ValueError("LINEAGE_CANDIDATE_PULSE_MISMATCH")
    decisions = [row.to_dict() for row in decision_result.selected_candidates]
    if decision_result.pulse_id != pulse.pulse_id:
        raise ValueError("LINEAGE_DECISION_PULSE_MISMATCH")
    if any(row.get("pulse_id") != pulse.pulse_id for row in decisions):
        raise ValueError("LINEAGE_DECISION_PULSE_MISMATCH")
    rejected = list(decision_result.rejected_decisions)
    truth = trade_truth_record.to_dict()
    identity = dict(truth.get("identity") or {})
    if identity.get("trace_id") != pulse.pulse_id:
        raise ValueError("LINEAGE_TRADE_TRUTH_PULSE_MISMATCH")
    snapshot_digest = sha256_canonical(dict(market_snapshot))
    feed_digest = sha256_canonical(dict(feed_health_truth))
    snapshot_tick_inputs = snapshot_tick_lineage(market_snapshot)
    correlation = compare_snapshot_tick_event_ids(snapshot_tick_inputs, process_local_tick_lineage)
    expected_payload = {
        "cycle_count": pulse_input.get("cycle_count"),
        "interval_end_epoch": pulse_input.get("interval_end_epoch"),
        "market_open": pulse_input.get("market_open"),
        "feed_live": pulse_input.get("feed_live"),
        "market_snapshot_sha256": snapshot_digest,
        "tick_lineage": snapshot_tick_inputs,
        "process_local_tick_lineage": dict(process_local_tick_lineage),
        "tick_store_snapshot_correlation": correlation,
        "feed_health_truth_sha256": feed_digest,
    }
    if dict(pulse_input) != expected_payload:
        raise ValueError("LINEAGE_PULSE_INPUT_MISMATCH")
    if pulse.payload_sha256 != pulse_payload_hash:
        raise ValueError("LINEAGE_PULSE_PAYLOAD_HASH_MISMATCH")
    return {
        "schema_version": 1,
        "pulse_id": pulse.pulse_id,
        "pulse_sequence": pulse.sequence_num,
        "pulse": pulse.to_dict(),
        "pulse_payload_sha256": pulse.payload_sha256,
        "pulse_input": dict(pulse_input),
        "market_snapshot_sha256": snapshot_digest,
        "feed_health_truth_sha256": feed_digest,
        "tick_lineage": expected_payload["tick_lineage"],
        "process_local_tick_lineage": dict(process_local_tick_lineage),
        "tick_store_snapshot_correlation": correlation,
        "strategy_result_pulse_id": strategy_result.pulse_id,
        "strategy_candidates": candidate_ids,
        "candidate_bindings": [{"candidate_id": row.get("candidate_id"), "pulse_id": row.get("pulse_id"), "payload_sha256": row.get("payload_sha256")} for row in candidates],
        "strategy_rejection_count": len(strategy_result.rejections),
        "evaluated_symbol_count": strategy_result.evaluated_symbol_count,
        "decision_result_pulse_id": decision_result.pulse_id,
        "selected_candidate_ids": [row.get("candidate_id") for row in decisions],
        "selected_candidate_bindings": [{"candidate_id": row.get("candidate_id"), "pulse_id": row.get("pulse_id"), "payload_sha256": row.get("payload_sha256")} for row in decisions],
        "rejected_decisions": rejected,
        "trade_truth_record_id": identity.get("truth_record_id"),
        "trade_truth_pulse_id": identity.get("trace_id"),
        "trade_truth_record_hash": truth.get("record_hash"),
        "authority": {
            "read_only": True, "append": False, "is_order_action": False,
            "broker_api_called": False, "broker_write_authority": False,
            "order_authority": False, "paper_authorized": False,
            "live_authorized": False, "allowed_for_live_execution": False,
        },
    }


def verify_observation_lineage_record(record: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Independently check hash closure and exact pulse joins in one envelope."""
    errors: list[str] = []
    try:
        schema_version = int(record.get("schema_version") or 0)
    except (TypeError, ValueError, OverflowError):
        schema_version = 0
    if schema_version != 1:
        errors.append("SCHEMA_VERSION_INVALID")
    pulse_input = record.get("pulse_input")
    if not isinstance(pulse_input, Mapping):
        errors.append("PULSE_INPUT_MISSING")
    else:
        if sha256_canonical(pulse_input) != record.get("pulse_payload_sha256"):
            errors.append("PULSE_INPUT_HASH_MISMATCH")
        if pulse_input.get("market_snapshot_sha256") != record.get("market_snapshot_sha256"):
            errors.append("SNAPSHOT_HASH_MISMATCH")
        if pulse_input.get("feed_health_truth_sha256") != record.get("feed_health_truth_sha256"):
            errors.append("FEED_TRUTH_HASH_MISMATCH")
        if pulse_input.get("tick_lineage") != record.get("tick_lineage"):
            errors.append("TICK_LINEAGE_MISMATCH")
        if pulse_input.get("process_local_tick_lineage") != record.get("process_local_tick_lineage"):
            errors.append("PROCESS_LOCAL_TICK_LINEAGE_MISMATCH")
        expected_correlation = compare_snapshot_tick_event_ids(
            record.get("tick_lineage") or {}, record.get("process_local_tick_lineage") or {},
        )
        if expected_correlation != record.get("tick_store_snapshot_correlation"):
            errors.append("TICK_STORE_SNAPSHOT_CORRELATION_MISMATCH")
        tick_lineage = record.get("tick_lineage")
        tick_rows = tick_lineage.get("ticks") if isinstance(tick_lineage, Mapping) else None
        if isinstance(tick_rows, Mapping):
            for token_text, tick in tick_rows.items():
                if not isinstance(tick, Mapping):
                    errors.append(f"TICK_LINEAGE_ROW_INVALID:{token_text}")
                    continue
                if tick.get("event_identity_status") == "INVALID_EVENT_PAYLOAD_BINDING":
                    errors.append(f"TICK_EVENT_BINDING_INVALID:{token_text}")
                    continue
                if tick.get("event_identity_status") != "VERIFIED_EVENT_PAYLOAD":
                    continue
                payload = tick.get("source_event_payload")
                try:
                    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
                    event_sha = hashlib.sha256(encoded).hexdigest()
                    if (event_sha != tick.get("source_event_sha256")
                            or int(payload.get("instrument_token")) != int(token_text)
                            or not str(tick.get("source_event_id") or "").endswith(f":{token_text}:{event_sha[:16]}")
                            or float(payload.get("last_price")) != float(tick.get("last_price"))
                            or float(payload.get("source_timestamp_epoch")) != float(tick.get("source_timestamp_epoch"))
                            or payload.get("source_timestamp_field") != tick.get("timestamp_source_field")):
                        errors.append(f"TICK_EVENT_BINDING_INVALID:{token_text}")
                except (AttributeError, TypeError, ValueError, OverflowError):
                    errors.append(f"TICK_EVENT_BINDING_INVALID:{token_text}")
        process_lineage = record.get("process_local_tick_lineage")
        process_tokens = process_lineage.get("tokens") if isinstance(process_lineage, Mapping) else None
        if isinstance(process_tokens, Mapping):
            for token_text, tick in process_tokens.items():
                if not isinstance(tick, Mapping):
                    errors.append(f"PROCESS_LOCAL_TICK_ROW_INVALID:{token_text}")
                    continue
                if tick.get("event_identity_status") != "VERIFIED_EVENT_PAYLOAD":
                    if tick.get("event_identity_status") == "INVALID_EVENT_PAYLOAD_BINDING":
                        errors.append(f"PROCESS_LOCAL_EVENT_BINDING_INVALID:{token_text}")
                    continue
                payload = tick.get("source_event_payload")
                try:
                    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
                    event_sha = hashlib.sha256(encoded).hexdigest()
                    if (event_sha != tick.get("source_event_sha256")
                            or int(payload.get("instrument_token")) != int(token_text)
                            or not str(tick.get("source_event_id") or "").endswith(f":{token_text}:{event_sha[:16]}")
                            or float(payload.get("last_price")) != float(tick.get("last_price"))
                            or float(payload.get("source_timestamp_epoch")) != float(tick.get("source_timestamp_epoch"))
                            or payload.get("source_timestamp_field") != tick.get("timestamp_source_field")):
                        errors.append(f"PROCESS_LOCAL_EVENT_BINDING_INVALID:{token_text}")
                except (AttributeError, TypeError, ValueError, OverflowError):
                    errors.append(f"PROCESS_LOCAL_EVENT_BINDING_INVALID:{token_text}")
    pulse_id = record.get("pulse_id")
    pulse = record.get("pulse")
    if not isinstance(pulse, Mapping):
        errors.append("PULSE_DESCRIPTOR_MISSING")
    else:
        try:
            recomputed_pulse_id = derive_pulse_id(
                session_id=str(pulse["session_id"]),
                sequence_num=int(pulse["sequence_num"]),
                timestamp_epoch=float(pulse["timestamp_epoch"]),
                payload_sha256=str(pulse["payload_sha256"]),
                parent_pulse_id=pulse.get("parent_pulse_id"),
                producer_sha=str(pulse["producer_sha"]),
            )
            if (recomputed_pulse_id != pulse_id or pulse.get("pulse_id") != pulse_id
                    or int(pulse.get("sequence_num")) != int(record.get("pulse_sequence") or 0)
                    or pulse.get("payload_sha256") != record.get("pulse_payload_sha256")):
                errors.append("PULSE_IDENTITY_INVALID")
        except (KeyError, TypeError, ValueError, OverflowError):
            errors.append("PULSE_IDENTITY_INVALID")
    if record.get("strategy_result_pulse_id") != pulse_id:
        errors.append("STRATEGY_PULSE_JOIN_MISMATCH")
    if record.get("decision_result_pulse_id") != pulse_id:
        errors.append("DECISION_PULSE_JOIN_MISMATCH")
    if record.get("trade_truth_pulse_id") != pulse_id:
        errors.append("TRADE_TRUTH_PULSE_JOIN_MISMATCH")
    for field in ("candidate_bindings", "selected_candidate_bindings"):
        bindings = record.get(field)
        if not isinstance(bindings, list) or any(not isinstance(row, Mapping) or row.get("pulse_id") != pulse_id for row in bindings):
            errors.append(f"{field.upper()}_PULSE_JOIN_MISMATCH")
    if not set(record.get("selected_candidate_ids") or []).issubset(set(record.get("strategy_candidates") or [])):
        errors.append("DECISION_CANDIDATE_MEMBERSHIP_MISMATCH")
    if not record.get("trade_truth_record_hash"):
        errors.append("TRADE_TRUTH_HASH_MISSING")
    authority = record.get("authority")
    if not isinstance(authority, Mapping) or any(authority.get(key) is not value for key, value in {
        "read_only": True, "append": False, "is_order_action": False,
        "broker_api_called": False, "broker_write_authority": False,
        "order_authority": False, "paper_authorized": False,
        "live_authorized": False, "allowed_for_live_execution": False,
    }.items()):
        errors.append("AUTHORITY_BOUNDARY_INVALID")
    return not errors, errors
