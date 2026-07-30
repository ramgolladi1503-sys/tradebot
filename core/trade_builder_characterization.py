"""Deterministic characterization helpers for the legacy TradeBuilder facade."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence


_VOLATILE_FIELDS = {
    "generated_at",
    "generated_epoch",
    "timestamp",
    "ts",
    "ts_epoch",
    "created_at",
    "created_ts",
    "created_ts_epoch",
    "display_ts_epoch",
    "decision_ts_epoch",
    "last_seen",
    "last_seen_ts",
    "latency_ms",
    "elapsed_ms",
}


@dataclass(frozen=True)
class CharacterizationRecord:
    case_id: str
    output_hash: str
    normalized_output: Any
    raised: bool = False
    error_type: str | None = None
    error_message: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "output_hash": self.output_hash,
            "normalized_output": self.normalized_output,
            "raised": self.raised,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


def _normalize(value: Any, *, strip_volatile: bool = True) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        items = sorted(((str(key), item) for key, item in value.items()), key=lambda pair: pair[0])
        for key, item in items:
            if strip_volatile and key in _VOLATILE_FIELDS:
                continue
            out[key] = _normalize(item, strip_volatile=strip_volatile)
        return out
    if isinstance(value, (list, tuple)):
        return [_normalize(item, strip_volatile=strip_volatile) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_normalize(item, strip_volatile=strip_volatile) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float):
        if value != value:
            return "NaN"
        if value == float("inf"):
            return "Infinity"
        if value == float("-inf"):
            return "-Infinity"
        return round(value, 12)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, "__dict__"):
        return _normalize(vars(value), strip_volatile=strip_volatile)
    return str(value)


def normalize_builder_output(value: Any) -> Any:
    return _normalize(value, strip_volatile=True)


def hash_builder_output(value: Any) -> str:
    normalized = normalize_builder_output(value)
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def characterize_call(
    case_id: str,
    callable_obj: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> CharacterizationRecord:
    try:
        output = callable_obj(*args, **kwargs)
    except Exception as exc:
        normalized = {
            "raised": True,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        return CharacterizationRecord(
            case_id=case_id,
            output_hash=hash_builder_output(normalized),
            normalized_output=normalized,
            raised=True,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    normalized = normalize_builder_output(output)
    return CharacterizationRecord(
        case_id=case_id,
        output_hash=hash_builder_output(normalized),
        normalized_output=normalized,
    )


def characterize_builder(
    builder: Any,
    snapshots: Sequence[Mapping[str, Any]],
    *,
    build_method: str = "build",
) -> tuple[CharacterizationRecord, ...]:
    method = getattr(builder, build_method, None)
    if not callable(method):
        raise TypeError(f"trade_builder_method_missing:{build_method}")
    records: list[CharacterizationRecord] = []
    for index, snapshot in enumerate(snapshots):
        case_id = str(snapshot.get("case_id") or f"case_{index:03d}")
        records.append(characterize_call(case_id, method, dict(snapshot)))
    return tuple(records)


def assert_repeatable(
    run_a: Iterable[CharacterizationRecord],
    run_b: Iterable[CharacterizationRecord],
) -> None:
    left = tuple((item.case_id, item.output_hash) for item in run_a)
    right = tuple((item.case_id, item.output_hash) for item in run_b)
    if left != right:
        raise AssertionError(f"trade_builder_characterization_mismatch:{left!r}!={right!r}")


__all__ = [
    "CharacterizationRecord",
    "assert_repeatable",
    "characterize_builder",
    "characterize_call",
    "hash_builder_output",
    "normalize_builder_output",
]
