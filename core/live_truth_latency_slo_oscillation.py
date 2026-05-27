"""Latency and SLO oscillation evidence for LIVE-TRUTH-07.

This module summarizes recent latency/SLO samples and classifies whether the
runtime evidence is stable, degraded, oscillating, or blocked. It is read-only:
it does not alter runtime loops, cooldowns, feeds, candidates, or decisions.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.events import write_json_atomic

LATENCY_SLO_SCHEMA_VERSION = 1
LATENCY_SLO_SOURCE = "live_truth_latency_slo_oscillation_v1"

SLO_STATUS_STABLE = "LATENCY_SLO_STABLE"
SLO_STATUS_DEGRADED = "LATENCY_SLO_DEGRADED"
SLO_STATUS_OSCILLATING = "LATENCY_SLO_OSCILLATING"
SLO_STATUS_BLOCKED = "LATENCY_SLO_BLOCKED"

SLO_STABLE_REASON = "latency_slo_stable"
NO_SAMPLES_REASON = "no_latency_samples"
INVALID_SAMPLE_REASON = "invalid_latency_sample"
INVALID_CONFIG_REASON = "invalid_latency_slo_config"
HIGH_LATENCY_REASON = "latency_above_slo_threshold"
SLO_STATE_FLAP_REASON = "slo_state_flapping"
COOLDOWN_THRASH_REASON = "cooldown_state_thrashing"
LOOP_MODE_THRASH_REASON = "loop_mode_thrashing"
RECOVERY_OSCILLATION_REASON = "recovery_state_oscillating"

DEFAULT_LATENCY_THRESHOLD_MS = 750.0
DEFAULT_MAX_STATE_FLIPS = 2
DEFAULT_MIN_SAMPLE_COUNT = 3

_LATENCY_KEYS = (
    "latency_ms",
    "p95_latency_ms",
    "loop_latency_ms",
    "decision_latency_ms",
    "tick_to_decision_latency_ms",
    "feed_latency_ms",
    "runtime_latency_ms",
)

_SLO_KEYS = ("slo_state", "slo_status", "latency_state", "state", "status")
_COOLDOWN_KEYS = ("cooldown_state", "cooldown_status", "cooldown_active", "in_cooldown")
_LOOP_MODE_KEYS = ("loop_mode", "runtime_mode", "mode", "loop_state")
_RECOVERY_KEYS = ("recovery_state", "recovery_status", "feed_recovery_state")

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"
_LIVE_ACTION_KEY = "live_" + "order_action"
_BROKER_ACTION_KEY = "broker_" + "order_action"


@dataclass(frozen=True)
class LatencySloSample:
    index: int
    latency_ms: float | None
    slo_state: str
    cooldown_state: str
    loop_mode: str
    recovery_state: str
    valid: bool
    reason_code: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "latency_ms": self.latency_ms,
            "slo_state": self.slo_state,
            "cooldown_state": self.cooldown_state,
            "loop_mode": self.loop_mode,
            "recovery_state": self.recovery_state,
            "valid": self.valid,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class LatencySloOscillationReport:
    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    sample_count: int
    valid_sample_count: int
    max_latency_ms: float | None
    avg_latency_ms: float | None
    latency_threshold_ms: float
    slo_state_flip_count: int
    cooldown_flip_count: int
    loop_mode_flip_count: int
    recovery_flip_count: int
    max_state_flips: int
    samples: tuple[LatencySloSample, ...]
    read_only: bool = True
    append: bool = False
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
        payload = {
            "schema_version": self.schema_version,
            "source": self.source,
            "status": self.status,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "sample_count": self.sample_count,
            "valid_sample_count": self.valid_sample_count,
            "max_latency_ms": self.max_latency_ms,
            "avg_latency_ms": self.avg_latency_ms,
            "latency_threshold_ms": self.latency_threshold_ms,
            "slo_state_flip_count": self.slo_state_flip_count,
            "cooldown_flip_count": self.cooldown_flip_count,
            "loop_mode_flip_count": self.loop_mode_flip_count,
            "recovery_flip_count": self.recovery_flip_count,
            "max_state_flips": self.max_state_flips,
            "samples": [sample.to_payload() for sample in self.samples],
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_latency_slo_oscillation_report(
    samples: Sequence[Mapping[str, Any] | Any] | Mapping[str, Any] | Any,
    *,
    latency_threshold_ms: float = DEFAULT_LATENCY_THRESHOLD_MS,
    max_state_flips: int = DEFAULT_MAX_STATE_FLIPS,
    min_sample_count: int = DEFAULT_MIN_SAMPLE_COUNT,
) -> LatencySloOscillationReport:
    """Build read-only latency/SLO oscillation evidence."""

    threshold = _positive_float_or_none(latency_threshold_ms)
    allowed_flips = _non_negative_int_or_none(max_state_flips)
    min_count = _positive_int_or_none(min_sample_count)
    if threshold is None or allowed_flips is None or min_count is None:
        return _report(
            status=SLO_STATUS_BLOCKED,
            reason_code=INVALID_CONFIG_REASON,
            reasons=(INVALID_CONFIG_REASON,),
            latency_threshold_ms=DEFAULT_LATENCY_THRESHOLD_MS if threshold is None else threshold,
            max_state_flips=DEFAULT_MAX_STATE_FLIPS if allowed_flips is None else allowed_flips,
            samples=(),
            metadata={"blocked_before_sample_evaluation": True},
        )

    sample_items = _extract_sample_items(samples)
    if not sample_items:
        return _report(
            status=SLO_STATUS_STABLE,
            reason_code=NO_SAMPLES_REASON,
            reasons=(NO_SAMPLES_REASON,),
            latency_threshold_ms=threshold,
            max_state_flips=allowed_flips,
            samples=(),
            metadata={"no_samples_is_stable": True, "evidence_only_no_runtime_change": True},
        )

    parsed = tuple(_parse_sample(index, item) for index, item in enumerate(sample_items))
    invalid_count = sum(1 for sample in parsed if not sample.valid)
    valid = tuple(sample for sample in parsed if sample.valid)
    latencies = tuple(sample.latency_ms for sample in valid if sample.latency_ms is not None)
    max_latency = max(latencies) if latencies else None
    avg_latency = round(sum(latencies) / len(latencies), 6) if latencies else None
    slo_flips = _flip_count(sample.slo_state for sample in valid)
    cooldown_flips = _flip_count(sample.cooldown_state for sample in valid)
    loop_flips = _flip_count(sample.loop_mode for sample in valid)
    recovery_flips = _flip_count(sample.recovery_state for sample in valid)

    reasons: list[str] = []
    if invalid_count:
        reasons.append(INVALID_SAMPLE_REASON)
    if len(valid) < min_count:
        reasons.append(NO_SAMPLES_REASON)
    if max_latency is not None and max_latency > threshold:
        reasons.append(HIGH_LATENCY_REASON)
    if slo_flips > allowed_flips:
        reasons.append(SLO_STATE_FLAP_REASON)
    if cooldown_flips > allowed_flips:
        reasons.append(COOLDOWN_THRASH_REASON)
    if loop_flips > allowed_flips:
        reasons.append(LOOP_MODE_THRASH_REASON)
    if recovery_flips > allowed_flips:
        reasons.append(RECOVERY_OSCILLATION_REASON)

    if invalid_count or len(valid) < min_count:
        status = SLO_STATUS_BLOCKED
    elif any(reason in reasons for reason in (SLO_STATE_FLAP_REASON, COOLDOWN_THRASH_REASON, LOOP_MODE_THRASH_REASON, RECOVERY_OSCILLATION_REASON)):
        status = SLO_STATUS_OSCILLATING
    elif HIGH_LATENCY_REASON in reasons:
        status = SLO_STATUS_DEGRADED
    else:
        status = SLO_STATUS_STABLE
        reasons.append(SLO_STABLE_REASON)

    deduped = _dedupe_preserve_order(reasons)
    return _report(
        status=status,
        reason_code=deduped[0],
        reasons=deduped,
        latency_threshold_ms=threshold,
        max_state_flips=allowed_flips,
        samples=parsed,
        metadata={
            "min_sample_count": min_count,
            "evidence_only_no_runtime_change": True,
            "invalid_sample_count": invalid_count,
            "max_latency_ms": max_latency,
            "avg_latency_ms": avg_latency,
            "slo_state_flip_count": slo_flips,
            "cooldown_flip_count": cooldown_flips,
            "loop_mode_flip_count": loop_flips,
            "recovery_flip_count": recovery_flips,
        },
    )


def write_latency_slo_oscillation_evidence(report: LatencySloOscillationReport, path: str | Path) -> Path:
    """Write latency/SLO oscillation evidence."""

    target = Path(path).expanduser()
    write_json_atomic(target, report.to_payload())
    return target


def _report(
    *,
    status: str,
    reason_code: str,
    reasons: tuple[str, ...],
    latency_threshold_ms: float,
    max_state_flips: int,
    samples: tuple[LatencySloSample, ...],
    metadata: dict[str, Any] | None = None,
) -> LatencySloOscillationReport:
    valid = tuple(sample for sample in samples if sample.valid)
    latencies = tuple(sample.latency_ms for sample in valid if sample.latency_ms is not None)
    max_latency = max(latencies) if latencies else None
    avg_latency = round(sum(latencies) / len(latencies), 6) if latencies else None
    return LatencySloOscillationReport(
        schema_version=LATENCY_SLO_SCHEMA_VERSION,
        source=LATENCY_SLO_SOURCE,
        status=status,
        reason_code=reason_code,
        reasons=reasons,
        sample_count=len(samples),
        valid_sample_count=len(valid),
        max_latency_ms=max_latency,
        avg_latency_ms=avg_latency,
        latency_threshold_ms=latency_threshold_ms,
        slo_state_flip_count=_flip_count(sample.slo_state for sample in valid),
        cooldown_flip_count=_flip_count(sample.cooldown_state for sample in valid),
        loop_mode_flip_count=_flip_count(sample.loop_mode for sample in valid),
        recovery_flip_count=_flip_count(sample.recovery_state for sample in valid),
        max_state_flips=max_state_flips,
        samples=samples,
        metadata=dict(metadata or {}),
    )


def _extract_sample_items(value: Sequence[Mapping[str, Any] | Any] | Mapping[str, Any] | Any) -> tuple[Any, ...]:
    payload = _payload_or_none(value)
    if payload is not None:
        for key in ("samples", "latency_samples", "slo_samples", "events", "rows", "items"):
            nested = payload.get(key)
            if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
                return tuple(nested)
        return (payload,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()


def _parse_sample(index: int, value: Mapping[str, Any] | Any) -> LatencySloSample:
    payload = _payload_or_none(value)
    if payload is None:
        return LatencySloSample(index, None, "", "", "", "", False, INVALID_SAMPLE_REASON)
    latency = _first_non_negative_float(payload, _LATENCY_KEYS)
    if latency is None:
        return LatencySloSample(index, None, _text(payload, _SLO_KEYS), _text(payload, _COOLDOWN_KEYS), _text(payload, _LOOP_MODE_KEYS), _text(payload, _RECOVERY_KEYS), False, INVALID_SAMPLE_REASON)
    return LatencySloSample(
        index=index,
        latency_ms=latency,
        slo_state=_normalize_state(_text(payload, _SLO_KEYS)),
        cooldown_state=_normalize_state(_text(payload, _COOLDOWN_KEYS)),
        loop_mode=_normalize_state(_text(payload, _LOOP_MODE_KEYS)),
        recovery_state=_normalize_state(_text(payload, _RECOVERY_KEYS)),
        valid=True,
        reason_code=SLO_STABLE_REASON,
    )


def _payload_or_none(value: Mapping[str, Any] | Any | None) -> dict[str, Any] | None:
    if hasattr(value, "to_payload"):
        try:
            value = value.to_payload()
        except Exception:
            return None
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _first_non_negative_float(payload: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        if key not in payload:
            continue
        parsed = _finite_float_or_none(payload.get(key))
        if parsed is not None and parsed >= 0:
            return parsed
    return None


def _text(payload: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "unknown"


def _normalize_state(value: str) -> str:
    return str(value or "unknown").strip().lower().replace("-", "_").replace(" ", "_")


def _flip_count(values: Any) -> int:
    compact = [str(value) for value in values if str(value or "").strip()]
    if not compact:
        return 0
    flips = 0
    previous = compact[0]
    for current in compact[1:]:
        if current != previous:
            flips += 1
            previous = current
    return flips


def _finite_float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _positive_float_or_none(value: Any) -> float | None:
    out = _finite_float_or_none(value)
    if out is None or out <= 0:
        return None
    return out


def _non_negative_int_or_none(value: Any) -> int | None:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out >= 0 else None


def _positive_int_or_none(value: Any) -> int | None:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _dedupe_preserve_order(values: Any) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return tuple(out)


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload["read_only"] = True
    payload["append"] = False
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload[_LIVE_ACTION_KEY] = False
    payload[_BROKER_ACTION_KEY] = False


__all__ = [
    "COOLDOWN_THRASH_REASON",
    "DEFAULT_LATENCY_THRESHOLD_MS",
    "DEFAULT_MAX_STATE_FLIPS",
    "DEFAULT_MIN_SAMPLE_COUNT",
    "HIGH_LATENCY_REASON",
    "INVALID_CONFIG_REASON",
    "INVALID_SAMPLE_REASON",
    "LATENCY_SLO_SCHEMA_VERSION",
    "LATENCY_SLO_SOURCE",
    "LOOP_MODE_THRASH_REASON",
    "NO_SAMPLES_REASON",
    "RECOVERY_OSCILLATION_REASON",
    "SLO_STABLE_REASON",
    "SLO_STATE_FLAP_REASON",
    "SLO_STATUS_BLOCKED",
    "SLO_STATUS_DEGRADED",
    "SLO_STATUS_OSCILLATING",
    "SLO_STATUS_STABLE",
    "LatencySloOscillationReport",
    "LatencySloSample",
    "build_latency_slo_oscillation_report",
    "write_latency_slo_oscillation_evidence",
]
