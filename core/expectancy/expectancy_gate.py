from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Mapping

EXPECTANCY_GATE_SCHEMA_VERSION = 1
EXPECTANCY_KILL = "KILL"
EXPECTANCY_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
EXPECTANCY_WATCH = "WATCH"
EXPECTANCY_KEEP = "KEEP"
_VALID_STATUSES = {
    EXPECTANCY_KILL,
    EXPECTANCY_INSUFFICIENT_DATA,
    EXPECTANCY_WATCH,
    EXPECTANCY_KEEP,
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExpectancyGateDecision:
    schema_version: int
    expectancy_status: str
    expectancy_status_reason: str
    expectancy_gate_reason: str
    setup_id: str | None
    strategy_family: str
    regime: str
    index: str
    expiry_type: str
    option_type: str
    direction: str
    read_only: bool = True
    append: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    return {}


def _status_from_value(value: Any) -> str:
    status = _upper(value)
    return status if status in _VALID_STATUSES else EXPECTANCY_INSUFFICIENT_DATA


def _lookup_nested(lookup: Mapping[str, Any], key_parts: tuple[str, ...]) -> Any:
    current: Any = lookup
    for key in key_parts:
        if not isinstance(current, Mapping):
            return None
        if key not in current:
            return None
        current = current[key]
    return current


def _resolve_status(entry: Mapping[str, Any], expectancy_lookup: Any = None) -> tuple[str, str]:
    explicit_override = _text(
        entry.get("expectancy_override")
        or entry.get("expectancy_status_override")
        or entry.get("manual_expectancy_override")
        or (entry.get("source_flags") or {}).get("expectancy_override")
    )
    if explicit_override:
        logger.warning(
            "expectancy_gate_manual_override trade_id=%s candidate_id=%s override=%s",
            entry.get("trade_id"),
            entry.get("candidate_id"),
            explicit_override,
        )
        return _status_from_value(explicit_override), "manual_expectancy_override"

    direct_status = _text(entry.get("expectancy_status") or entry.get("keep_watch_kill_status"))
    if direct_status:
        return _status_from_value(direct_status), "row_expectancy_status"

    lookup_value = expectancy_lookup
    if lookup_value is None:
        lookup_value = entry.get("expectancy_lookup")
    if lookup_value is None and isinstance(entry.get("metadata"), Mapping):
        lookup_value = (entry.get("metadata") or {}).get("expectancy_lookup")
    if lookup_value is None and isinstance(entry.get("source_flags"), Mapping):
        lookup_value = (entry.get("source_flags") or {}).get("expectancy_lookup")

    if callable(lookup_value):
        resolved = lookup_value(entry)
        if isinstance(resolved, Mapping):
            resolved = resolved.get("expectancy_status") or resolved.get("keep_watch_kill_status")
        if resolved is not None:
            return _status_from_value(resolved), "callable_expectancy_lookup"

    if isinstance(lookup_value, Mapping):
        setup_id = _text(entry.get("setup_id"))
        strategy_family = _text(entry.get("strategy_family")).lower()
        regime = _text(entry.get("regime")).lower()
        index = _text(entry.get("index")).lower()
        expiry_type = _text(entry.get("expiry_type")).lower()
        option_type = _text(entry.get("option_type")).lower()
        direction = _text(entry.get("direction") or entry.get("side")).lower()

        candidates: list[Any] = [
            lookup_value.get(setup_id) if setup_id else None,
            lookup_value.get((strategy_family, regime, setup_id)) if setup_id else None,
            lookup_value.get((strategy_family, regime, index, expiry_type, option_type, direction)),
            lookup_value.get((strategy_family, regime, index)),
            lookup_value.get((strategy_family, regime)),
        ]
        nested = _lookup_nested(lookup_value, (strategy_family, regime, setup_id)) if setup_id else None
        if nested is not None:
            candidates.insert(0, nested)
        nested = _lookup_nested(lookup_value, (strategy_family, regime))
        if nested is not None:
            candidates.append(nested)
        for candidate in candidates:
            if candidate is None:
                continue
            if isinstance(candidate, Mapping):
                resolved = candidate.get("expectancy_status") or candidate.get("keep_watch_kill_status")
                if resolved is not None:
                    return _status_from_value(resolved), "mapping_expectancy_lookup"
            else:
                return _status_from_value(candidate), "mapping_expectancy_lookup"

    return EXPECTANCY_INSUFFICIENT_DATA, "missing_expectancy_lookup"


def _lifecycle_rank(entry: Mapping[str, Any]) -> int:
    permission = _upper(entry.get("permission"))
    final_action = _upper(entry.get("final_action"))
    readiness = _upper(entry.get("readiness"))
    execution_status = _text(entry.get("execution_status")).lower()
    if (
        permission == "BLOCK"
        or final_action == "BLOCK"
        or readiness == "BLOCKED"
        or execution_status == "blocked"
    ):
        return 3
    if (
        permission == "QUEUE_ONLY"
        or final_action == "QUEUE_ONLY"
        or readiness == "QUEUE_ONLY"
        or execution_status == "queue_only"
    ):
        return 2
    if (
        permission == "ADVISORY_ONLY"
        or final_action == "ADVISORY_ONLY"
        or readiness == "ADVISORY_ONLY"
        or execution_status == "advisory_only"
    ):
        return 1
    return 0


def _set_strict_lifecycle(entry: dict[str, Any], status: str, *, reason: str) -> dict[str, Any]:
    out = dict(entry)
    current_rank = _lifecycle_rank(out)
    target_rank = 3 if status == EXPECTANCY_KILL else 2
    if current_rank >= target_rank:
        if not str(out.get("expectancy_gate_reason") or "").strip():
            out["expectancy_gate_reason"] = reason
        return out
    if status == EXPECTANCY_KILL:
        out["permission"] = "BLOCK"
        out["final_action"] = "BLOCK"
        out["readiness"] = "BLOCKED"
        out["execution_status"] = "blocked"
        out["candidate_status"] = "blocked"
        out["visibility_bucket"] = "blocked"
        out["tradable"] = False
        out["is_executable"] = False
    else:
        out["permission"] = "QUEUE_ONLY"
        out["final_action"] = "QUEUE_ONLY"
        out["readiness"] = "QUEUE_ONLY"
        out["execution_status"] = "queue_only"
        out["candidate_status"] = "advisory_only"
        out["visibility_bucket"] = "advisory"
        out["tradable"] = False
        out["is_executable"] = False
        out["selected_for_execution"] = False
    out["reportable_executable"] = False
    out["execution_allowed"] = False
    out["eligible_for_execution"] = False
    out["selected_for_execution"] = False
    out["fallback_used"] = bool(out.get("fallback_used"))
    if not str(out.get("final_emit_block_reason") or "").strip():
        out["final_emit_block_reason"] = reason
    if not str(out.get("permission_reason") or "").strip():
        out["permission_reason"] = reason
    out["expectancy_gate_reason"] = reason
    return out


def apply_expectancy_gate(
    entry: Mapping[str, Any] | dict[str, Any],
    expectancy_lookup: Any = None,
) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return dict(entry or {})
    row = dict(entry)
    status, reason = _resolve_status(row, expectancy_lookup=expectancy_lookup)
    row["expectancy_status"] = status
    row["expectancy_status_reason"] = reason
    row["expectancy_gate_applied"] = True
    row["expectancy_gate_reason"] = reason
    row["reportable_executable"] = bool(row.get("reportable_executable")) if status == EXPECTANCY_KEEP else False
    if status == EXPECTANCY_KEEP:
        return row
    gated = _set_strict_lifecycle(row, status, reason=f"expectancy_{status.lower()}")
    if not str(gated.get("reason") or "").strip():
        gated["reason"] = gated.get("expectancy_gate_reason") or f"expectancy_{status.lower()}"
    return gated


__all__ = [
    "EXPECTANCY_GATE_SCHEMA_VERSION",
    "EXPECTANCY_KEEP",
    "EXPECTANCY_INSUFFICIENT_DATA",
    "EXPECTANCY_KILL",
    "EXPECTANCY_WATCH",
    "ExpectancyGateDecision",
    "apply_expectancy_gate",
]
