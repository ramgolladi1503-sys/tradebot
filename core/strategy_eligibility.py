"""Contract-driven strategy eligibility for EDGE-68.

This module replaces hardcoded strategy allow-lists with read-only eligibility
logic derived from StrategySpec and StrategyHypothesis contracts. It does not
execute strategy modules, generate candidates, rank candidates, wire runtime
behavior, call brokers, or create order intent.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.strategy_hypothesis_contracts import (
    HYPOTHESIS_STATUS_BLOCK,
    StrategyHypothesisContract,
    StrategyHypothesisRegistry,
    build_strategy_hypothesis_registry,
)
from core.strategy_spec import StrategySpec, StrategySpecRegistry, build_strategy_spec_registry

STRATEGY_ELIGIBILITY_SCHEMA_VERSION = 1
STRATEGY_ELIGIBILITY_SOURCE = "strategy_eligibility_v1"

ELIGIBILITY_STATUS_ELIGIBLE = "ELIGIBLE"
ELIGIBILITY_STATUS_REJECTED = "REJECTED"
ELIGIBILITY_STATUS_BLOCKED = "BLOCKED"

ELIGIBILITY_EMPTY_REGISTRY = "strategy_eligibility_empty_registry"
ELIGIBILITY_REGISTRY_INVALID = "strategy_eligibility_registry_invalid"
ELIGIBILITY_HYPOTHESIS_INVALID = "strategy_eligibility_hypothesis_invalid"
ELIGIBILITY_CONTRACT_MISSING = "strategy_eligibility_contract_missing"
ELIGIBILITY_REGIME_MISMATCH = "strategy_eligibility_regime_mismatch"
ELIGIBILITY_DIRECTION_MISMATCH = "strategy_eligibility_direction_mismatch"
ELIGIBILITY_EVIDENCE_MISSING = "strategy_eligibility_evidence_missing"
ELIGIBILITY_CONFIDENCE_TOO_LOW = "strategy_eligibility_confidence_too_low"
ELIGIBILITY_INPUT_MISSING = "strategy_eligibility_input_missing"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class StrategyEligibilityInput:
    regime: str
    direction: str
    evidence_keys: tuple[str, ...]
    market_state_confidence: float = 0.0
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
class StrategyEligibilityDecision:
    strategy_id: str
    status: str
    eligible: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    reasons: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = STRATEGY_ELIGIBILITY_SOURCE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "strategy_id": self.strategy_id,
            "status": self.status,
            "eligible": self.eligible,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


@dataclass(frozen=True)
class StrategyEligibilityReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    input: StrategyEligibilityInput
    decisions: tuple[StrategyEligibilityDecision, ...]
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
    def eligible_strategy_ids(self) -> tuple[str, ...]:
        return tuple(decision.strategy_id for decision in self.decisions if decision.eligible)

    def get(self, strategy_id: str) -> StrategyEligibilityDecision | None:
        wanted = _normalize_id(strategy_id)
        for decision in self.decisions:
            if decision.strategy_id == wanted:
                return decision
        return None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "input": self.input.to_payload(),
            "decision_count": sum(1 for _ in self.decisions),
            "eligible_strategy_ids": list(self.eligible_strategy_ids),
            "decisions": [decision.to_payload() for decision in self.decisions],
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


def evaluate_strategy_eligibility(
    *,
    regime: str,
    direction: str,
    evidence_keys: Iterable[str],
    market_state_confidence: float,
    strategy_registry: StrategySpecRegistry | Iterable[StrategySpec | Mapping[str, Any]] | None = None,
    hypothesis_registry: StrategyHypothesisRegistry | None = None,
    source: str = STRATEGY_ELIGIBILITY_SOURCE,
) -> StrategyEligibilityReport:
    """Evaluate strategy eligibility from contracts instead of hardcoded lists."""

    resolved_strategy_registry = _resolve_strategy_registry(strategy_registry)
    resolved_hypothesis_registry = hypothesis_registry or build_strategy_hypothesis_registry(resolved_strategy_registry)
    eligibility_input = StrategyEligibilityInput(
        regime=str(regime or "").strip().upper(),
        direction=str(direction or "").strip().upper(),
        evidence_keys=_lower_tuple(evidence_keys),
        market_state_confidence=_safe_float(market_state_confidence),
    )
    decisions = tuple(
        _evaluate_one(spec, resolved_hypothesis_registry.get(spec.strategy_id), eligibility_input)
        for spec in resolved_strategy_registry.specs
    )
    report_blockers = _report_blockers(resolved_strategy_registry, resolved_hypothesis_registry, eligibility_input)
    warnings = _dedupe_sorted(
        warning
        for decision in decisions
        for warning in decision.warnings
    )
    return StrategyEligibilityReport(
        schema_version=STRATEGY_ELIGIBILITY_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        input=eligibility_input,
        decisions=decisions,
        blockers=report_blockers,
        warnings=warnings,
        metadata={
            "model": STRATEGY_ELIGIBILITY_SOURCE,
            "scope": "contract_driven_strategy_eligibility_no_runtime_wiring",
            "does_not_import_strategy_modules": True,
            "does_not_execute_strategy_callables": True,
        },
    )


def _evaluate_one(
    spec: StrategySpec,
    contract: StrategyHypothesisContract | None,
    eligibility_input: StrategyEligibilityInput,
) -> StrategyEligibilityDecision:
    blockers: list[str] = []
    reasons: list[str] = []
    if contract is None:
        blockers.append(ELIGIBILITY_CONTRACT_MISSING)
    if not eligibility_input.regime or not eligibility_input.direction:
        blockers.append(ELIGIBILITY_INPUT_MISSING)
    if eligibility_input.regime not in spec.declared_regimes:
        blockers.append(ELIGIBILITY_REGIME_MISMATCH)
    if eligibility_input.direction not in spec.direction_capabilities:
        blockers.append(ELIGIBILITY_DIRECTION_MISMATCH)
    if eligibility_input.market_state_confidence < spec.min_market_state_confidence:
        blockers.append(ELIGIBILITY_CONFIDENCE_TOO_LOW)
    if contract is not None:
        if eligibility_input.regime not in contract.expected_regimes:
            blockers.append(ELIGIBILITY_REGIME_MISMATCH)
        if eligibility_input.direction not in contract.direction_capabilities:
            blockers.append(ELIGIBILITY_DIRECTION_MISMATCH)
        missing_evidence = tuple(
            key for key in contract.required_evidence_keys if key not in eligibility_input.evidence_keys
        )
        if missing_evidence:
            blockers.append(ELIGIBILITY_EVIDENCE_MISSING)
            reasons.extend(f"missing_evidence:{key}" for key in missing_evidence)
    unique_blockers = _dedupe_sorted(blockers)
    eligible = not unique_blockers
    return StrategyEligibilityDecision(
        strategy_id=spec.strategy_id,
        status=ELIGIBILITY_STATUS_ELIGIBLE if eligible else ELIGIBILITY_STATUS_REJECTED,
        eligible=eligible,
        blockers=unique_blockers,
        reasons=tuple(reasons),
        metadata={
            "family": spec.family,
            "module_path": spec.module_path,
            "callable_name": spec.callable_name,
            "min_market_state_confidence": spec.min_market_state_confidence,
        },
    )


def _report_blockers(
    strategy_registry: StrategySpecRegistry,
    hypothesis_registry: StrategyHypothesisRegistry,
    eligibility_input: StrategyEligibilityInput,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not strategy_registry.specs:
        blockers.append(ELIGIBILITY_EMPTY_REGISTRY)
    if not strategy_registry.valid:
        blockers.append(ELIGIBILITY_REGISTRY_INVALID)
    if not hypothesis_registry.valid:
        blockers.append(ELIGIBILITY_HYPOTHESIS_INVALID)
    if not eligibility_input.regime or not eligibility_input.direction:
        blockers.append(ELIGIBILITY_INPUT_MISSING)
    if any(issue.severity == HYPOTHESIS_STATUS_BLOCK for issue in hypothesis_registry.issues):
        blockers.append(ELIGIBILITY_HYPOTHESIS_INVALID)
    return _dedupe_sorted(blockers)


def _resolve_strategy_registry(
    registry: StrategySpecRegistry | Iterable[StrategySpec | Mapping[str, Any]] | None,
) -> StrategySpecRegistry:
    if isinstance(registry, StrategySpecRegistry):
        return registry
    return build_strategy_spec_registry(registry)


def _normalize_id(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


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
    "ELIGIBILITY_CONFIDENCE_TOO_LOW",
    "ELIGIBILITY_CONTRACT_MISSING",
    "ELIGIBILITY_DIRECTION_MISMATCH",
    "ELIGIBILITY_EMPTY_REGISTRY",
    "ELIGIBILITY_EVIDENCE_MISSING",
    "ELIGIBILITY_HYPOTHESIS_INVALID",
    "ELIGIBILITY_INPUT_MISSING",
    "ELIGIBILITY_REGIME_MISMATCH",
    "ELIGIBILITY_REGISTRY_INVALID",
    "ELIGIBILITY_STATUS_BLOCKED",
    "ELIGIBILITY_STATUS_ELIGIBLE",
    "ELIGIBILITY_STATUS_REJECTED",
    "STRATEGY_ELIGIBILITY_SCHEMA_VERSION",
    "STRATEGY_ELIGIBILITY_SOURCE",
    "StrategyEligibilityDecision",
    "StrategyEligibilityInput",
    "StrategyEligibilityReport",
    "evaluate_strategy_eligibility",
]
