"""Read-only strategy registry candidate pool for EDGE-69.

This module converts contract-eligible strategy metadata into a deterministic
candidate pool seam. It does not execute strategy modules, inspect market ticks,
rank candidates, score edge, wire runtime behavior, call brokers, or create
order intent.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.strategy_eligibility import (
    StrategyEligibilityReport,
    evaluate_strategy_eligibility,
)
from core.strategy_hypothesis_contracts import StrategyHypothesisRegistry
from core.strategy_spec import StrategySpec, StrategySpecRegistry, build_strategy_spec_registry

STRATEGY_CANDIDATE_POOL_SCHEMA_VERSION = 1
STRATEGY_CANDIDATE_POOL_SOURCE = "strategy_candidate_pool_v1"

CANDIDATE_POOL_EMPTY = "strategy_candidate_pool_empty"
CANDIDATE_POOL_ELIGIBILITY_INVALID = "strategy_candidate_pool_eligibility_invalid"
CANDIDATE_POOL_REGISTRY_INVALID = "strategy_candidate_pool_registry_invalid"
CANDIDATE_POOL_INPUT_MISSING = "strategy_candidate_pool_input_missing"
CANDIDATE_POOL_STRATEGY_INELIGIBLE = "strategy_candidate_pool_strategy_ineligible"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class StrategyCandidatePoolInput:
    regime: str
    direction: str
    evidence_keys: tuple[str, ...]
    market_state_confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "direction": self.direction,
            "evidence_keys": list(self.evidence_keys),
            "market_state_confidence": self.market_state_confidence,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StrategyRegistryCandidate:
    candidate_id: str
    strategy_id: str
    instrument: str
    regime: str
    direction: str
    family: str
    module_path: str
    callable_name: str
    eligibility_status: str
    required_evidence_keys: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = STRATEGY_CANDIDATE_POOL_SOURCE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "candidate_id": self.candidate_id,
            "strategy_id": self.strategy_id,
            "instrument": self.instrument,
            "regime": self.regime,
            "direction": self.direction,
            "family": self.family,
            "module_path": self.module_path,
            "callable_name": self.callable_name,
            "eligibility_status": self.eligibility_status,
            "required_evidence_keys": list(self.required_evidence_keys),
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


@dataclass(frozen=True)
class StrategyCandidatePoolReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    input: StrategyCandidatePoolInput
    candidates: tuple[StrategyRegistryCandidate, ...]
    excluded_strategy_ids: tuple[str, ...]
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
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(candidate.candidate_id for candidate in self.candidates)

    def get(self, candidate_id: str) -> StrategyRegistryCandidate | None:
        wanted = _candidate_key(candidate_id)
        for candidate in self.candidates:
            if candidate.candidate_id == wanted:
                return candidate
        return None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "input": self.input.to_payload(),
            "candidate_count": len(self.candidates),
            "candidate_ids": list(self.candidate_ids),
            "candidates": [candidate.to_payload() for candidate in self.candidates],
            "excluded_strategy_ids": list(self.excluded_strategy_ids),
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


def build_strategy_candidate_pool(
    *,
    regime: str,
    direction: str,
    evidence_keys: Iterable[str],
    market_state_confidence: float,
    strategy_registry: StrategySpecRegistry | Iterable[StrategySpec | Mapping[str, Any]] | None = None,
    hypothesis_registry: StrategyHypothesisRegistry | None = None,
    eligibility_report: StrategyEligibilityReport | None = None,
    source: str = STRATEGY_CANDIDATE_POOL_SOURCE,
) -> StrategyCandidatePoolReport:
    """Build deterministic metadata candidates from eligible strategy specs only."""

    resolved_registry = _resolve_strategy_registry(strategy_registry)
    pool_input = StrategyCandidatePoolInput(
        regime=str(regime or "").strip().upper(),
        direction=str(direction or "").strip().upper(),
        evidence_keys=_lower_tuple(evidence_keys),
        market_state_confidence=_safe_float(market_state_confidence),
    )
    resolved_eligibility = eligibility_report or evaluate_strategy_eligibility(
        regime=pool_input.regime,
        direction=pool_input.direction,
        evidence_keys=pool_input.evidence_keys,
        market_state_confidence=pool_input.market_state_confidence,
        strategy_registry=resolved_registry,
        hypothesis_registry=hypothesis_registry,
    )

    blockers = _report_blockers(resolved_registry, resolved_eligibility, pool_input)
    eligible_ids = set(resolved_eligibility.eligible_strategy_ids) if not blockers else set()
    candidates = tuple(
        candidate
        for spec in resolved_registry.specs
        if spec.strategy_id in eligible_ids
        for candidate in _candidates_from_spec(spec, pool_input, resolved_eligibility)
    )
    excluded_ids = tuple(
        spec.strategy_id for spec in resolved_registry.specs if spec.strategy_id not in eligible_ids
    )
    warnings = _dedupe_sorted(
        (
            *(resolved_eligibility.warnings if resolved_eligibility else ()),
            *((CANDIDATE_POOL_EMPTY,) if not candidates and not blockers else ()),
            *((CANDIDATE_POOL_STRATEGY_INELIGIBLE,) if excluded_ids else ()),
        )
    )
    return StrategyCandidatePoolReport(
        schema_version=STRATEGY_CANDIDATE_POOL_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        input=pool_input,
        candidates=candidates,
        excluded_strategy_ids=excluded_ids,
        blockers=blockers,
        warnings=warnings,
        metadata={
            "model": STRATEGY_CANDIDATE_POOL_SOURCE,
            "scope": "strategy_registry_candidate_pool_no_runtime_wiring_no_ranking",
            "eligibility_source": resolved_eligibility.source,
            "does_not_import_strategy_modules": True,
            "does_not_execute_strategy_callables": True,
            "does_not_rank_candidates": True,
            "does_not_score_edge": True,
        },
    )


def _candidates_from_spec(
    spec: StrategySpec,
    pool_input: StrategyCandidatePoolInput,
    eligibility_report: StrategyEligibilityReport,
) -> tuple[StrategyRegistryCandidate, ...]:
    decision = eligibility_report.get(spec.strategy_id)
    if decision is None or not decision.eligible:
        return ()
    return tuple(
        StrategyRegistryCandidate(
            candidate_id=_build_candidate_id(spec.strategy_id, instrument, pool_input.direction, pool_input.regime),
            strategy_id=spec.strategy_id,
            instrument=instrument,
            regime=pool_input.regime,
            direction=pool_input.direction,
            family=spec.family,
            module_path=spec.module_path,
            callable_name=spec.callable_name,
            eligibility_status=decision.status,
            required_evidence_keys=spec.required_evidence_keys,
            metadata={
                "strategy_name": spec.name,
                "min_market_state_confidence": spec.min_market_state_confidence,
                "eligibility_blockers": list(decision.blockers),
                "eligibility_reasons": list(decision.reasons),
            },
        )
        for instrument in sorted(spec.instruments)
    )


def _report_blockers(
    strategy_registry: StrategySpecRegistry,
    eligibility_report: StrategyEligibilityReport,
    pool_input: StrategyCandidatePoolInput,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not pool_input.regime or not pool_input.direction:
        blockers.append(CANDIDATE_POOL_INPUT_MISSING)
    if not strategy_registry.valid:
        blockers.append(CANDIDATE_POOL_REGISTRY_INVALID)
    if not eligibility_report.valid:
        blockers.append(CANDIDATE_POOL_ELIGIBILITY_INVALID)
    return _dedupe_sorted(blockers)


def _resolve_strategy_registry(
    registry: StrategySpecRegistry | Iterable[StrategySpec | Mapping[str, Any]] | None,
) -> StrategySpecRegistry:
    if isinstance(registry, StrategySpecRegistry):
        return registry
    return build_strategy_spec_registry(registry)


def _build_candidate_id(strategy_id: str, instrument: str, direction: str, regime: str) -> str:
    return _candidate_key(f"{strategy_id}:{instrument}:{direction}:{regime}")


def _candidate_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _lower_tuple(value: Iterable[str]) -> tuple[str, ...]:
    return tuple(str(item).strip().lower() for item in value if str(item).strip())


def _safe_float(value: Any) -> float:
    try:
        return round(float(value), 4)
    except Exception:
        return 0.0


def _dedupe_sorted(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


__all__ = [
    "CANDIDATE_POOL_ELIGIBILITY_INVALID",
    "CANDIDATE_POOL_EMPTY",
    "CANDIDATE_POOL_INPUT_MISSING",
    "CANDIDATE_POOL_REGISTRY_INVALID",
    "CANDIDATE_POOL_STRATEGY_INELIGIBLE",
    "STRATEGY_CANDIDATE_POOL_SCHEMA_VERSION",
    "STRATEGY_CANDIDATE_POOL_SOURCE",
    "StrategyCandidatePoolInput",
    "StrategyCandidatePoolReport",
    "StrategyRegistryCandidate",
    "build_strategy_candidate_pool",
]
