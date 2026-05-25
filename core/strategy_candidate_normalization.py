"""Read-only candidate normalization and deduplication contract for EDGE-70."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.strategy_candidate_pool import StrategyCandidatePoolReport, StrategyRegistryCandidate

STRATEGY_CANDIDATE_NORMALIZATION_SCHEMA_VERSION = 1
STRATEGY_CANDIDATE_NORMALIZATION_SOURCE = "strategy_candidate_normalization_v1"

NORMALIZATION_STATUS_INCLUDED = "INCLUDED"
NORMALIZATION_STATUS_DUPLICATE_REJECTED = "DUPLICATE_REJECTED"
NORMALIZATION_STATUS_BLOCKED = "BLOCKED"

NORMALIZATION_EMPTY_INPUT = "strategy_candidate_normalization_empty_input"
NORMALIZATION_POOL_INVALID = "strategy_candidate_normalization_pool_invalid"
NORMALIZATION_MISSING_FIELD = "strategy_candidate_normalization_missing_field"
NORMALIZATION_DUPLICATE_CANDIDATE = "strategy_candidate_normalization_duplicate_candidate"
NORMALIZATION_INVALID_CANDIDATE = "strategy_candidate_normalization_invalid_candidate"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class NormalizedStrategyCandidate:
    canonical_candidate_id: str
    original_candidate_id: str
    strategy_id: str
    instrument: str
    regime: str
    direction: str
    family: str
    module_path: str
    callable_name: str
    eligibility_status: str
    required_evidence_keys: tuple[str, ...]
    normalization_status: str = NORMALIZATION_STATUS_INCLUDED
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = STRATEGY_CANDIDATE_NORMALIZATION_SOURCE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "canonical_candidate_id": self.canonical_candidate_id,
            "original_candidate_id": self.original_candidate_id,
            "strategy_id": self.strategy_id,
            "instrument": self.instrument,
            "regime": self.regime,
            "direction": self.direction,
            "family": self.family,
            "module_path": self.module_path,
            "callable_name": self.callable_name,
            "eligibility_status": self.eligibility_status,
            "required_evidence_keys": list(self.required_evidence_keys),
            "normalization_status": self.normalization_status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


@dataclass(frozen=True)
class CandidateNormalizationRejection:
    candidate_id: str
    canonical_candidate_id: str
    status: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = STRATEGY_CANDIDATE_NORMALIZATION_SOURCE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "candidate_id": self.candidate_id,
            "canonical_candidate_id": self.canonical_candidate_id,
            "status": self.status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


@dataclass(frozen=True)
class CandidateNormalizationReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    normalized_candidates: tuple[NormalizedStrategyCandidate, ...]
    rejected_candidates: tuple[CandidateNormalizationRejection, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def valid(self) -> bool:
        return not self.blockers

    @property
    def canonical_candidate_ids(self) -> tuple[str, ...]:
        return tuple(candidate.canonical_candidate_id for candidate in self.normalized_candidates)

    def get(self, canonical_candidate_id: str) -> NormalizedStrategyCandidate | None:
        wanted = _candidate_key(canonical_candidate_id)
        for candidate in self.normalized_candidates:
            if candidate.canonical_candidate_id == wanted:
                return candidate
        return None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "normalized_count": len(self.normalized_candidates),
            "rejected_count": len(self.rejected_candidates),
            "canonical_candidate_ids": list(self.canonical_candidate_ids),
            "normalized_candidates": [candidate.to_payload() for candidate in self.normalized_candidates],
            "rejected_candidates": [candidate.to_payload() for candidate in self.rejected_candidates],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def normalize_strategy_candidates(
    candidates: StrategyCandidatePoolReport | Iterable[StrategyRegistryCandidate | Mapping[str, Any]],
    *,
    source: str = STRATEGY_CANDIDATE_NORMALIZATION_SOURCE,
) -> CandidateNormalizationReport:
    """Normalize and deduplicate candidate metadata without ranking or scoring."""

    pool_invalid = isinstance(candidates, StrategyCandidatePoolReport) and not candidates.valid
    raw_candidates = _resolve_candidates(candidates)
    report_blockers = _dedupe_sorted(
        (
            *((NORMALIZATION_EMPTY_INPUT,) if not raw_candidates else ()),
            *((NORMALIZATION_POOL_INVALID,) if pool_invalid else ()),
        )
    )
    if report_blockers:
        return CandidateNormalizationReport(
            schema_version=STRATEGY_CANDIDATE_NORMALIZATION_SCHEMA_VERSION,
            read_only=True,
            append=False,
            source=source,
            normalized_candidates=(),
            rejected_candidates=tuple(
                _reject_invalid(candidate, NORMALIZATION_POOL_INVALID if pool_invalid else NORMALIZATION_EMPTY_INPUT)
                for candidate in raw_candidates
            ),
            blockers=report_blockers,
            warnings=(),
            metadata=_metadata(),
        )

    seen: set[str] = set()
    normalized: list[NormalizedStrategyCandidate] = []
    rejected: list[CandidateNormalizationRejection] = []
    for raw in raw_candidates:
        candidate = _coerce_candidate(raw)
        blockers = _candidate_blockers(candidate)
        canonical_id = _canonical_id(candidate)
        if blockers:
            rejected.append(_reject_candidate(candidate, canonical_id, NORMALIZATION_STATUS_BLOCKED, blockers))
            continue
        if canonical_id in seen:
            rejected.append(
                _reject_candidate(
                    candidate,
                    canonical_id,
                    NORMALIZATION_STATUS_DUPLICATE_REJECTED,
                    (NORMALIZATION_DUPLICATE_CANDIDATE,),
                )
            )
            continue
        seen.add(canonical_id)
        normalized.append(_normalize_candidate(candidate, canonical_id))

    warnings = _dedupe_sorted(
        (
            *((NORMALIZATION_DUPLICATE_CANDIDATE,) if any(
                NORMALIZATION_DUPLICATE_CANDIDATE in item.blockers for item in rejected
            ) else ()),
            *((NORMALIZATION_INVALID_CANDIDATE,) if any(
                NORMALIZATION_INVALID_CANDIDATE in item.blockers or NORMALIZATION_MISSING_FIELD in item.blockers for item in rejected
            ) else ()),
        )
    )
    return CandidateNormalizationReport(
        schema_version=STRATEGY_CANDIDATE_NORMALIZATION_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        normalized_candidates=tuple(sorted(normalized, key=lambda item: item.canonical_candidate_id)),
        rejected_candidates=tuple(rejected),
        blockers=(),
        warnings=warnings,
        metadata=_metadata(),
    )


def _resolve_candidates(
    candidates: StrategyCandidatePoolReport | Iterable[StrategyRegistryCandidate | Mapping[str, Any]],
) -> tuple[StrategyRegistryCandidate | Mapping[str, Any], ...]:
    if isinstance(candidates, StrategyCandidatePoolReport):
        return tuple(candidates.candidates)
    if candidates is None:
        return ()
    return tuple(candidates)


def _normalize_candidate(candidate: StrategyRegistryCandidate, canonical_id: str) -> NormalizedStrategyCandidate:
    return NormalizedStrategyCandidate(
        canonical_candidate_id=canonical_id,
        original_candidate_id=_candidate_key(candidate.candidate_id),
        strategy_id=_normalize_id(candidate.strategy_id),
        instrument=_normalize_symbol(candidate.instrument),
        regime=_normalize_symbol(candidate.regime),
        direction=_normalize_symbol(candidate.direction),
        family=_normalize_symbol(candidate.family),
        module_path=str(candidate.module_path or "").strip(),
        callable_name=str(candidate.callable_name or "").strip(),
        eligibility_status=_normalize_symbol(candidate.eligibility_status),
        required_evidence_keys=_lower_tuple(candidate.required_evidence_keys),
        metadata={
            "original_source": candidate.source,
            "normalization_key_fields": ["strategy_id", "instrument", "direction", "regime"],
        },
    )


def _coerce_candidate(candidate: StrategyRegistryCandidate | Mapping[str, Any]) -> StrategyRegistryCandidate:
    if isinstance(candidate, StrategyRegistryCandidate):
        return candidate
    if not isinstance(candidate, Mapping):
        return StrategyRegistryCandidate(
            candidate_id="",
            strategy_id="",
            instrument="",
            regime="",
            direction="",
            family="",
            module_path="",
            callable_name="",
            eligibility_status="",
            required_evidence_keys=(),
            metadata={"coercion_error": type(candidate).__name__},
        )
    return StrategyRegistryCandidate(
        candidate_id=str(candidate.get("candidate_id") or ""),
        strategy_id=str(candidate.get("strategy_id") or ""),
        instrument=str(candidate.get("instrument") or ""),
        regime=str(candidate.get("regime") or ""),
        direction=str(candidate.get("direction") or ""),
        family=str(candidate.get("family") or ""),
        module_path=str(candidate.get("module_path") or ""),
        callable_name=str(candidate.get("callable_name") or ""),
        eligibility_status=str(candidate.get("eligibility_status") or ""),
        required_evidence_keys=_lower_tuple(candidate.get("required_evidence_keys") or ()),
        metadata=_safe_dict(candidate.get("metadata")),
    )


def _reject_invalid(candidate: StrategyRegistryCandidate | Mapping[str, Any], blocker: str) -> CandidateNormalizationRejection:
    coerced = _coerce_candidate(candidate)
    return _reject_candidate(coerced, _canonical_id(coerced), NORMALIZATION_STATUS_BLOCKED, (blocker,))


def _reject_candidate(
    candidate: StrategyRegistryCandidate,
    canonical_id: str,
    status: str,
    blockers: tuple[str, ...],
) -> CandidateNormalizationRejection:
    return CandidateNormalizationRejection(
        candidate_id=_candidate_key(candidate.candidate_id),
        canonical_candidate_id=canonical_id,
        status=status,
        blockers=_dedupe_sorted(blockers),
        metadata={
            "strategy_id": _normalize_id(candidate.strategy_id),
            "instrument": _normalize_symbol(candidate.instrument),
            "direction": _normalize_symbol(candidate.direction),
            "regime": _normalize_symbol(candidate.regime),
        },
    )


def _candidate_blockers(candidate: StrategyRegistryCandidate) -> tuple[str, ...]:
    blockers: list[str] = []
    required = {
        "candidate_id": candidate.candidate_id,
        "strategy_id": candidate.strategy_id,
        "instrument": candidate.instrument,
        "regime": candidate.regime,
        "direction": candidate.direction,
        "family": candidate.family,
        "module_path": candidate.module_path,
        "callable_name": candidate.callable_name,
        "eligibility_status": candidate.eligibility_status,
    }
    for value in required.values():
        if not str(value or "").strip():
            blockers.append(NORMALIZATION_MISSING_FIELD)
            break
    if not candidate.required_evidence_keys:
        blockers.append(NORMALIZATION_MISSING_FIELD)
    if not _canonical_id(candidate):
        blockers.append(NORMALIZATION_INVALID_CANDIDATE)
    return _dedupe_sorted(blockers)


def _canonical_id(candidate: StrategyRegistryCandidate) -> str:
    parts = (
        _normalize_id(candidate.strategy_id),
        _normalize_symbol(candidate.instrument).lower(),
        _normalize_symbol(candidate.direction).lower(),
        _normalize_symbol(candidate.regime).lower(),
    )
    if not all(parts):
        return ""
    return _candidate_key(":".join(parts))


def _metadata() -> dict[str, Any]:
    return {
        "model": STRATEGY_CANDIDATE_NORMALIZATION_SOURCE,
        "scope": "candidate_normalization_dedup_no_runtime_wiring_no_ranking",
        "does_not_import_strategy_modules": True,
        "does_not_execute_strategy_callables": True,
        "does_not_rank_candidates": True,
        "does_not_score_edge": True,
    }


def _candidate_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _normalize_id(value: Any) -> str:
    return _candidate_key(value)


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _lower_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, Iterable):
        values = tuple(value)
    else:
        values = (value,)
    return tuple(str(item).strip().lower() for item in values if str(item).strip())


def _safe_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _safe_json_value(item) for key, item in value.items()}


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _dedupe_sorted(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


__all__ = [
    "CandidateNormalizationRejection",
    "CandidateNormalizationReport",
    "NORMALIZATION_DUPLICATE_CANDIDATE",
    "NORMALIZATION_EMPTY_INPUT",
    "NORMALIZATION_INVALID_CANDIDATE",
    "NORMALIZATION_MISSING_FIELD",
    "NORMALIZATION_POOL_INVALID",
    "NORMALIZATION_STATUS_BLOCKED",
    "NORMALIZATION_STATUS_DUPLICATE_REJECTED",
    "NORMALIZATION_STATUS_INCLUDED",
    "NormalizedStrategyCandidate",
    "STRATEGY_CANDIDATE_NORMALIZATION_SCHEMA_VERSION",
    "STRATEGY_CANDIDATE_NORMALIZATION_SOURCE",
    "normalize_strategy_candidates",
]
