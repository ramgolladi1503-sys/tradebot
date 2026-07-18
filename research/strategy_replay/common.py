from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


class StrategyReplayError(RuntimeError):
    pass


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _mapping_or_dict(record: Any) -> Mapping[str, Any]:
    if isinstance(record, Mapping):
        return record
    if hasattr(record, "to_dict"):
        payload = record.to_dict()
        if isinstance(payload, Mapping):
            return payload
    if hasattr(record, "__dict__"):
        return vars(record)
    raise TypeError(f"unsupported_record_type:{type(record)!r}")


def _string_field(record: Any, field: str) -> str:
    value = _mapping_or_dict(record).get(field)
    return str(value or "")


def canonical_session_key(record: Any) -> str:
    payload = {
        "logical_path": _string_field(record, "logical_path"),
        "session_date": _string_field(record, "session_date"),
        "sha256": _string_field(record, "sha256"),
        "symbol": _string_field(record, "symbol"),
    }
    return canonical_json_bytes(payload).decode("utf-8")


def partition_assignment(record: Any, *, shard_count: int) -> int:
    if shard_count < 1:
        raise ValueError("shard_count_must_be_positive")
    digest = sha256_bytes(canonical_session_key(record).encode("utf-8"))
    return int(digest, 16) % shard_count


def sorted_records(records: Iterable[Any]) -> list[dict[str, Any]]:
    materialized = [dict(_mapping_or_dict(record)) for record in records]
    return sorted(
        materialized,
        key=lambda item: (
            str(item.get("symbol") or ""),
            str(item.get("session_date") or ""),
            str(item.get("logical_path") or ""),
            str(item.get("sha256") or ""),
        ),
    )


def selection_summary(records: Iterable[Any]) -> dict[str, Any]:
    ordered = sorted_records(records)
    symbol_counts = Counter(str(record.get("symbol") or "") for record in ordered)
    selected_via = Counter(str(record.get("selected_via") or "") for record in ordered if str(record.get("selected_via") or ""))
    sessions = [str(record.get("session_date") or "") for record in ordered if str(record.get("session_date") or "")]
    return {
        "selected_file_count": len(ordered),
        "symbol_counts": dict(sorted(symbol_counts.items())),
        "earliest_session": min(sessions, default=None),
        "latest_session": max(sessions, default=None),
        "selected_via": dict(sorted(selected_via.items())),
        "semantic_hash": sha256_bytes(canonical_json_bytes(ordered)),
    }


def recompute_candidate_hash(entries: Iterable[Any]) -> str:
    materialized = [dict(_mapping_or_dict(entry)) for entry in entries]
    return sha256_bytes(canonical_json_bytes(materialized))


def validate_ledger(entries: Iterable[Any], *, expected_candidate_hash: str | None = None) -> str:
    materialized = [dict(_mapping_or_dict(entry)) for entry in entries]
    for index, entry in enumerate(materialized):
        missing = [field for field in ("symbol", "session_date", "direction", "proposal_ready_at_iso", "setup_id", "history_hash") if not str(entry.get(field) or "").strip()]
        if missing:
            raise StrategyReplayError(f"ledger_entry_missing_fields:{index}:{','.join(missing)}")
    actual_hash = recompute_candidate_hash(materialized)
    if expected_candidate_hash is not None and actual_hash != expected_candidate_hash:
        raise StrategyReplayError(
            f"candidate_semantic_hash_mismatch:expected={expected_candidate_hash}:actual={actual_hash}"
        )
    return actual_hash


def write_canonical_json(path: Path, payload: Any) -> str:
    serialized = canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(serialized + b"\n")
    digest = sha256_bytes(serialized)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def verify_sha256_sidecar(path: Path) -> str:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.exists():
        raise StrategyReplayError(f"artifact_missing:{path}")
    if not sidecar.exists():
        raise StrategyReplayError(f"artifact_sidecar_missing:{sidecar}")
    expected = str(sidecar.read_text(encoding="utf-8").split()[0]).strip().lower()
    if len(expected) != 64:
        raise StrategyReplayError(f"artifact_sidecar_malformed:{sidecar}")
    actual = sha256_bytes(path.read_bytes().rstrip(b"\n"))
    if actual != expected:
        raise StrategyReplayError(f"artifact_sidecar_hash_mismatch:{path}:expected={expected}:actual={actual}")
    return actual


def load_canonical_json(path: Path) -> Any:
    verify_sha256_sidecar(path)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_evidence_envelope(payload: Mapping[str, Any]) -> None:
    required = (
        "mode",
        "candidate_id",
        "decision",
        "reason",
        "timestamp",
        "read_only",
        "append",
        "is_order_action",
        "broker_api_called",
        "allowed_for_live_execution",
        "source",
    )
    missing = [field for field in required if field not in payload]
    if missing:
        raise StrategyReplayError(f"evidence_envelope_missing:{','.join(missing)}")
    if payload["read_only"] is not True:
        raise StrategyReplayError("evidence_envelope_read_only_required")
    if payload["append"] is not False:
        raise StrategyReplayError("evidence_envelope_append_forbidden")
    if payload["is_order_action"] is not False:
        raise StrategyReplayError("evidence_envelope_order_action_forbidden")
    if payload["broker_api_called"] is not False:
        raise StrategyReplayError("evidence_envelope_broker_call_forbidden")
    if payload["allowed_for_live_execution"] is not False:
        raise StrategyReplayError("evidence_envelope_live_execution_forbidden")
