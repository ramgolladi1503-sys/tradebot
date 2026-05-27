"""Strategy performance shadow fallback evidence for LIVE-TRUTH-10.

This reducer checks whether strategy performance evidence is being shadowed by
fallback, estimated, recovered, or otherwise low-trust performance sources. It
is read-only and does not change runtime, ranking, scoring, strategies, feeds,
lifecycle state, or execution behavior.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.events import write_json_atomic

STRATEGY_PERF_SHADOW_FALLBACK_SCHEMA_VERSION = 1
STRATEGY_PERF_SHADOW_FALLBACK_SOURCE = "live_truth_strategy_perf_shadow_fallback_v1"

PERF_STATUS_TRUSTED = "STRATEGY_PERF_SHADOW_FALLBACK_TRUSTED"
PERF_STATUS_REVIEW = "STRATEGY_PERF_SHADOW_FALLBACK_REVIEW"
PERF_STATUS_SHADOWED = "STRATEGY_PERF_SHADOW_FALLBACK_SHADOWED"
PERF_STATUS_BLOCKED = "STRATEGY_PERF_SHADOW_FALLBACK_BLOCKED"

TRUSTED_REASON = "strategy_perf_shadow_fallback_trusted"
NO_PERF_ROWS_REASON = "no_strategy_perf_rows"
INVALID_PERF_ROW_REASON = "invalid_strategy_perf_row"
INVALID_CONFIG_REASON = "invalid_strategy_perf_shadow_fallback_config"
MISSING_STRATEGY_REASON = "missing_strategy_name"
MISSING_TRUST_FIELD_REASON = "missing_strategy_perf_trust_field"
FALLBACK_RATE_HIGH_REASON = "strategy_perf_fallback_rate_high"
SHADOW_RATE_HIGH_REASON = "strategy_perf_shadow_rate_high"
ESTIMATED_RATE_HIGH_REASON = "strategy_perf_estimated_rate_high"
RECOVERED_RATE_HIGH_REASON = "strategy_perf_recovered_rate_high"
LOW_SAMPLE_SHADOW_REASON = "strategy_perf_low_sample_shadow"

DEFAULT_MAX_FALLBACK_RATE = 0.0
DEFAULT_MAX_SHADOW_RATE = 0.0
DEFAULT_MAX_ESTIMATED_RATE = 0.10
DEFAULT_MAX_RECOVERED_RATE = 0.20
DEFAULT_MIN_SAMPLE_COUNT = 3

_STRATEGY_KEYS = ("strategy", "strategy_name", "family", "strategy_family", "name")
_SAMPLE_KEYS = ("sample_count", "samples", "trade_count", "closed_count", "n", "count")
_FALLBACK_KEYS = (
    "fallback",
    "uses_fallback",
    "fallback_used",
    "is_fallback",
    "fallback_perf",
    "perf_fallback",
)
_SHADOW_KEYS = (
    "shadow_fallback",
    "shadowed_by_fallback",
    "shadow_perf",
    "shadowed",
    "is_shadowed",
)
_ESTIMATED_KEYS = (
    "estimated",
    "is_estimated",
    "estimated_perf",
    "fallback_estimated",
    "synthetic",
    "is_synthetic",
)
_RECOVERED_KEYS = (
    "recovered",
    "recovered_fallback",
    "fallback_recovered",
    "is_recovered",
    "recovered_perf",
)
_SOURCE_KEYS = ("source", "perf_source", "data_source", "evidence_source")
_REASON_KEYS = ("reason", "reason_code", "status_reason", "fallback_reason")

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"
_LIVE_ACTION_KEY = "live_" + "order_action"
_BROKER_ACTION_KEY = "broker_" + "order_action"


@dataclass(frozen=True)
class StrategyPerfShadowFallbackRow:
    index: int
    strategy: str
    sample_count: int
    fallback: bool
    shadow_fallback: bool
    estimated: bool
    recovered: bool
    trusted: bool
    valid: bool
    reason_code: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "strategy": self.strategy,
            "sample_count": self.sample_count,
            "fallback": self.fallback,
            "shadow_fallback": self.shadow_fallback,
            "estimated": self.estimated,
            "recovered": self.recovered,
            "trusted": self.trusted,
            "valid": self.valid,
            "reason_code": self.reason_code,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StrategyPerfShadowFallbackReport:
    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    row_count: int
    valid_row_count: int
    trusted_count: int
    fallback_count: int
    shadow_fallback_count: int
    estimated_count: int
    recovered_count: int
    low_sample_shadow_count: int
    fallback_rate: float
    shadow_fallback_rate: float
    estimated_rate: float
    recovered_rate: float
    max_fallback_rate: float
    max_shadow_rate: float
    max_estimated_rate: float
    max_recovered_rate: float
    min_sample_count: int
    rows: tuple[StrategyPerfShadowFallbackRow, ...]
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
            "row_count": self.row_count,
            "valid_row_count": self.valid_row_count,
            "trusted_count": self.trusted_count,
            "fallback_count": self.fallback_count,
            "shadow_fallback_count": self.shadow_fallback_count,
            "estimated_count": self.estimated_count,
            "recovered_count": self.recovered_count,
            "low_sample_shadow_count": self.low_sample_shadow_count,
            "fallback_rate": self.fallback_rate,
            "shadow_fallback_rate": self.shadow_fallback_rate,
            "estimated_rate": self.estimated_rate,
            "recovered_rate": self.recovered_rate,
            "max_fallback_rate": self.max_fallback_rate,
            "max_shadow_rate": self.max_shadow_rate,
            "max_estimated_rate": self.max_estimated_rate,
            "max_recovered_rate": self.max_recovered_rate,
            "min_sample_count": self.min_sample_count,
            "rows": [row.to_payload() for row in self.rows],
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_strategy_perf_shadow_fallback_report(
    perf_rows: Sequence[Mapping[str, Any] | Any] | Mapping[str, Any] | Any,
    *,
    max_fallback_rate: float = DEFAULT_MAX_FALLBACK_RATE,
    max_shadow_rate: float = DEFAULT_MAX_SHADOW_RATE,
    max_estimated_rate: float = DEFAULT_MAX_ESTIMATED_RATE,
    max_recovered_rate: float = DEFAULT_MAX_RECOVERED_RATE,
    min_sample_count: int = DEFAULT_MIN_SAMPLE_COUNT,
) -> StrategyPerfShadowFallbackReport:
    """Build read-only evidence over strategy-performance fallback shadowing."""

    fallback_limit = _ratio_or_none(max_fallback_rate)
    shadow_limit = _ratio_or_none(max_shadow_rate)
    estimated_limit = _ratio_or_none(max_estimated_rate)
    recovered_limit = _ratio_or_none(max_recovered_rate)
    min_samples = _positive_int_or_none(min_sample_count)
    if (
        fallback_limit is None
        or shadow_limit is None
        or estimated_limit is None
        or recovered_limit is None
        or min_samples is None
    ):
        return _report(
            status=PERF_STATUS_BLOCKED,
            reason_code=INVALID_CONFIG_REASON,
            reasons=(INVALID_CONFIG_REASON,),
            rows=(),
            max_fallback_rate=DEFAULT_MAX_FALLBACK_RATE if fallback_limit is None else fallback_limit,
            max_shadow_rate=DEFAULT_MAX_SHADOW_RATE if shadow_limit is None else shadow_limit,
            max_estimated_rate=DEFAULT_MAX_ESTIMATED_RATE if estimated_limit is None else estimated_limit,
            max_recovered_rate=DEFAULT_MAX_RECOVERED_RATE if recovered_limit is None else recovered_limit,
            min_sample_count=DEFAULT_MIN_SAMPLE_COUNT if min_samples is None else min_samples,
            metadata={"blocked_before_perf_evaluation": True},
        )

    raw_rows = _extract_perf_rows(perf_rows)
    if not raw_rows:
        return _report(
            status=PERF_STATUS_BLOCKED,
            reason_code=NO_PERF_ROWS_REASON,
            reasons=(NO_PERF_ROWS_REASON,),
            rows=(),
            max_fallback_rate=fallback_limit,
            max_shadow_rate=shadow_limit,
            max_estimated_rate=estimated_limit,
            max_recovered_rate=recovered_limit,
            min_sample_count=min_samples,
            metadata={"blocked_before_perf_evaluation": True, "evidence_only_no_runtime_change": True},
        )

    parsed = tuple(_parse_row(index, row, min_sample_count=min_samples) for index, row in enumerate(raw_rows))
    invalid = tuple(row for row in parsed if not row.valid)
    valid = tuple(row for row in parsed if row.valid)
    if not valid:
        return _report(
            status=PERF_STATUS_BLOCKED,
            reason_code=INVALID_PERF_ROW_REASON,
            reasons=(INVALID_PERF_ROW_REASON,),
            rows=parsed,
            max_fallback_rate=fallback_limit,
            max_shadow_rate=shadow_limit,
            max_estimated_rate=estimated_limit,
            max_recovered_rate=recovered_limit,
            min_sample_count=min_samples,
            metadata={"blocked_before_perf_evaluation": True, "evidence_only_no_runtime_change": True},
        )

    fallback_rate = _rate(sum(1 for row in valid if row.fallback), len(valid))
    shadow_rate = _rate(sum(1 for row in valid if row.shadow_fallback), len(valid))
    estimated_rate = _rate(sum(1 for row in valid if row.estimated), len(valid))
    recovered_rate = _rate(sum(1 for row in valid if row.recovered), len(valid))
    low_sample_shadow_count = sum(
        1
        for row in valid
        if row.sample_count < min_samples
        and (row.fallback or row.shadow_fallback or row.estimated or row.recovered)
    )

    reasons: list[str] = []
    if invalid:
        reasons.append(INVALID_PERF_ROW_REASON)
    if any(row.reason_code == MISSING_STRATEGY_REASON for row in parsed):
        reasons.append(MISSING_STRATEGY_REASON)
    if any(row.reason_code == MISSING_TRUST_FIELD_REASON for row in valid):
        reasons.append(MISSING_TRUST_FIELD_REASON)
    if fallback_rate > fallback_limit:
        reasons.append(FALLBACK_RATE_HIGH_REASON)
    if shadow_rate > shadow_limit:
        reasons.append(SHADOW_RATE_HIGH_REASON)
    if estimated_rate > estimated_limit:
        reasons.append(ESTIMATED_RATE_HIGH_REASON)
    if recovered_rate > recovered_limit:
        reasons.append(RECOVERED_RATE_HIGH_REASON)
    if low_sample_shadow_count:
        reasons.append(LOW_SAMPLE_SHADOW_REASON)

    if invalid:
        status = PERF_STATUS_BLOCKED
    elif fallback_rate > fallback_limit or shadow_rate > shadow_limit:
        status = PERF_STATUS_SHADOWED
    elif any(
        reason in reasons
        for reason in (
            MISSING_TRUST_FIELD_REASON,
            ESTIMATED_RATE_HIGH_REASON,
            RECOVERED_RATE_HIGH_REASON,
            LOW_SAMPLE_SHADOW_REASON,
        )
    ):
        status = PERF_STATUS_REVIEW
    else:
        status = PERF_STATUS_TRUSTED
        reasons.append(TRUSTED_REASON)

    deduped = _dedupe_preserve_order(reasons)
    return _report(
        status=status,
        reason_code=deduped[0],
        reasons=deduped,
        rows=parsed,
        max_fallback_rate=fallback_limit,
        max_shadow_rate=shadow_limit,
        max_estimated_rate=estimated_limit,
        max_recovered_rate=recovered_limit,
        min_sample_count=min_samples,
        metadata={
            "evidence_only_no_runtime_change": True,
            "valid_strategies": sorted(row.strategy for row in valid),
            "invalid_row_count": len(invalid),
        },
    )


def write_strategy_perf_shadow_fallback_evidence(
    report: StrategyPerfShadowFallbackReport,
    path: str | Path,
) -> Path:
    """Write strategy-performance fallback-shadow evidence."""

    target = Path(path).expanduser()
    write_json_atomic(target, report.to_payload())
    return target


def _report(
    *,
    status: str,
    reason_code: str,
    reasons: tuple[str, ...],
    rows: tuple[StrategyPerfShadowFallbackRow, ...],
    max_fallback_rate: float,
    max_shadow_rate: float,
    max_estimated_rate: float,
    max_recovered_rate: float,
    min_sample_count: int,
    metadata: dict[str, Any] | None = None,
) -> StrategyPerfShadowFallbackReport:
    valid = tuple(row for row in rows if row.valid)
    fallback_count = sum(1 for row in valid if row.fallback)
    shadow_count = sum(1 for row in valid if row.shadow_fallback)
    estimated_count = sum(1 for row in valid if row.estimated)
    recovered_count = sum(1 for row in valid if row.recovered)
    low_sample_shadow_count = sum(
        1
        for row in valid
        if row.sample_count < min_sample_count
        and (row.fallback or row.shadow_fallback or row.estimated or row.recovered)
    )
    return StrategyPerfShadowFallbackReport(
        schema_version=STRATEGY_PERF_SHADOW_FALLBACK_SCHEMA_VERSION,
        source=STRATEGY_PERF_SHADOW_FALLBACK_SOURCE,
        status=status,
        reason_code=reason_code,
        reasons=reasons,
        row_count=len(rows),
        valid_row_count=len(valid),
        trusted_count=sum(1 for row in valid if row.trusted),
        fallback_count=fallback_count,
        shadow_fallback_count=shadow_count,
        estimated_count=estimated_count,
        recovered_count=recovered_count,
        low_sample_shadow_count=low_sample_shadow_count,
        fallback_rate=_rate(fallback_count, len(valid)),
        shadow_fallback_rate=_rate(shadow_count, len(valid)),
        estimated_rate=_rate(estimated_count, len(valid)),
        recovered_rate=_rate(recovered_count, len(valid)),
        max_fallback_rate=max_fallback_rate,
        max_shadow_rate=max_shadow_rate,
        max_estimated_rate=max_estimated_rate,
        max_recovered_rate=max_recovered_rate,
        min_sample_count=min_sample_count,
        rows=rows,
        metadata=dict(metadata or {}),
    )


def _extract_perf_rows(value: Sequence[Mapping[str, Any] | Any] | Mapping[str, Any] | Any) -> tuple[Any, ...]:
    payload = _payload_or_none(value)
    if payload is not None:
        for key in (
            "strategy_perf",
            "strategy_performance",
            "performance_rows",
            "perf_rows",
            "strategies",
            "rows",
            "items",
        ):
            nested = payload.get(key)
            if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
                return tuple(nested)
            if isinstance(nested, Mapping):
                return tuple(nested.values())
        return (payload,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()


def _parse_row(index: int, value: Mapping[str, Any] | Any, *, min_sample_count: int) -> StrategyPerfShadowFallbackRow:
    payload = _payload_or_none(value)
    if payload is None:
        return StrategyPerfShadowFallbackRow(index, "", 0, False, False, False, False, False, False, INVALID_PERF_ROW_REASON, "")

    strategy = _first_text(payload, _STRATEGY_KEYS)
    if not strategy:
        return StrategyPerfShadowFallbackRow(index, "", 0, False, False, False, False, False, False, MISSING_STRATEGY_REASON, _source(payload))

    sample_count = _first_non_negative_int(payload, _SAMPLE_KEYS) or 0
    fallback = _flag(payload, _FALLBACK_KEYS) or _source_has_any(payload, ("fallback",))
    shadow = _flag(payload, _SHADOW_KEYS) or _source_has_any(payload, ("shadow", "fallback_shadow"))
    estimated = _flag(payload, _ESTIMATED_KEYS) or _source_has_any(payload, ("estimated", "synthetic"))
    recovered = _flag(payload, _RECOVERED_KEYS) or _source_has_any(payload, ("recovered", "recovered_fallback"))
    has_trust_field = _has_any_key(payload, (*_FALLBACK_KEYS, *_SHADOW_KEYS, *_ESTIMATED_KEYS, *_RECOVERED_KEYS, *_SOURCE_KEYS))
    trusted = not (fallback or shadow or estimated or recovered)
    reason = _first_text(payload, _REASON_KEYS)
    reason_code = _normalize_reason(reason) if reason else TRUSTED_REASON
    if not has_trust_field:
        reason_code = MISSING_TRUST_FIELD_REASON
    elif sample_count < min_sample_count and not trusted:
        reason_code = LOW_SAMPLE_SHADOW_REASON
    elif not trusted and reason_code == TRUSTED_REASON:
        reason_code = "fallback_shadow_marker_present"

    return StrategyPerfShadowFallbackRow(
        index=index,
        strategy=strategy,
        sample_count=sample_count,
        fallback=fallback,
        shadow_fallback=shadow,
        estimated=estimated,
        recovered=recovered,
        trusted=trusted,
        valid=True,
        reason_code=reason_code,
        source=_source(payload),
        metadata={"has_trust_field": has_trust_field},
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


def _first_text(payload: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _source(payload: Mapping[str, Any]) -> str:
    return _first_text(payload, _SOURCE_KEYS)


def _first_non_negative_int(payload: Mapping[str, Any], keys: Sequence[str]) -> int | None:
    for key in keys:
        if key not in payload:
            continue
        try:
            parsed = int(payload.get(key))
        except (TypeError, ValueError):
            continue
        if parsed >= 0:
            return parsed
    return None


def _flag(payload: Mapping[str, Any], keys: Sequence[str]) -> bool:
    for key in keys:
        if key not in payload:
            continue
        parsed = _bool_or_none(payload.get(key))
        if parsed is not None:
            return parsed
    return False


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "fallback", "shadow", "estimated", "synthetic", "recovered"}:
        return True
    if text in {"false", "0", "no", "n", "trusted", "real", "actual", "none"}:
        return False
    return None


def _source_has_any(payload: Mapping[str, Any], markers: Sequence[str]) -> bool:
    source_text = " ".join(str(payload.get(key) or "") for key in (*_SOURCE_KEYS, *_REASON_KEYS)).lower()
    return any(marker in source_text for marker in markers)


def _has_any_key(payload: Mapping[str, Any], keys: Sequence[str]) -> bool:
    return any(key in payload for key in keys)


def _normalize_reason(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _ratio_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out) or out < 0.0 or out > 1.0:
        return None
    return out


def _positive_int_or_none(value: Any) -> int | None:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 6)


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
    "DEFAULT_MAX_ESTIMATED_RATE",
    "DEFAULT_MAX_FALLBACK_RATE",
    "DEFAULT_MAX_RECOVERED_RATE",
    "DEFAULT_MAX_SHADOW_RATE",
    "DEFAULT_MIN_SAMPLE_COUNT",
    "ESTIMATED_RATE_HIGH_REASON",
    "FALLBACK_RATE_HIGH_REASON",
    "INVALID_CONFIG_REASON",
    "INVALID_PERF_ROW_REASON",
    "LOW_SAMPLE_SHADOW_REASON",
    "MISSING_STRATEGY_REASON",
    "MISSING_TRUST_FIELD_REASON",
    "NO_PERF_ROWS_REASON",
    "PERF_STATUS_BLOCKED",
    "PERF_STATUS_REVIEW",
    "PERF_STATUS_SHADOWED",
    "PERF_STATUS_TRUSTED",
    "RECOVERED_RATE_HIGH_REASON",
    "SHADOW_RATE_HIGH_REASON",
    "STRATEGY_PERF_SHADOW_FALLBACK_SCHEMA_VERSION",
    "STRATEGY_PERF_SHADOW_FALLBACK_SOURCE",
    "StrategyPerfShadowFallbackReport",
    "StrategyPerfShadowFallbackRow",
    "TRUSTED_REASON",
    "build_strategy_perf_shadow_fallback_report",
    "write_strategy_perf_shadow_fallback_evidence",
]
