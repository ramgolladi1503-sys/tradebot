"""Read-only candidate classification contract for EDGE-71."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.regime_state import (
    REGIME_BEAR_TREND,
    REGIME_BULL_TREND,
    REGIME_HIGH_VOLATILITY,
    REGIME_MIXED_UNCERTAIN,
    REGIME_OPENING_DISCOVERY,
    REGIME_RANGE_BOUND,
)
from core.strategy_candidate_normalization import (
    CandidateNormalizationReport,
    NormalizedStrategyCandidate,
)
from core.strategy_spec import (
    DIRECTION_BUY_CALL,
    DIRECTION_BUY_PUT,
    DIRECTION_CALL,
    DIRECTION_NEUTRAL,
    DIRECTION_PUT,
    FAMILY_BREAKOUT,
    FAMILY_ENSEMBLE,
    FAMILY_EVENT,
    FAMILY_EXPIRY,
    FAMILY_MEAN_REVERSION,
    FAMILY_VWAP,
)

STRATEGY_CANDIDATE_CLASSIFICATION_SCHEMA_VERSION = 1
STRATEGY_CANDIDATE_CLASSIFICATION_SOURCE = "strategy_candidate_classification_v1"

CLASSIFICATION_EMPTY_INPUT = "strategy_candidate_classification_empty_input"
CLASSIFICATION_NORMALIZATION_INVALID = "strategy_candidate_classification_normalization_invalid"
CLASSIFICATION_MISSING_FIELD = "strategy_candidate_classification_missing_field"
CLASSIFICATION_UNKNOWN_DIRECTION = "strategy_candidate_classification_unknown_direction"
CLASSIFICATION_UNKNOWN_REGIME = "strategy_candidate_classification_unknown_regime"
CLASSIFICATION_UNKNOWN_FAMILY = "strategy_candidate_classification_unknown_family"
CLASSIFICATION_EVIDENCE_INCOMPLETE = "strategy_candidate_classification_evidence_incomplete"

DIRECTION_CLASS_CALL_BIAS = "CALL_BIAS"
DIRECTION_CLASS_PUT_BIAS = "PUT_BIAS"
DIRECTION_CLASS_NEUTRAL = "NEUTRAL"
DIRECTION_CLASS_UNKNOWN = "UNKNOWN_DIRECTION"

REGIME_CLASS_TREND = "TREND"
REGIME_CLASS_RANGE = "RANGE"
REGIME_CLASS_VOLATILITY = "VOLATILITY"
REGIME_CLASS_OPENING_DISCOVERY = "OPENING_DISCOVERY"
REGIME_CLASS_MIXED = "MIXED"
REGIME_CLASS_UNKNOWN = "UNKNOWN_REGIME"

FAMILY_CLASS_BREAKOUT = "BREAKOUT"
FAMILY_CLASS_VWAP = "VWAP"
FAMILY_CLASS_MEAN_REVERSION = "MEAN_REVERSION"
FAMILY_CLASS_EXPIRY = "EXPIRY"
FAMILY_CLASS_ENSEMBLE = "ENSEMBLE"
FAMILY_CLASS_EVENT = "EVENT"
FAMILY_CLASS_UNKNOWN = "UNKNOWN_FAMILY"

INSTRUMENT_CLASS_INDEX = "INDEX"
INSTRUMENT_CLASS_UNKNOWN = "UNKNOWN_INSTRUMENT"

EVIDENCE_CLASS_CORE_COMPLETE = "CORE_EVIDENCE_COMPLETE"
EVIDENCE_CLASS_INCOMPLETE = "CORE_EVIDENCE_INCOMPLETE"

_CORE_EVIDENCE_KEYS = ("market_state", "regime_state", "feed_health_truth", "quote_truth")
_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class ClassifiedStrategyCandidate:
    canonical_candidate_id: str
    strategy_id: str
    instrument: str
    regime: str
    direction: str
    family: str
    direction_class: str
    regime_class: str
    family_class: str
    instrument_class: str
    evidence_class: str
    labels: tuple[str, ...]
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = STRATEGY_CANDIDATE_CLASSIFICATION_SOURCE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def valid(self) -> bool:
        return not self.blockers

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "canonical_candidate_id": self.canonical_candidate_id,
            "strategy_id": self.strategy_id,
            "instrument": self.instrument,
            "regime": self.regime,
            "direction": self.direction,
            "family": self.family,
            "direction_class": self.direction_class,
            "regime_class": self.regime_class,
            "family_class": self.family_class,
            "instrument_class": self.instrument_class,
            "evidence_class": self.evidence_class,
            "labels": list(self.labels),
            "valid": self.valid,
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
class CandidateClassificationReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    classified_candidates: tuple[ClassifiedStrategyCandidate, ...]
    blocked_candidates: tuple[ClassifiedStrategyCandidate, ...]
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
        return tuple(candidate.canonical_candidate_id for candidate in self.classified_candidates)

    def get(self, canonical_candidate_id: str) -> ClassifiedStrategyCandidate | None:
        wanted = _candidate_key(canonical_candidate_id)
        for candidate in (*self.classified_candidates, *self.blocked_candidates):
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
            "classified_count": len(self.classified_candidates),
            "blocked_count": len(self.blocked_candidates),
            "canonical_candidate_ids": list(self.canonical_candidate_ids),
            "classified_candidates": [candidate.to_payload() for candidate in self.classified_candidates],
            "blocked_candidates": [candidate.to_payload() for candidate in self.blocked_candidates],
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


def classify_strategy_candidates(
    candidates: CandidateNormalizationReport | Iterable[NormalizedStrategyCandidate | Mapping[str, Any]],
    *,
    source: str = STRATEGY_CANDIDATE_CLASSIFICATION_SOURCE,
) -> CandidateClassificationReport:
    """Classify normalized candidate metadata without ranking or scoring."""

    normalization_invalid = isinstance(candidates, CandidateNormalizationReport) and not candidates.valid
    raw_candidates = _resolve_candidates(candidates)
    report_blockers = _dedupe_sorted(
        (
            *((CLASSIFICATION_EMPTY_INPUT,) if not raw_candidates else ()),
            *((CLASSIFICATION_NORMALIZATION_INVALID,) if normalization_invalid else ()),
        )
    )
    if report_blockers:
        return CandidateClassificationReport(
            schema_version=STRATEGY_CANDIDATE_CLASSIFICATION_SCHEMA_VERSION,
            read_only=True,
            append=False,
            source=source,
            classified_candidates=(),
            blocked_candidates=tuple(
                _classify_candidate(_coerce_candidate(candidate), forced_blockers=report_blockers)
                for candidate in raw_candidates
            ),
            blockers=report_blockers,
            warnings=(),
            metadata=_metadata(),
        )

    classified: list[ClassifiedStrategyCandidate] = []
    blocked: list[ClassifiedStrategyCandidate] = []
    for raw in raw_candidates:
        result = _classify_candidate(_coerce_candidate(raw))
        if result.valid:
            classified.append(result)
        else:
            blocked.append(result)

    warnings = _dedupe_sorted(
        warning
        for candidate in (*classified, *blocked)
        for warning in candidate.warnings
    )
    return CandidateClassificationReport(
        schema_version=STRATEGY_CANDIDATE_CLASSIFICATION_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        classified_candidates=tuple(sorted(classified, key=lambda item: item.canonical_candidate_id)),
        blocked_candidates=tuple(sorted(blocked, key=lambda item: item.canonical_candidate_id)),
        blockers=(),
        warnings=warnings,
        metadata=_metadata(),
    )


def _resolve_candidates(
    candidates: CandidateNormalizationReport | Iterable[NormalizedStrategyCandidate | Mapping[str, Any]],
) -> tuple[NormalizedStrategyCandidate | Mapping[str, Any], ...]:
    if isinstance(candidates, CandidateNormalizationReport):
        return tuple(candidates.normalized_candidates)
    if candidates is None:
        return ()
    return tuple(candidates)


def _classify_candidate(
    candidate: NormalizedStrategyCandidate,
    *,
    forced_blockers: Iterable[str] = (),
) -> ClassifiedStrategyCandidate:
    blockers = _dedupe_sorted((*_candidate_blockers(candidate), *forced_blockers))
    direction_class, direction_warnings = _classify_direction(candidate.direction)
    regime_class, regime_warnings = _classify_regime(candidate.regime)
    family_class, family_warnings = _classify_family(candidate.family)
    instrument_class = _classify_instrument(candidate.instrument)
    evidence_class, evidence_warnings = _classify_evidence(candidate.required_evidence_keys)
    warnings = _dedupe_sorted((*direction_warnings, *regime_warnings, *family_warnings, *evidence_warnings))
    labels = _dedupe_sorted(
        (
            direction_class,
            regime_class,
            family_class,
            instrument_class,
            evidence_class,
        )
    )
    return ClassifiedStrategyCandidate(
        canonical_candidate_id=_candidate_key(candidate.canonical_candidate_id),
        strategy_id=_candidate_key(candidate.strategy_id),
        instrument=_upper_key(candidate.instrument),
        regime=_upper_key(candidate.regime),
        direction=_upper_key(candidate.direction),
        family=_upper_key(candidate.family),
        direction_class=direction_class,
        regime_class=regime_class,
        family_class=family_class,
        instrument_class=instrument_class,
        evidence_class=evidence_class,
        labels=labels,
        blockers=blockers,
        warnings=warnings,
        metadata={
            "classification_key_fields": ["direction", "regime", "family", "instrument", "required_evidence_keys"],
            "source_candidate_source": candidate.source,
        },
    )


def _coerce_candidate(candidate: NormalizedStrategyCandidate | Mapping[str, Any]) -> NormalizedStrategyCandidate:
    if isinstance(candidate, NormalizedStrategyCandidate):
        return candidate
    if not isinstance(candidate, Mapping):
        return NormalizedStrategyCandidate(
            canonical_candidate_id="",
            original_candidate_id="",
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
    return NormalizedStrategyCandidate(
        canonical_candidate_id=str(candidate.get("canonical_candidate_id") or ""),
        original_candidate_id=str(candidate.get("original_candidate_id") or candidate.get("candidate_id") or ""),
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


def _candidate_blockers(candidate: NormalizedStrategyCandidate) -> tuple[str, ...]:
    required = (
        candidate.canonical_candidate_id,
        candidate.strategy_id,
        candidate.instrument,
        candidate.regime,
        candidate.direction,
        candidate.family,
    )
    if not all(str(value or "").strip() for value in required):
        return (CLASSIFICATION_MISSING_FIELD,)
    return ()


def _classify_direction(direction: str) -> tuple[str, tuple[str, ...]]:
    normalized = _upper_key(direction)
    if normalized in {DIRECTION_BUY_CALL, DIRECTION_CALL}:
        return DIRECTION_CLASS_CALL_BIAS, ()
    if normalized in {DIRECTION_BUY_PUT, DIRECTION_PUT}:
        return DIRECTION_CLASS_PUT_BIAS, ()
    if normalized == DIRECTION_NEUTRAL:
        return DIRECTION_CLASS_NEUTRAL, ()
    return DIRECTION_CLASS_UNKNOWN, (CLASSIFICATION_UNKNOWN_DIRECTION,)


def _classify_regime(regime: str) -> tuple[str, tuple[str, ...]]:
    normalized = _upper_key(regime)
    if normalized in {REGIME_BULL_TREND, REGIME_BEAR_TREND}:
        return REGIME_CLASS_TREND, ()
    if normalized == REGIME_RANGE_BOUND:
        return REGIME_CLASS_RANGE, ()
    if normalized == REGIME_HIGH_VOLATILITY:
        return REGIME_CLASS_VOLATILITY, ()
    if normalized == REGIME_OPENING_DISCOVERY:
        return REGIME_CLASS_OPENING_DISCOVERY, ()
    if normalized == REGIME_MIXED_UNCERTAIN:
        return REGIME_CLASS_MIXED, ()
    return REGIME_CLASS_UNKNOWN, (CLASSIFICATION_UNKNOWN_REGIME,)


def _classify_family(family: str) -> tuple[str, tuple[str, ...]]:
    normalized = _upper_key(family)
    if normalized == FAMILY_BREAKOUT:
        return FAMILY_CLASS_BREAKOUT, ()
    if normalized == FAMILY_VWAP:
        return FAMILY_CLASS_VWAP, ()
    if normalized == FAMILY_MEAN_REVERSION:
        return FAMILY_CLASS_MEAN_REVERSION, ()
    if normalized == FAMILY_EXPIRY:
        return FAMILY_CLASS_EXPIRY, ()
    if normalized == FAMILY_ENSEMBLE:
        return FAMILY_CLASS_ENSEMBLE, ()
    if normalized == FAMILY_EVENT:
        return FAMILY_CLASS_EVENT, ()
    return FAMILY_CLASS_UNKNOWN, (CLASSIFICATION_UNKNOWN_FAMILY,)


def _classify_instrument(instrument: str) -> str:
    normalized = _upper_key(instrument)
    if normalized in {"NIFTY", "BANKNIFTY", "SENSEX"}:
        return INSTRUMENT_CLASS_INDEX
    return INSTRUMENT_CLASS_UNKNOWN


def _classify_evidence(required_evidence_keys: Iterable[str]) -> tuple[str, tuple[str, ...]]:
    evidence = set(_lower_tuple(required_evidence_keys))
    if all(key in evidence for key in _CORE_EVIDENCE_KEYS):
        return EVIDENCE_CLASS_CORE_COMPLETE, ()
    return EVIDENCE_CLASS_INCOMPLETE, (CLASSIFICATION_EVIDENCE_INCOMPLETE,)


def _metadata() -> dict[str, Any]:
    return {
        "model": STRATEGY_CANDIDATE_CLASSIFICATION_SOURCE,
        "scope": "candidate_classification_no_runtime_wiring_no_ranking_no_scoring",
        "does_not_import_strategy_modules": True,
        "does_not_execute_strategy_callables": True,
        "does_not_rank_candidates": True,
        "does_not_score_edge": True,
    }


def _candidate_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _upper_key(value: Any) -> str:
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
    return tuple(str(item).strip().lower().replace(" ", "_").replace("-", "_") for item in values if str(item).strip())


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
    "CLASSIFICATION_EMPTY_INPUT",
    "CLASSIFICATION_EVIDENCE_INCOMPLETE",
    "CLASSIFICATION_MISSING_FIELD",
    "CLASSIFICATION_NORMALIZATION_INVALID",
    "CLASSIFICATION_UNKNOWN_DIRECTION",
    "CLASSIFICATION_UNKNOWN_FAMILY",
    "CLASSIFICATION_UNKNOWN_REGIME",
    "CandidateClassificationReport",
    "ClassifiedStrategyCandidate",
    "DIRECTION_CLASS_CALL_BIAS",
    "DIRECTION_CLASS_NEUTRAL",
    "DIRECTION_CLASS_PUT_BIAS",
    "DIRECTION_CLASS_UNKNOWN",
    "EVIDENCE_CLASS_CORE_COMPLETE",
    "EVIDENCE_CLASS_INCOMPLETE",
    "FAMILY_CLASS_BREAKOUT",
    "FAMILY_CLASS_ENSEMBLE",
    "FAMILY_CLASS_EVENT",
    "FAMILY_CLASS_EXPIRY",
    "FAMILY_CLASS_MEAN_REVERSION",
    "FAMILY_CLASS_UNKNOWN",
    "FAMILY_CLASS_VWAP",
    "INSTRUMENT_CLASS_INDEX",
    "INSTRUMENT_CLASS_UNKNOWN",
    "REGIME_CLASS_MIXED",
    "REGIME_CLASS_OPENING_DISCOVERY",
    "REGIME_CLASS_RANGE",
    "REGIME_CLASS_TREND",
    "REGIME_CLASS_UNKNOWN",
    "REGIME_CLASS_VOLATILITY",
    "STRATEGY_CANDIDATE_CLASSIFICATION_SCHEMA_VERSION",
    "STRATEGY_CANDIDATE_CLASSIFICATION_SOURCE",
    "classify_strategy_candidates",
]
