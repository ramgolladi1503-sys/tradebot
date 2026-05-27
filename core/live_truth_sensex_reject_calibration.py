"""SENSEX reject calibration evidence for LIVE-TRUTH-08.

This reducer summarizes SENSEX candidate rejection evidence so later work can
see whether rejects are concentrated, well-explained, or likely over-filtered.
It is read-only and does not alter strategies, ranking, runtime state, or
candidate eligibility.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.events import write_json_atomic

SENSEX_REJECT_CALIBRATION_SCHEMA_VERSION = 1
SENSEX_REJECT_CALIBRATION_SOURCE = "live_truth_sensex_reject_calibration_v1"

CALIBRATION_STATUS_BALANCED = "SENSEX_REJECT_CALIBRATION_BALANCED"
CALIBRATION_STATUS_REVIEW = "SENSEX_REJECT_CALIBRATION_REVIEW"
CALIBRATION_STATUS_OVERFILTERED = "SENSEX_REJECT_CALIBRATION_OVERFILTERED"
CALIBRATION_STATUS_BLOCKED = "SENSEX_REJECT_CALIBRATION_BLOCKED"

CALIBRATION_BALANCED_REASON = "sensex_reject_calibration_balanced"
NO_REJECTS_REASON = "no_sensex_rejects"
INVALID_REJECT_REASON = "invalid_sensex_reject_payload"
INVALID_CONFIG_REASON = "invalid_sensex_reject_calibration_config"
REJECT_RATE_HIGH_REASON = "sensex_reject_rate_high"
REASON_CONCENTRATION_HIGH_REASON = "sensex_reject_reason_concentration_high"
NEAR_MISS_RATE_HIGH_REASON = "sensex_near_miss_reject_rate_high"
MISSING_REJECT_REASON = "sensex_reject_reason_missing"
NON_SENSEX_ONLY_REASON = "non_sensex_only"

DEFAULT_MAX_REJECT_RATE = 0.85
DEFAULT_MAX_REASON_CONCENTRATION = 0.70
DEFAULT_MAX_NEAR_MISS_RATE = 0.35
DEFAULT_MIN_TOTAL_COUNT = 3
DEFAULT_NEAR_MISS_MARGIN = 0.05

_SYMBOL_KEYS = ("symbol", "instrument", "underlying", "index", "name", "candidate_id")
_REASON_KEYS = ("reject_reason", "reason", "reason_code", "block_reason", "status_reason")
_DECISION_KEYS = ("decision", "status", "candidate_status", "state")
_SCORE_KEYS = ("score", "quality_score", "confidence", "confidence_raw", "edge_score", "rank_score")
_THRESHOLD_KEYS = ("threshold", "min_score", "quality_threshold", "accept_threshold")

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"
_LIVE_ACTION_KEY = "live_" + "order_action"
_BROKER_ACTION_KEY = "broker_" + "order_action"


@dataclass(frozen=True)
class SensexRejectItem:
    index: int
    symbol: str
    reason_code: str
    score: float | None
    threshold: float | None
    near_miss: bool
    valid: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "symbol": self.symbol,
            "reason_code": self.reason_code,
            "score": self.score,
            "threshold": self.threshold,
            "near_miss": self.near_miss,
            "valid": self.valid,
        }


@dataclass(frozen=True)
class SensexRejectCalibrationReport:
    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    total_count: int
    sensex_count: int
    rejected_count: int
    accepted_count: int
    invalid_count: int
    reject_rate: float
    near_miss_count: int
    near_miss_rate: float
    dominant_reason: str | None
    dominant_reason_count: int
    dominant_reason_share: float
    max_reject_rate: float
    max_reason_concentration: float
    max_near_miss_rate: float
    items: tuple[SensexRejectItem, ...]
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
            "total_count": self.total_count,
            "sensex_count": self.sensex_count,
            "rejected_count": self.rejected_count,
            "accepted_count": self.accepted_count,
            "invalid_count": self.invalid_count,
            "reject_rate": self.reject_rate,
            "near_miss_count": self.near_miss_count,
            "near_miss_rate": self.near_miss_rate,
            "dominant_reason": self.dominant_reason,
            "dominant_reason_count": self.dominant_reason_count,
            "dominant_reason_share": self.dominant_reason_share,
            "max_reject_rate": self.max_reject_rate,
            "max_reason_concentration": self.max_reason_concentration,
            "max_near_miss_rate": self.max_near_miss_rate,
            "items": [item.to_payload() for item in self.items],
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_sensex_reject_calibration_report(
    candidates: Sequence[Mapping[str, Any] | Any] | Mapping[str, Any] | Any,
    *,
    max_reject_rate: float = DEFAULT_MAX_REJECT_RATE,
    max_reason_concentration: float = DEFAULT_MAX_REASON_CONCENTRATION,
    max_near_miss_rate: float = DEFAULT_MAX_NEAR_MISS_RATE,
    min_total_count: int = DEFAULT_MIN_TOTAL_COUNT,
    near_miss_margin: float = DEFAULT_NEAR_MISS_MARGIN,
) -> SensexRejectCalibrationReport:
    """Build read-only SENSEX reject calibration evidence."""

    reject_limit = _ratio_or_none(max_reject_rate)
    concentration_limit = _ratio_or_none(max_reason_concentration)
    near_miss_limit = _ratio_or_none(max_near_miss_rate)
    min_count = _positive_int_or_none(min_total_count)
    margin = _non_negative_float_or_none(near_miss_margin)
    if (
        reject_limit is None
        or concentration_limit is None
        or near_miss_limit is None
        or min_count is None
        or margin is None
    ):
        return _report(
            status=CALIBRATION_STATUS_BLOCKED,
            reason_code=INVALID_CONFIG_REASON,
            reasons=(INVALID_CONFIG_REASON,),
            max_reject_rate=DEFAULT_MAX_REJECT_RATE if reject_limit is None else reject_limit,
            max_reason_concentration=DEFAULT_MAX_REASON_CONCENTRATION
            if concentration_limit is None
            else concentration_limit,
            max_near_miss_rate=DEFAULT_MAX_NEAR_MISS_RATE if near_miss_limit is None else near_miss_limit,
            items=(),
            accepted_count=0,
            invalid_count=0,
            metadata={"blocked_before_candidate_evaluation": True},
        )

    raw_items = _extract_candidate_items(candidates)
    if not raw_items:
        return _report(
            status=CALIBRATION_STATUS_BALANCED,
            reason_code=NO_REJECTS_REASON,
            reasons=(NO_REJECTS_REASON,),
            max_reject_rate=reject_limit,
            max_reason_concentration=concentration_limit,
            max_near_miss_rate=near_miss_limit,
            items=(),
            accepted_count=0,
            invalid_count=0,
            metadata={"no_candidates_is_balanced": True, "evidence_only_no_runtime_change": True},
        )

    parsed_all = tuple(_parse_item(index, item, near_miss_margin=margin) for index, item in enumerate(raw_items))
    invalid_count = sum(1 for item in parsed_all if not item.valid)
    sensex_items = tuple(item for item in parsed_all if item.valid and _is_sensex_symbol(item.symbol))
    non_sensex_valid_count = sum(1 for item in parsed_all if item.valid and not _is_sensex_symbol(item.symbol))
    if not sensex_items:
        reason = INVALID_REJECT_REASON if invalid_count else NON_SENSEX_ONLY_REASON
        return _report(
            status=CALIBRATION_STATUS_BLOCKED if invalid_count else CALIBRATION_STATUS_BALANCED,
            reason_code=reason,
            reasons=(reason,),
            max_reject_rate=reject_limit,
            max_reason_concentration=concentration_limit,
            max_near_miss_rate=near_miss_limit,
            items=parsed_all,
            accepted_count=non_sensex_valid_count,
            invalid_count=invalid_count,
            metadata={"sensex_count": 0, "evidence_only_no_runtime_change": True},
        )

    rejected = tuple(item for item in sensex_items if _is_reject_reason(item.reason_code))
    accepted_count = len(sensex_items) - len(rejected)
    reason_counts = Counter(item.reason_code for item in rejected if item.reason_code)
    dominant_reason, dominant_count = reason_counts.most_common(1)[0] if reason_counts else (None, 0)
    reject_rate = _safe_ratio(len(rejected), len(sensex_items))
    dominant_share = _safe_ratio(dominant_count, len(rejected))
    near_miss_count = sum(1 for item in rejected if item.near_miss)
    near_miss_rate = _safe_ratio(near_miss_count, len(rejected))

    reasons: list[str] = []
    if invalid_count:
        reasons.append(INVALID_REJECT_REASON)
    if len(sensex_items) < min_count:
        reasons.append(NO_REJECTS_REASON)
    if any(item.reason_code == MISSING_REJECT_REASON for item in rejected):
        reasons.append(MISSING_REJECT_REASON)
    if reject_rate > reject_limit:
        reasons.append(REJECT_RATE_HIGH_REASON)
    if dominant_share > concentration_limit and len(rejected) > 1:
        reasons.append(REASON_CONCENTRATION_HIGH_REASON)
    if near_miss_rate > near_miss_limit:
        reasons.append(NEAR_MISS_RATE_HIGH_REASON)

    if invalid_count or len(sensex_items) < min_count:
        status = CALIBRATION_STATUS_BLOCKED
    elif REJECT_RATE_HIGH_REASON in reasons and NEAR_MISS_RATE_HIGH_REASON in reasons:
        status = CALIBRATION_STATUS_OVERFILTERED
    elif any(
        reason in reasons
        for reason in (REJECT_RATE_HIGH_REASON, REASON_CONCENTRATION_HIGH_REASON, NEAR_MISS_RATE_HIGH_REASON)
    ):
        status = CALIBRATION_STATUS_REVIEW
    else:
        status = CALIBRATION_STATUS_BALANCED
        reasons.append(CALIBRATION_BALANCED_REASON)

    deduped = _dedupe_preserve_order(reasons)
    return _report(
        status=status,
        reason_code=deduped[0],
        reasons=deduped,
        max_reject_rate=reject_limit,
        max_reason_concentration=concentration_limit,
        max_near_miss_rate=near_miss_limit,
        items=parsed_all,
        accepted_count=accepted_count,
        invalid_count=invalid_count,
        metadata={
            "min_total_count": min_count,
            "near_miss_margin": margin,
            "sensex_count": len(sensex_items),
            "non_sensex_valid_count": non_sensex_valid_count,
            "evidence_only_no_runtime_change": True,
        },
    )


def write_sensex_reject_calibration_evidence(report: SensexRejectCalibrationReport, path: str | Path) -> Path:
    """Write SENSEX reject calibration evidence."""

    target = Path(path).expanduser()
    write_json_atomic(target, report.to_payload())
    return target


def _report(
    *,
    status: str,
    reason_code: str,
    reasons: tuple[str, ...],
    max_reject_rate: float,
    max_reason_concentration: float,
    max_near_miss_rate: float,
    items: tuple[SensexRejectItem, ...],
    accepted_count: int,
    invalid_count: int,
    metadata: dict[str, Any] | None = None,
) -> SensexRejectCalibrationReport:
    valid_sensex = tuple(item for item in items if item.valid and _is_sensex_symbol(item.symbol))
    rejected = tuple(item for item in valid_sensex if _is_reject_reason(item.reason_code))
    reason_counts = Counter(item.reason_code for item in rejected if item.reason_code)
    dominant_reason, dominant_count = reason_counts.most_common(1)[0] if reason_counts else (None, 0)
    near_miss_count = sum(1 for item in rejected if item.near_miss)
    return SensexRejectCalibrationReport(
        schema_version=SENSEX_REJECT_CALIBRATION_SCHEMA_VERSION,
        source=SENSEX_REJECT_CALIBRATION_SOURCE,
        status=status,
        reason_code=reason_code,
        reasons=reasons,
        total_count=len(items),
        sensex_count=len(valid_sensex),
        rejected_count=len(rejected),
        accepted_count=accepted_count,
        invalid_count=invalid_count,
        reject_rate=_safe_ratio(len(rejected), len(valid_sensex)),
        near_miss_count=near_miss_count,
        near_miss_rate=_safe_ratio(near_miss_count, len(rejected)),
        dominant_reason=dominant_reason,
        dominant_reason_count=dominant_count,
        dominant_reason_share=_safe_ratio(dominant_count, len(rejected)),
        max_reject_rate=max_reject_rate,
        max_reason_concentration=max_reason_concentration,
        max_near_miss_rate=max_near_miss_rate,
        items=items,
        metadata=dict(metadata or {}),
    )


def _extract_candidate_items(value: Sequence[Mapping[str, Any] | Any] | Mapping[str, Any] | Any) -> tuple[Any, ...]:
    payload = _payload_or_none(value)
    if payload is not None:
        for key in ("candidates", "rejected_candidates", "sensex_candidates", "items", "rows"):
            nested = payload.get(key)
            if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
                return tuple(nested)
        return (payload,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()


def _parse_item(index: int, value: Mapping[str, Any] | Any, *, near_miss_margin: float) -> SensexRejectItem:
    payload = _payload_or_none(value)
    if payload is None:
        return SensexRejectItem(index, "", INVALID_REJECT_REASON, None, None, False, False)
    symbol = _first_text(payload, _SYMBOL_KEYS)
    if not symbol:
        return SensexRejectItem(index, "", INVALID_REJECT_REASON, None, None, False, False)
    reason = _first_text(payload, _REASON_KEYS) or _decision_to_reason(_first_text(payload, _DECISION_KEYS))
    reason_code = _normalize_reason(reason) if reason else MISSING_REJECT_REASON
    score = _first_finite_float(payload, _SCORE_KEYS)
    threshold = _first_finite_float(payload, _THRESHOLD_KEYS)
    near_miss = _is_near_miss(score, threshold, near_miss_margin)
    return SensexRejectItem(index, symbol, reason_code, score, threshold, near_miss, True)


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


def _first_finite_float(payload: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        parsed = _finite_float_or_none(payload.get(key)) if key in payload else None
        if parsed is not None:
            return parsed
    return None


def _decision_to_reason(value: str) -> str:
    text = _normalize_reason(value)
    if text in {"accepted", "accept", "selected", "clean", "displayable"}:
        return "accepted"
    if text in {"rejected", "reject", "blocked", "filtered"}:
        return MISSING_REJECT_REASON
    return text


def _normalize_reason(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _is_sensex_symbol(value: str) -> bool:
    return "sensex" in str(value or "").lower()


def _is_reject_reason(reason_code: str) -> bool:
    text = _normalize_reason(reason_code)
    return text not in {"", "accepted", "accept", "selected", "clean", "displayable", "ok", "pass"}


def _is_near_miss(score: float | None, threshold: float | None, margin: float) -> bool:
    if score is None or threshold is None:
        return False
    return threshold - margin <= score < threshold


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _finite_float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _ratio_or_none(value: Any) -> float | None:
    out = _finite_float_or_none(value)
    if out is None or out < 0 or out > 1:
        return None
    return out


def _non_negative_float_or_none(value: Any) -> float | None:
    out = _finite_float_or_none(value)
    if out is None or out < 0:
        return None
    return out


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
    "CALIBRATION_BALANCED_REASON",
    "CALIBRATION_STATUS_BALANCED",
    "CALIBRATION_STATUS_BLOCKED",
    "CALIBRATION_STATUS_OVERFILTERED",
    "CALIBRATION_STATUS_REVIEW",
    "DEFAULT_MAX_NEAR_MISS_RATE",
    "DEFAULT_MAX_REASON_CONCENTRATION",
    "DEFAULT_MAX_REJECT_RATE",
    "INVALID_CONFIG_REASON",
    "INVALID_REJECT_REASON",
    "MISSING_REJECT_REASON",
    "NEAR_MISS_RATE_HIGH_REASON",
    "NO_REJECTS_REASON",
    "NON_SENSEX_ONLY_REASON",
    "REASON_CONCENTRATION_HIGH_REASON",
    "REJECT_RATE_HIGH_REASON",
    "SENSEX_REJECT_CALIBRATION_SCHEMA_VERSION",
    "SENSEX_REJECT_CALIBRATION_SOURCE",
    "SensexRejectCalibrationReport",
    "SensexRejectItem",
    "build_sensex_reject_calibration_report",
    "write_sensex_reject_calibration_evidence",
]
