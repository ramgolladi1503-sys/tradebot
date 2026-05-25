"""Read-only StrategySpec registry contract.

EDGE-65 creates a declarative registry for strategy metadata. It does not select
strategies, replace hardcoded eligibility, generate candidates, rank candidates,
write runtime files, call brokers, or create order intent. EDGE-68 can later use
this contract to replace hardcoded strategy eligibility.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from core.regime_state import (
    REGIME_BEAR_TREND,
    REGIME_BULL_TREND,
    REGIME_HIGH_VOLATILITY,
    REGIME_LIQUIDITY_STRESSED,
    REGIME_MIXED_UNCERTAIN,
    REGIME_OPENING_DISCOVERY,
    REGIME_OUT_OF_SESSION,
    REGIME_RANGE_BOUND,
    REGIME_UNKNOWN,
    REGIME_VOLATILITY_STRESSED,
)

STRATEGY_SPEC_SCHEMA_VERSION = 1
STRATEGY_SPEC_SOURCE = "strategy_spec_registry_v1"

STRATEGY_SPEC_INVALID = "strategy_spec_invalid"
STRATEGY_SPEC_DUPLICATE_ID = "strategy_spec_duplicate_id"
STRATEGY_SPEC_EMPTY_REGISTRY = "strategy_spec_empty_registry"
STRATEGY_SPEC_MISSING_FIELD = "strategy_spec_missing_field"
STRATEGY_SPEC_UNKNOWN_REGIME = "strategy_spec_unknown_regime"
STRATEGY_SPEC_UNSAFE_REGIME = "strategy_spec_unsafe_regime"
STRATEGY_SPEC_UNSAFE_EVIDENCE = "strategy_spec_unsafe_evidence"

FAMILY_BREAKOUT = "BREAKOUT"
FAMILY_VWAP = "VWAP"
FAMILY_MEAN_REVERSION = "MEAN_REVERSION"
FAMILY_EXPIRY = "EXPIRY"
FAMILY_ENSEMBLE = "ENSEMBLE"
FAMILY_EVENT = "EVENT"

DIRECTION_BUY_CALL = "BUY_CALL"
DIRECTION_BUY_PUT = "BUY_PUT"
DIRECTION_CALL = "CALL"
DIRECTION_PUT = "PUT"
DIRECTION_NEUTRAL = "NEUTRAL"

_VALID_REGIMES = {
    REGIME_BEAR_TREND,
    REGIME_BULL_TREND,
    REGIME_HIGH_VOLATILITY,
    REGIME_LIQUIDITY_STRESSED,
    REGIME_MIXED_UNCERTAIN,
    REGIME_OPENING_DISCOVERY,
    REGIME_OUT_OF_SESSION,
    REGIME_RANGE_BOUND,
    REGIME_UNKNOWN,
    REGIME_VOLATILITY_STRESSED,
}

_UNSAFE_REGIMES = {
    REGIME_UNKNOWN,
    REGIME_OUT_OF_SESSION,
    REGIME_LIQUIDITY_STRESSED,
    REGIME_VOLATILITY_STRESSED,
}

_REQUIRED_MARKET_STATE_DIMENSIONS = (
    "trend",
    "volatility",
    "breadth",
    "liquidity",
    "session",
)

_DEFAULT_REQUIRED_EVIDENCE_KEYS = (
    "market_state",
    "regime_state",
    "feed_health_truth",
    "quote_truth",
)

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class StrategySpec:
    """Declarative metadata for one strategy implementation."""

    strategy_id: str
    name: str
    family: str
    module_path: str
    callable_name: str
    instruments: tuple[str, ...]
    declared_regimes: tuple[str, ...]
    blocked_regimes: tuple[str, ...] = field(default_factory=tuple)
    required_market_state_dimensions: tuple[str, ...] = _REQUIRED_MARKET_STATE_DIMENSIONS
    required_evidence_keys: tuple[str, ...] = _DEFAULT_REQUIRED_EVIDENCE_KEYS
    direction_capabilities: tuple[str, ...] = field(default_factory=tuple)
    min_market_state_confidence: float = 0.0
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = STRATEGY_SPEC_SOURCE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "family": self.family,
            "module_path": self.module_path,
            "callable_name": self.callable_name,
            "instruments": list(self.instruments),
            "declared_regimes": list(self.declared_regimes),
            "blocked_regimes": list(self.blocked_regimes),
            "required_market_state_dimensions": list(self.required_market_state_dimensions),
            "required_evidence_keys": list(self.required_evidence_keys),
            "direction_capabilities": list(self.direction_capabilities),
            "min_market_state_confidence": self.min_market_state_confidence,
            "description": self.description,
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


@dataclass(frozen=True)
class StrategySpecIssue:
    """Validation issue for a StrategySpec registry."""

    strategy_id: str | None
    code: str
    severity: str
    message: str
    field: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "field": self.field,
        }


@dataclass(frozen=True)
class StrategySpecRegistry:
    """Read-only registry report for strategy specs."""

    schema_version: int
    read_only: bool
    append: bool
    source: str
    specs: tuple[StrategySpec, ...]
    issues: tuple[StrategySpecIssue, ...]
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

    def strategy_ids(self) -> tuple[str, ...]:
        return tuple(spec.strategy_id for spec in self.specs)

    def get(self, strategy_id: str) -> StrategySpec | None:
        wanted = _normalize_id(strategy_id)
        for spec in self.specs:
            if spec.strategy_id == wanted:
                return spec
        return None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "spec_count": len(self.specs),
            "strategy_ids": list(self.strategy_ids()),
            "specs": [spec.to_payload() for spec in self.specs],
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


def build_default_strategy_specs() -> tuple[StrategySpec, ...]:
    """Return the default declarative strategy inventory.

    This is metadata only. It does not import strategy modules or execute strategy
    callables.
    """

    return (
        StrategySpec(
            strategy_id="ensemble",
            name="Ensemble Signal",
            family=FAMILY_ENSEMBLE,
            module_path="strategies.ensemble",
            callable_name="ensemble_signal",
            instruments=("NIFTY", "BANKNIFTY", "SENSEX"),
            declared_regimes=(
                REGIME_BULL_TREND,
                REGIME_BEAR_TREND,
                REGIME_RANGE_BOUND,
                REGIME_HIGH_VOLATILITY,
                REGIME_MIXED_UNCERTAIN,
            ),
            blocked_regimes=tuple(sorted(_UNSAFE_REGIMES)),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.55,
            description="Aggregates trend, ORB, mean-reversion, micro-pattern, and event signals.",
        ),
        StrategySpec(
            strategy_id="nifty_intraday",
            name="NIFTY Intraday VWAP",
            family=FAMILY_VWAP,
            module_path="strategies.nifty_intraday",
            callable_name="generate_signal",
            instruments=("NIFTY",),
            declared_regimes=(REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND),
            blocked_regimes=tuple(sorted(_UNSAFE_REGIMES)),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.60,
            description="NIFTY VWAP directional and range-aware intraday setup metadata.",
        ),
        StrategySpec(
            strategy_id="banknifty_intraday",
            name="BANKNIFTY Intraday VWAP",
            family=FAMILY_VWAP,
            module_path="strategies.banknifty_intraday",
            callable_name="generate_signal",
            instruments=("BANKNIFTY",),
            declared_regimes=(REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND),
            blocked_regimes=tuple(sorted(_UNSAFE_REGIMES)),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.60,
            description="BANKNIFTY VWAP directional and range-aware intraday setup metadata.",
        ),
        StrategySpec(
            strategy_id="sensex_intraday",
            name="SENSEX Intraday VWAP",
            family=FAMILY_VWAP,
            module_path="strategies.sensex_intraday",
            callable_name="generate_signal",
            instruments=("SENSEX",),
            declared_regimes=(REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND),
            blocked_regimes=tuple(sorted(_UNSAFE_REGIMES)),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.60,
            description="SENSEX VWAP directional and range-aware intraday setup metadata.",
        ),
        StrategySpec(
            strategy_id="zero_hero_expiry",
            name="Zero Hero Expiry",
            family=FAMILY_EXPIRY,
            module_path="strategies.zero_hero",
            callable_name="generate_signal",
            instruments=("NIFTY", "BANKNIFTY", "SENSEX"),
            declared_regimes=(REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_HIGH_VOLATILITY),
            blocked_regimes=tuple(sorted(_UNSAFE_REGIMES)),
            direction_capabilities=(DIRECTION_CALL, DIRECTION_PUT, DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.70,
            description="Expiry-focused optionality metadata. This registry does not activate it.",
        ),
    )


def build_strategy_spec_registry(
    specs: Iterable[StrategySpec | Mapping[str, Any]] | None = None,
    *,
    source: str = STRATEGY_SPEC_SOURCE,
) -> StrategySpecRegistry:
    """Build and validate a read-only strategy registry report."""

    normalized_specs = tuple(_coerce_spec(spec) for spec in (specs if specs is not None else build_default_strategy_specs()))
    issues = _validate_specs(normalized_specs)
    blockers = _dedupe_sorted(issue.code for issue in issues if issue.severity == "BLOCKER")
    warnings = _dedupe_sorted(issue.code for issue in issues if issue.severity == "WARNING")
    return StrategySpecRegistry(
        schema_version=STRATEGY_SPEC_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        specs=normalized_specs,
        issues=issues,
        blockers=blockers,
        warnings=warnings,
        metadata={
            "model": STRATEGY_SPEC_SOURCE,
            "scope": "read_only_strategy_spec_registry_no_eligibility_replacement",
            "does_not_import_strategy_modules": True,
        },
    )


def get_strategy_spec(strategy_id: str, registry: StrategySpecRegistry | None = None) -> StrategySpec | None:
    """Look up one spec by id without executing strategy code."""

    current_registry = registry or build_strategy_spec_registry()
    return current_registry.get(strategy_id)


def _validate_specs(specs: tuple[StrategySpec, ...]) -> tuple[StrategySpecIssue, ...]:
    issues: list[StrategySpecIssue] = []
    if not specs:
        issues.append(
            StrategySpecIssue(
                strategy_id=None,
                code=STRATEGY_SPEC_EMPTY_REGISTRY,
                severity="BLOCKER",
                message="strategy registry cannot be empty",
            )
        )
        return tuple(issues)

    seen: dict[str, int] = {}
    for spec in specs:
        seen[spec.strategy_id] = seen.get(spec.strategy_id, 0) + 1
    for strategy_id, count in sorted(seen.items()):
        if count > 1:
            issues.append(
                StrategySpecIssue(
                    strategy_id=strategy_id,
                    code=STRATEGY_SPEC_DUPLICATE_ID,
                    severity="BLOCKER",
                    message="strategy_id must be unique",
                    field="strategy_id",
                )
            )

    for spec in specs:
        issues.extend(_validate_required_fields(spec))
        issues.extend(_validate_regimes(spec))
        issues.extend(_validate_evidence_contract(spec))
    return tuple(issues)


def _validate_required_fields(spec: StrategySpec) -> tuple[StrategySpecIssue, ...]:
    issues: list[StrategySpecIssue] = []
    required_strings = {
        "strategy_id": spec.strategy_id,
        "name": spec.name,
        "family": spec.family,
        "module_path": spec.module_path,
        "callable_name": spec.callable_name,
    }
    for field_name, value in required_strings.items():
        if not value:
            issues.append(
                StrategySpecIssue(
                    strategy_id=spec.strategy_id or None,
                    code=STRATEGY_SPEC_MISSING_FIELD,
                    severity="BLOCKER",
                    message=f"{field_name} is required",
                    field=field_name,
                )
            )
    for field_name, values in {
        "instruments": spec.instruments,
        "declared_regimes": spec.declared_regimes,
        "direction_capabilities": spec.direction_capabilities,
    }.items():
        if not values:
            issues.append(
                StrategySpecIssue(
                    strategy_id=spec.strategy_id or None,
                    code=STRATEGY_SPEC_MISSING_FIELD,
                    severity="BLOCKER",
                    message=f"{field_name} must not be empty",
                    field=field_name,
                )
            )
    if spec.min_market_state_confidence < 0.0 or spec.min_market_state_confidence > 1.0:
        issues.append(
            StrategySpecIssue(
                strategy_id=spec.strategy_id,
                code=STRATEGY_SPEC_INVALID,
                severity="BLOCKER",
                message="min_market_state_confidence must be between 0 and 1",
                field="min_market_state_confidence",
            )
        )
    return tuple(issues)


def _validate_regimes(spec: StrategySpec) -> tuple[StrategySpecIssue, ...]:
    issues: list[StrategySpecIssue] = []
    for regime in (*spec.declared_regimes, *spec.blocked_regimes):
        if regime not in _VALID_REGIMES:
            issues.append(
                StrategySpecIssue(
                    strategy_id=spec.strategy_id,
                    code=STRATEGY_SPEC_UNKNOWN_REGIME,
                    severity="BLOCKER",
                    message=f"unknown regime: {regime}",
                    field="declared_regimes",
                )
            )
    unsafe_declared = tuple(regime for regime in spec.declared_regimes if regime in _UNSAFE_REGIMES)
    for regime in unsafe_declared:
        issues.append(
            StrategySpecIssue(
                strategy_id=spec.strategy_id,
                code=STRATEGY_SPEC_UNSAFE_REGIME,
                severity="BLOCKER",
                message=f"unsafe regime cannot be declared tradable metadata: {regime}",
                field="declared_regimes",
            )
        )
    missing_unsafe_blocks = tuple(regime for regime in _UNSAFE_REGIMES if regime not in spec.blocked_regimes)
    for regime in missing_unsafe_blocks:
        issues.append(
            StrategySpecIssue(
                strategy_id=spec.strategy_id,
                code=STRATEGY_SPEC_UNSAFE_REGIME,
                severity="WARNING",
                message=f"unsafe regime should be explicitly blocked: {regime}",
                field="blocked_regimes",
            )
        )
    return tuple(issues)


def _validate_evidence_contract(spec: StrategySpec) -> tuple[StrategySpecIssue, ...]:
    issues: list[StrategySpecIssue] = []
    missing_dimensions = tuple(
        dimension for dimension in _REQUIRED_MARKET_STATE_DIMENSIONS if dimension not in spec.required_market_state_dimensions
    )
    for dimension in missing_dimensions:
        issues.append(
            StrategySpecIssue(
                strategy_id=spec.strategy_id,
                code=STRATEGY_SPEC_UNSAFE_EVIDENCE,
                severity="BLOCKER",
                message=f"missing required market-state dimension: {dimension}",
                field="required_market_state_dimensions",
            )
        )
    for evidence_key in _DEFAULT_REQUIRED_EVIDENCE_KEYS:
        if evidence_key not in spec.required_evidence_keys:
            issues.append(
                StrategySpecIssue(
                    strategy_id=spec.strategy_id,
                    code=STRATEGY_SPEC_UNSAFE_EVIDENCE,
                    severity="WARNING",
                    message=f"recommended evidence key missing: {evidence_key}",
                    field="required_evidence_keys",
                )
            )
    return tuple(issues)


def _coerce_spec(spec: StrategySpec | Mapping[str, Any]) -> StrategySpec:
    if isinstance(spec, StrategySpec):
        return _normalized_spec(spec)
    if not isinstance(spec, Mapping):
        return StrategySpec(
            strategy_id="",
            name="",
            family="",
            module_path="",
            callable_name="",
            instruments=(),
            declared_regimes=(),
            direction_capabilities=(),
            metadata={"coercion_error": f"unsupported spec type: {type(spec).__name__}"},
        )
    return _normalized_spec(
        StrategySpec(
            strategy_id=str(spec.get("strategy_id") or ""),
            name=str(spec.get("name") or ""),
            family=str(spec.get("family") or ""),
            module_path=str(spec.get("module_path") or ""),
            callable_name=str(spec.get("callable_name") or ""),
            instruments=_normalize_tuple(spec.get("instruments")),
            declared_regimes=_normalize_tuple(spec.get("declared_regimes")),
            blocked_regimes=_normalize_tuple(spec.get("blocked_regimes")),
            required_market_state_dimensions=_normalize_tuple(
                spec.get("required_market_state_dimensions") or _REQUIRED_MARKET_STATE_DIMENSIONS
            ),
            required_evidence_keys=_normalize_tuple(spec.get("required_evidence_keys") or _DEFAULT_REQUIRED_EVIDENCE_KEYS),
            direction_capabilities=_normalize_tuple(spec.get("direction_capabilities")),
            min_market_state_confidence=_safe_confidence(spec.get("min_market_state_confidence")),
            description=str(spec.get("description") or ""),
            metadata=_safe_dict(spec.get("metadata")),
        )
    )


def _normalized_spec(spec: StrategySpec) -> StrategySpec:
    return StrategySpec(
        strategy_id=_normalize_id(spec.strategy_id),
        name=str(spec.name or "").strip(),
        family=str(spec.family or "").strip().upper(),
        module_path=str(spec.module_path or "").strip(),
        callable_name=str(spec.callable_name or "").strip(),
        instruments=_normalize_tuple(spec.instruments),
        declared_regimes=_normalize_tuple(spec.declared_regimes),
        blocked_regimes=_normalize_tuple(spec.blocked_regimes),
        required_market_state_dimensions=_normalize_tuple(spec.required_market_state_dimensions),
        required_evidence_keys=_normalize_tuple(spec.required_evidence_keys),
        direction_capabilities=_normalize_tuple(spec.direction_capabilities),
        min_market_state_confidence=_safe_confidence(spec.min_market_state_confidence),
        description=str(spec.description or "").strip(),
        metadata=_safe_dict(spec.metadata),
        read_only=True,
        append=False,
        source=STRATEGY_SPEC_SOURCE,
    )


def _normalize_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, Iterable):
        values = tuple(value)
    else:
        values = (value,)
    return tuple(str(item).strip().upper() for item in values if str(item).strip())


def _normalize_id(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _safe_confidence(value: Any) -> float:
    try:
        return round(float(value), 4)
    except Exception:
        return 0.0


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
    "DIRECTION_BUY_CALL",
    "DIRECTION_BUY_PUT",
    "DIRECTION_CALL",
    "DIRECTION_NEUTRAL",
    "DIRECTION_PUT",
    "FAMILY_BREAKOUT",
    "FAMILY_ENSEMBLE",
    "FAMILY_EVENT",
    "FAMILY_EXPIRY",
    "FAMILY_MEAN_REVERSION",
    "FAMILY_VWAP",
    "STRATEGY_SPEC_DUPLICATE_ID",
    "STRATEGY_SPEC_EMPTY_REGISTRY",
    "STRATEGY_SPEC_INVALID",
    "STRATEGY_SPEC_MISSING_FIELD",
    "STRATEGY_SPEC_SCHEMA_VERSION",
    "STRATEGY_SPEC_SOURCE",
    "STRATEGY_SPEC_UNKNOWN_REGIME",
    "STRATEGY_SPEC_UNSAFE_EVIDENCE",
    "STRATEGY_SPEC_UNSAFE_REGIME",
    "StrategySpec",
    "StrategySpecIssue",
    "StrategySpecRegistry",
    "build_default_strategy_specs",
    "build_strategy_spec_registry",
    "get_strategy_spec",
]
