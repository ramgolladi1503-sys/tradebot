"""Read-only strategy hypothesis contracts for EDGE-67.

A hypothesis contract states what a strategy must prove later in paper-truth
analysis. It does not calculate profitability, select strategies, generate
candidates, rank candidates, wire runtime behavior, or create order intent.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.strategy_quality_audit import QUALITY_STATUS_BLOCK, build_strategy_quality_audit
from core.strategy_spec import StrategySpec, StrategySpecRegistry, build_strategy_spec_registry

STRATEGY_HYPOTHESIS_SCHEMA_VERSION = 1
STRATEGY_HYPOTHESIS_SOURCE = "strategy_hypothesis_contracts_v1"

HYPOTHESIS_STATUS_PASS = "PASS"
HYPOTHESIS_STATUS_WARN = "WARN"
HYPOTHESIS_STATUS_BLOCK = "BLOCK"

HYPOTHESIS_EMPTY_REGISTRY = "strategy_hypothesis_empty_registry"
HYPOTHESIS_DUPLICATE_ID = "strategy_hypothesis_duplicate_id"
HYPOTHESIS_MISSING_FIELD = "strategy_hypothesis_missing_field"
HYPOTHESIS_UNKNOWN_STRATEGY = "strategy_hypothesis_unknown_strategy"
HYPOTHESIS_MISSING_CONTRACT = "strategy_hypothesis_missing_contract"
HYPOTHESIS_REGIME_MISMATCH = "strategy_hypothesis_regime_mismatch"
HYPOTHESIS_DIRECTION_MISMATCH = "strategy_hypothesis_direction_mismatch"
HYPOTHESIS_MISSING_EVIDENCE = "strategy_hypothesis_missing_evidence"
HYPOTHESIS_MISSING_OUTCOME_METRIC = "strategy_hypothesis_missing_outcome_metric"
HYPOTHESIS_MISSING_INVALIDATION_RULE = "strategy_hypothesis_missing_invalidation_rule"
HYPOTHESIS_INVALID_THRESHOLD = "strategy_hypothesis_invalid_threshold"
HYPOTHESIS_QUALITY_BLOCKED = "strategy_hypothesis_quality_blocked"

_REQUIRED_OUTCOME_METRICS = ("expectancy_r", "sample_size")
_DEFAULT_OUTCOME_METRICS = (
    "expectancy_r",
    "sample_size",
    "win_rate",
    "avg_win_r",
    "avg_loss_r",
    "max_adverse_excursion_r",
    "slippage_r",
)
_DEFAULT_INVALIDATION_REASONS = (
    "negative_expectancy",
    "insufficient_sample_size",
    "regime_mismatch",
    "missing_required_evidence",
    "spread_or_slippage_degraded",
)
_DEFAULT_EXTRA_EVIDENCE = ("strategy_quality_audit", "paper_outcome_journal")
_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class StrategyHypothesisContract:
    strategy_id: str
    hypothesis_id: str
    title: str
    thesis: str
    expected_regimes: tuple[str, ...]
    direction_capabilities: tuple[str, ...]
    required_evidence_keys: tuple[str, ...]
    outcome_metrics: tuple[str, ...] = _DEFAULT_OUTCOME_METRICS
    invalidation_reasons: tuple[str, ...] = _DEFAULT_INVALIDATION_REASONS
    min_sample_size: int = 30
    min_expectancy_r: float = 0.05
    max_drawdown_r: float = 3.0
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = STRATEGY_HYPOTHESIS_SOURCE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "strategy_id": self.strategy_id,
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "thesis": self.thesis,
            "expected_regimes": list(self.expected_regimes),
            "direction_capabilities": list(self.direction_capabilities),
            "required_evidence_keys": list(self.required_evidence_keys),
            "outcome_metrics": list(self.outcome_metrics),
            "invalidation_reasons": list(self.invalidation_reasons),
            "min_sample_size": self.min_sample_size,
            "min_expectancy_r": self.min_expectancy_r,
            "max_drawdown_r": self.max_drawdown_r,
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


@dataclass(frozen=True)
class StrategyHypothesisIssue:
    strategy_id: str | None
    hypothesis_id: str | None
    code: str
    severity: str
    message: str
    field: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "hypothesis_id": self.hypothesis_id,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "field": self.field,
        }


@dataclass(frozen=True)
class StrategyHypothesisRegistry:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    strategy_registry_valid: bool
    contracts: tuple[StrategyHypothesisContract, ...]
    issues: tuple[StrategyHypothesisIssue, ...]
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

    def get(self, strategy_id: str) -> StrategyHypothesisContract | None:
        wanted = _normalize_id(strategy_id)
        for contract in self.contracts:
            if contract.strategy_id == wanted:
                return contract
        return None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "strategy_registry_valid": self.strategy_registry_valid,
            "contract_count": sum(1 for _ in self.contracts),
            "strategy_ids": [contract.strategy_id for contract in self.contracts],
            "contracts": [contract.to_payload() for contract in self.contracts],
            "issues": [issue.to_payload() for issue in self.issues],
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


def build_default_strategy_hypothesis_contracts(
    registry: StrategySpecRegistry | Iterable[StrategySpec | Mapping[str, Any]] | None = None,
) -> tuple[StrategyHypothesisContract, ...]:
    resolved = _resolve_registry(registry)
    return tuple(_contract_from_spec(spec) for spec in resolved.specs)


def build_strategy_hypothesis_registry(
    strategy_registry: StrategySpecRegistry | Iterable[StrategySpec | Mapping[str, Any]] | None = None,
    contracts: Iterable[StrategyHypothesisContract | Mapping[str, Any]] | None = None,
    *,
    source: str = STRATEGY_HYPOTHESIS_SOURCE,
) -> StrategyHypothesisRegistry:
    resolved_registry = _resolve_registry(strategy_registry)
    resolved_contracts = tuple(
        _coerce_contract(contract)
        for contract in (contracts if contracts is not None else build_default_strategy_hypothesis_contracts(resolved_registry))
    )
    issues = _validate_contracts(resolved_registry, resolved_contracts)
    return StrategyHypothesisRegistry(
        schema_version=STRATEGY_HYPOTHESIS_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        strategy_registry_valid=resolved_registry.valid,
        contracts=resolved_contracts,
        issues=issues,
        blockers=_dedupe_sorted(issue.code for issue in issues if issue.severity == HYPOTHESIS_STATUS_BLOCK),
        warnings=_dedupe_sorted(issue.code for issue in issues if issue.severity == HYPOTHESIS_STATUS_WARN),
        metadata={
            "model": STRATEGY_HYPOTHESIS_SOURCE,
            "scope": "read_only_strategy_hypothesis_contracts_no_selection",
            "does_not_import_strategy_modules": True,
            "does_not_execute_strategy_callables": True,
        },
    )


def get_strategy_hypothesis_contract(
    strategy_id: str,
    registry: StrategyHypothesisRegistry | None = None,
) -> StrategyHypothesisContract | None:
    return (registry or build_strategy_hypothesis_registry()).get(strategy_id)


def _resolve_registry(
    registry: StrategySpecRegistry | Iterable[StrategySpec | Mapping[str, Any]] | None,
) -> StrategySpecRegistry:
    if isinstance(registry, StrategySpecRegistry):
        return registry
    return build_strategy_spec_registry(registry)


def _contract_from_spec(spec: StrategySpec) -> StrategyHypothesisContract:
    required_evidence = _dedupe_sorted((*spec.required_evidence_keys, *_DEFAULT_EXTRA_EVIDENCE))
    return StrategyHypothesisContract(
        strategy_id=spec.strategy_id,
        hypothesis_id=f"{spec.strategy_id}_hypothesis_v1",
        title=f"{spec.name} hypothesis v1",
        thesis=f"{spec.name} should only be evaluated when declared regime, direction, and evidence contracts are satisfied.",
        expected_regimes=spec.declared_regimes,
        direction_capabilities=spec.direction_capabilities,
        required_evidence_keys=required_evidence,
        metadata={
            "family": spec.family,
            "module_path": spec.module_path,
            "callable_name": spec.callable_name,
            "min_market_state_confidence": spec.min_market_state_confidence,
            "hypothesis_scope": "paper_truth_validation_only",
        },
    )


def _validate_contracts(
    registry: StrategySpecRegistry,
    contracts: tuple[StrategyHypothesisContract, ...],
) -> tuple[StrategyHypothesisIssue, ...]:
    issues: list[StrategyHypothesisIssue] = []
    if not registry.specs:
        issues.append(_issue(None, None, HYPOTHESIS_EMPTY_REGISTRY, HYPOTHESIS_STATUS_BLOCK, "strategy registry cannot be empty"))
        return tuple(issues)
    if not contracts:
        issues.append(_issue(None, None, HYPOTHESIS_MISSING_CONTRACT, HYPOTHESIS_STATUS_BLOCK, "hypothesis contracts cannot be empty"))
        return tuple(issues)

    strategy_ids = {spec.strategy_id for spec in registry.specs}
    specs_by_id = {spec.strategy_id: spec for spec in registry.specs}
    contract_ids: dict[str, int] = {}
    contract_strategy_ids: dict[str, int] = {}
    for contract in contracts:
        contract_ids[contract.hypothesis_id] = contract_ids.get(contract.hypothesis_id, 0) + 1
        contract_strategy_ids[contract.strategy_id] = contract_strategy_ids.get(contract.strategy_id, 0) + 1

    for hypothesis_id, count in sorted(contract_ids.items()):
        if count > 1:
            issues.append(_issue(None, hypothesis_id, HYPOTHESIS_DUPLICATE_ID, HYPOTHESIS_STATUS_BLOCK, "hypothesis_id must be unique", "hypothesis_id"))
    for strategy_id, count in sorted(contract_strategy_ids.items()):
        if count > 1:
            issues.append(_issue(strategy_id, None, HYPOTHESIS_DUPLICATE_ID, HYPOTHESIS_STATUS_BLOCK, "strategy_id must have at most one hypothesis contract", "strategy_id"))
    for strategy_id in sorted(strategy_ids - set(contract_strategy_ids)):
        issues.append(_issue(strategy_id, None, HYPOTHESIS_MISSING_CONTRACT, HYPOTHESIS_STATUS_BLOCK, "strategy is missing a hypothesis contract", "strategy_id"))

    quality_audit = build_strategy_quality_audit(registry)
    blocked_strategy_ids = {
        record.strategy_id for record in quality_audit.records if record.quality_status == QUALITY_STATUS_BLOCK
    }
    for strategy_id in sorted(blocked_strategy_ids):
        issues.append(_issue(strategy_id, None, HYPOTHESIS_QUALITY_BLOCKED, HYPOTHESIS_STATUS_BLOCK, "strategy quality audit is blocking this strategy", "strategy_id"))

    for contract in contracts:
        issues.extend(_validate_required_fields(contract))
        if contract.strategy_id not in strategy_ids:
            issues.append(_issue(contract.strategy_id, contract.hypothesis_id, HYPOTHESIS_UNKNOWN_STRATEGY, HYPOTHESIS_STATUS_BLOCK, "contract references a strategy that is not in the registry", "strategy_id"))
            continue
        issues.extend(_validate_contract_against_spec(contract, specs_by_id[contract.strategy_id]))
    return tuple(issues)


def _validate_required_fields(contract: StrategyHypothesisContract) -> tuple[StrategyHypothesisIssue, ...]:
    issues: list[StrategyHypothesisIssue] = []
    for field_name in ("strategy_id", "hypothesis_id", "title", "thesis"):
        if not getattr(contract, field_name):
            issues.append(_issue(contract.strategy_id or None, contract.hypothesis_id or None, HYPOTHESIS_MISSING_FIELD, HYPOTHESIS_STATUS_BLOCK, f"{field_name} is required", field_name))
    for field_name in ("expected_regimes", "direction_capabilities", "required_evidence_keys", "outcome_metrics"):
        if not getattr(contract, field_name):
            issues.append(_issue(contract.strategy_id, contract.hypothesis_id, HYPOTHESIS_MISSING_FIELD, HYPOTHESIS_STATUS_BLOCK, f"{field_name} must not be empty", field_name))
    if not contract.invalidation_reasons:
        issues.append(_issue(contract.strategy_id, contract.hypothesis_id, HYPOTHESIS_MISSING_INVALIDATION_RULE, HYPOTHESIS_STATUS_BLOCK, "at least one invalidation rule is required", "invalidation_reasons"))
    if contract.min_sample_size < 1:
        issues.append(_issue(contract.strategy_id, contract.hypothesis_id, HYPOTHESIS_INVALID_THRESHOLD, HYPOTHESIS_STATUS_BLOCK, "min_sample_size must be positive", "min_sample_size"))
    if contract.min_expectancy_r < -10.0 or contract.min_expectancy_r > 10.0:
        issues.append(_issue(contract.strategy_id, contract.hypothesis_id, HYPOTHESIS_INVALID_THRESHOLD, HYPOTHESIS_STATUS_BLOCK, "min_expectancy_r must be within a bounded R range", "min_expectancy_r"))
    if contract.max_drawdown_r <= 0.0:
        issues.append(_issue(contract.strategy_id, contract.hypothesis_id, HYPOTHESIS_INVALID_THRESHOLD, HYPOTHESIS_STATUS_BLOCK, "max_drawdown_r must be positive", "max_drawdown_r"))
    return tuple(issues)


def _validate_contract_against_spec(
    contract: StrategyHypothesisContract,
    spec: StrategySpec,
) -> tuple[StrategyHypothesisIssue, ...]:
    issues: list[StrategyHypothesisIssue] = []
    spec_regimes = set(spec.declared_regimes)
    spec_directions = set(spec.direction_capabilities)
    missing_regimes = tuple(regime for regime in contract.expected_regimes if regime not in spec_regimes)
    missing_directions = tuple(direction for direction in contract.direction_capabilities if direction not in spec_directions)
    missing_evidence = tuple(key for key in spec.required_evidence_keys if key not in contract.required_evidence_keys)

    for regime in missing_regimes:
        issues.append(_issue(contract.strategy_id, contract.hypothesis_id, HYPOTHESIS_REGIME_MISMATCH, HYPOTHESIS_STATUS_BLOCK, f"expected regime is not declared by StrategySpec: {regime}", "expected_regimes"))
    for direction in missing_directions:
        issues.append(_issue(contract.strategy_id, contract.hypothesis_id, HYPOTHESIS_DIRECTION_MISMATCH, HYPOTHESIS_STATUS_BLOCK, f"direction is not declared by StrategySpec: {direction}", "direction_capabilities"))
    for evidence_key in missing_evidence:
        issues.append(_issue(contract.strategy_id, contract.hypothesis_id, HYPOTHESIS_MISSING_EVIDENCE, HYPOTHESIS_STATUS_BLOCK, f"required evidence key missing from hypothesis contract: {evidence_key}", "required_evidence_keys"))
    for metric in _REQUIRED_OUTCOME_METRICS:
        if metric not in contract.outcome_metrics:
            issues.append(_issue(contract.strategy_id, contract.hypothesis_id, HYPOTHESIS_MISSING_OUTCOME_METRIC, HYPOTHESIS_STATUS_BLOCK, f"required outcome metric missing: {metric}", "outcome_metrics"))
    return tuple(issues)


def _coerce_contract(contract: StrategyHypothesisContract | Mapping[str, Any]) -> StrategyHypothesisContract:
    if isinstance(contract, StrategyHypothesisContract):
        return _normalized_contract(contract)
    if not isinstance(contract, Mapping):
        return _normalized_contract(StrategyHypothesisContract("", "", "", "", (), (), ()))
    return _normalized_contract(
        StrategyHypothesisContract(
            strategy_id=str(contract.get("strategy_id") or ""),
            hypothesis_id=str(contract.get("hypothesis_id") or ""),
            title=str(contract.get("title") or ""),
            thesis=str(contract.get("thesis") or ""),
            expected_regimes=_upper_tuple(contract.get("expected_regimes")),
            direction_capabilities=_upper_tuple(contract.get("direction_capabilities")),
            required_evidence_keys=_lower_tuple(contract.get("required_evidence_keys")),
            outcome_metrics=_lower_tuple(contract.get("outcome_metrics") or _DEFAULT_OUTCOME_METRICS),
            invalidation_reasons=_lower_tuple(contract.get("invalidation_reasons") or _DEFAULT_INVALIDATION_REASONS),
            min_sample_size=_safe_int(contract.get("min_sample_size"), default=30),
            min_expectancy_r=_safe_float(contract.get("min_expectancy_r"), default=0.05),
            max_drawdown_r=_safe_float(contract.get("max_drawdown_r"), default=3.0),
            metadata=_safe_dict(contract.get("metadata")),
        )
    )


def _normalized_contract(contract: StrategyHypothesisContract) -> StrategyHypothesisContract:
    return StrategyHypothesisContract(
        strategy_id=_normalize_id(contract.strategy_id),
        hypothesis_id=_normalize_id(contract.hypothesis_id),
        title=str(contract.title or "").strip(),
        thesis=str(contract.thesis or "").strip(),
        expected_regimes=_upper_tuple(contract.expected_regimes),
        direction_capabilities=_upper_tuple(contract.direction_capabilities),
        required_evidence_keys=_lower_tuple(contract.required_evidence_keys),
        outcome_metrics=_lower_tuple(contract.outcome_metrics),
        invalidation_reasons=_lower_tuple(contract.invalidation_reasons),
        min_sample_size=_safe_int(contract.min_sample_size, default=30),
        min_expectancy_r=_safe_float(contract.min_expectancy_r, default=0.05),
        max_drawdown_r=_safe_float(contract.max_drawdown_r, default=3.0),
        metadata=_safe_dict(contract.metadata),
        read_only=True,
        append=False,
        source=STRATEGY_HYPOTHESIS_SOURCE,
    )


def _issue(
    strategy_id: str | None,
    hypothesis_id: str | None,
    code: str,
    severity: str,
    message: str,
    field: str | None = None,
) -> StrategyHypothesisIssue:
    return StrategyHypothesisIssue(strategy_id, hypothesis_id, code, severity, message, field)


def _normalize_id(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _upper_tuple(value: Any) -> tuple[str, ...]:
    return tuple(item.upper() for item in _string_tuple(value))


def _lower_tuple(value: Any) -> tuple[str, ...]:
    return tuple(item.lower() for item in _string_tuple(value))


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, Iterable):
        values = tuple(value)
    else:
        values = (value,)
    return tuple(str(item).strip() for item in values if str(item).strip())


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return round(float(value), 4)
    except Exception:
        return default


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
    "HYPOTHESIS_DIRECTION_MISMATCH",
    "HYPOTHESIS_DUPLICATE_ID",
    "HYPOTHESIS_EMPTY_REGISTRY",
    "HYPOTHESIS_INVALID_THRESHOLD",
    "HYPOTHESIS_MISSING_CONTRACT",
    "HYPOTHESIS_MISSING_EVIDENCE",
    "HYPOTHESIS_MISSING_FIELD",
    "HYPOTHESIS_MISSING_INVALIDATION_RULE",
    "HYPOTHESIS_MISSING_OUTCOME_METRIC",
    "HYPOTHESIS_QUALITY_BLOCKED",
    "HYPOTHESIS_REGIME_MISMATCH",
    "HYPOTHESIS_STATUS_BLOCK",
    "HYPOTHESIS_STATUS_PASS",
    "HYPOTHESIS_STATUS_WARN",
    "HYPOTHESIS_UNKNOWN_STRATEGY",
    "STRATEGY_HYPOTHESIS_SCHEMA_VERSION",
    "STRATEGY_HYPOTHESIS_SOURCE",
    "StrategyHypothesisContract",
    "StrategyHypothesisIssue",
    "StrategyHypothesisRegistry",
    "build_default_strategy_hypothesis_contracts",
    "build_strategy_hypothesis_registry",
    "get_strategy_hypothesis_contract",
]
