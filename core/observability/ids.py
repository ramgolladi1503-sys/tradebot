from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

_ID_SAFE_RE = re.compile(r"[^a-z0-9_.-]+")
_MULTI_SEP_RE = re.compile(r"[_-]{2,}")
_MAX_COMPONENT_LEN = 80
_HASH_LEN = 12


class ObservabilityIdentityError(ValueError):
    """Raised when an observability identity cannot be created safely."""


@dataclass(frozen=True)
class ObservabilityIds:
    """Stable identifier bundle for one observable Tradebot scope."""

    run_id: str
    cycle_id: str
    trace_id: str
    span_id: str | None = None
    candidate_id: str | None = None

    def as_dict(self) -> dict[str, str]:
        """Return only populated identity fields as plain strings."""

        payload = {
            "run_id": self.run_id,
            "cycle_id": self.cycle_id,
            "trace_id": self.trace_id,
        }
        if self.span_id:
            payload["span_id"] = self.span_id
        if self.candidate_id:
            payload["candidate_id"] = self.candidate_id
        return payload


def build_run_id(*, started_at: datetime | None = None, label: str = "tradebot") -> str:
    """Build a stable run identifier from a timestamp and label."""

    timestamp = _format_timestamp(started_at or datetime.now(timezone.utc))
    return _join_identity("run", normalize_identity_component(label), timestamp)


def build_cycle_id(*, run_id: str, sequence: int, started_at: datetime | None = None) -> str:
    """Build a cycle identifier scoped to a run and sequence number."""

    if sequence < 0:
        raise ObservabilityIdentityError("cycle_sequence_must_be_non_negative")
    timestamp = _format_timestamp(started_at or datetime.now(timezone.utc))
    return _join_identity(
        "cycle",
        normalize_identity_component(run_id),
        f"{sequence:06d}",
        timestamp,
    )


def build_trace_id(*, scope: str, stable_parts: Mapping[str, object] | None = None) -> str:
    """Build a deterministic trace identifier for a cycle or candidate scope."""

    normalized_scope = normalize_identity_component(scope)
    digest = _stable_hash(stable_parts or {"scope": normalized_scope})
    return _join_identity("trace", normalized_scope, digest)


def build_span_id(*, stage: str, trace_id: str) -> str:
    """Build a deterministic span identifier from a trace and stage."""

    normalized_stage = normalize_identity_component(stage)
    digest = _stable_hash({"trace_id": trace_id, "stage": normalized_stage})
    return _join_identity("span", normalized_stage, digest)


def build_candidate_id(
    *,
    symbol: str,
    side: str | None = None,
    strike: int | str | None = None,
    option_type: str | None = None,
    strategy_id: str | None = None,
    cycle_id: str | None = None,
    extra: Mapping[str, object] | None = None,
) -> str:
    """Build a deterministic candidate identifier from trading-safe metadata."""

    parts: list[str] = ["candidate", normalize_identity_component(symbol)]
    for value in (option_type, strike, side, strategy_id):
        if value is not None:
            parts.append(normalize_identity_component(value))
    stable_parts: dict[str, object] = {
        "symbol": symbol,
        "side": side,
        "strike": strike,
        "option_type": option_type,
        "strategy_id": strategy_id,
        "cycle_id": cycle_id,
    }
    if extra:
        stable_parts["extra"] = dict(extra)
    parts.append(_stable_hash(stable_parts))
    return _join_identity(*parts)


def normalize_identity_component(value: object) -> str:
    """Normalize one identifier component into a compact safe token."""

    raw = str(value).strip().lower()
    if not raw:
        raise ObservabilityIdentityError("identity_component_empty")
    normalized = _ID_SAFE_RE.sub("_", raw)
    normalized = _MULTI_SEP_RE.sub("_", normalized).strip("_.-")
    if not normalized:
        raise ObservabilityIdentityError("identity_component_not_representable")
    if len(normalized) <= _MAX_COMPONENT_LEN:
        return normalized
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:_HASH_LEN]
    return f"{normalized[:_MAX_COMPONENT_LEN - _HASH_LEN - 1]}_{digest}"


def _join_identity(*parts: str) -> str:
    normalized = [normalize_identity_component(part) for part in parts if part]
    if not normalized:
        raise ObservabilityIdentityError("identity_requires_at_least_one_component")
    return "_".join(normalized)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _stable_hash(parts: Mapping[str, object]) -> str:
    flattened = _flatten_mapping(parts)
    payload = "|".join(f"{key}={value}" for key, value in flattened)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_HASH_LEN]


def _flatten_mapping(parts: Mapping[str, object], prefix: str = "") -> tuple[tuple[str, str], ...]:
    flattened: list[tuple[str, str]] = []
    for key in sorted(parts, key=str):
        value = parts[key]
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flattened.extend(_flatten_mapping(value, prefix=name))
        else:
            flattened.append((name, "" if value is None else str(value)))
    return tuple(flattened)
