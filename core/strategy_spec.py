"""Read-only StrategySpec registry contract for EDGE-65."""

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
FAMILY_PAIR_ARBITRAGE = "PAIR_ARBITRAGE"
FAMILY_VWAP_ORB = "VWAP_ORB"
FAMILY_MOVEMENT = "MOVEMENT"
FAMILY_PRO_STRATEGY = "PRO_STRATEGY"

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
_UNSAFE_REGIMES = {REGIME_UNKNOWN, REGIME_OUT_OF_SESSION, REGIME_LIQUIDITY_STRESSED, REGIME_VOLATILITY_STRESSED}
_REQUIRED_MARKET_STATE_DIMENSIONS = ("trend", "volatility", "breadth", "liquidity", "session")
_DEFAULT_REQUIRED_EVIDENCE_KEYS = ("market_state", "regime_state", "feed_health_truth", "quote_truth")
_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    name: str
    family: str
    module_path: str
    callable_name: str
    instruments: tuple[str, ...]
    declared_regimes: tuple[str, ...]
    preferred_regimes: tuple[str, ...] = field(default_factory=tuple)
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
            "preferred_regimes": list(self.preferred_regimes),
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
    unsafe = tuple(sorted(_UNSAFE_REGIMES))
    return (
        StrategySpec(
            "ensemble",
            "Ensemble Signal",
            FAMILY_ENSEMBLE,
            "strategies.ensemble",
            "ensemble_signal",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND, REGIME_HIGH_VOLATILITY, REGIME_MIXED_UNCERTAIN),
            preferred_regimes=(REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND),
            blocked_regimes=unsafe,
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.55,
            description="Aggregates trend, ORB, mean-reversion, micro-pattern, and event signals.",
        ),
        StrategySpec(
            "vwap_orb",
            "VWAP ORB",
            FAMILY_VWAP_ORB,
            "strategies.vwap_orb",
            "vwap_orb_strategy",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_BULL_TREND, REGIME_RANGE_BOUND, REGIME_OPENING_DISCOVERY),
            preferred_regimes=(REGIME_OPENING_DISCOVERY, REGIME_BULL_TREND),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "vwap_state",
                "trend_confirmation",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.65,
        ),
        StrategySpec(
            "nifty_intraday",
            "NIFTY Intraday VWAP",
            FAMILY_VWAP,
            "strategies.nifty_intraday",
            "generate_signal",
            ("NIFTY",),
            (REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND),
            preferred_regimes=(REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND),
            blocked_regimes=unsafe,
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.60,
        ),
        StrategySpec(
            "banknifty_intraday",
            "BANKNIFTY Intraday VWAP",
            FAMILY_VWAP,
            "strategies.banknifty_intraday",
            "generate_signal",
            ("BANKNIFTY",),
            (REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND),
            preferred_regimes=(REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND),
            blocked_regimes=unsafe,
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.60,
        ),
        StrategySpec(
            "sensex_intraday",
            "SENSEX Intraday VWAP",
            FAMILY_VWAP,
            "strategies.sensex_intraday",
            "generate_signal",
            ("SENSEX",),
            (REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND),
            preferred_regimes=(REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND),
            blocked_regimes=unsafe,
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.60,
        ),
        StrategySpec(
            "zero_hero_expiry",
            "Zero Hero Expiry",
            FAMILY_EXPIRY,
            "strategies.zero_hero",
            "generate_signal",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_HIGH_VOLATILITY),
            preferred_regimes=(REGIME_HIGH_VOLATILITY,),
            blocked_regimes=unsafe,
            direction_capabilities=(DIRECTION_CALL, DIRECTION_PUT, DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.70,
        ),
        StrategySpec(
            "pairs_arbitrage",
            "Pairs Arbitrage",
            FAMILY_PAIR_ARBITRAGE,
            "strategies.pairs_arbitrage",
            "generate_signal",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_RANGE_BOUND, REGIME_MIXED_UNCERTAIN),
            preferred_regimes=(REGIME_RANGE_BOUND,),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "cross_asset_health",
                "spread_truth",
                "beta_truth",
                "cointegration_truth",
                "leg_freshness_a",
                "leg_freshness_b",
            ),
            direction_capabilities=("LONG_SPREAD", "SHORT_SPREAD"),
            min_market_state_confidence=0.75,
        ),
        StrategySpec(
            "opening_range_retest",
            "Opening Range Retest",
            FAMILY_MOVEMENT,
            "strategies.movement.opening_range_breakout",
            "generate_opening_range_retest_candidates",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_BULL_TREND, REGIME_RANGE_BOUND, REGIME_OPENING_DISCOVERY),
            preferred_regimes=(REGIME_OPENING_DISCOVERY, REGIME_BULL_TREND),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "session_state",
                "structure_state",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.65,
        ),
        StrategySpec(
            "trend_pullback",
            "Trend Pullback",
            FAMILY_MOVEMENT,
            "strategies.movement.trend_pullback",
            "generate_trend_pullback_candidates",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND),
            preferred_regimes=(REGIME_BULL_TREND, REGIME_BEAR_TREND),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "anchor_state",
                "retracement_state",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.65,
        ),
        StrategySpec(
            "mean_reversion_extension",
            "Mean Reversion Extension",
            FAMILY_MEAN_REVERSION,
            "strategies.movement.mean_reversion_extension",
            "generate_mean_reversion_extension_candidates",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_RANGE_BOUND, REGIME_MIXED_UNCERTAIN),
            preferred_regimes=(REGIME_RANGE_BOUND,),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "mean_reversion_anchor",
                "oscillator_confirmation",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.60,
        ),
        StrategySpec(
            "opening_drive",
            "Opening Drive",
            FAMILY_MOVEMENT,
            "strategies.movement.opening_drive",
            "generate_opening_drive_candidates",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_BULL_TREND, REGIME_RANGE_BOUND, REGIME_OPENING_DISCOVERY),
            preferred_regimes=(REGIME_OPENING_DISCOVERY, REGIME_BULL_TREND),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "session_state",
                "structure_state",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.65,
        ),
        StrategySpec(
            "compression_breakout",
            "Compression Breakout",
            FAMILY_MOVEMENT,
            "strategies.movement.compression_breakout",
            "generate_compression_breakout_candidates",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_BULL_TREND, REGIME_RANGE_BOUND, REGIME_MIXED_UNCERTAIN),
            preferred_regimes=(REGIME_BULL_TREND, REGIME_RANGE_BOUND),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "compression_state",
                "structure_state",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.62,
        ),
        StrategySpec(
            "failed_breakout_trap",
            "Failed Breakout Trap",
            FAMILY_MOVEMENT,
            "strategies.movement.failed_breakout_trap",
            "generate_failed_breakout_trap_candidates",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_BEAR_TREND, REGIME_RANGE_BOUND, REGIME_MIXED_UNCERTAIN),
            preferred_regimes=(REGIME_RANGE_BOUND, REGIME_MIXED_UNCERTAIN),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "trap_state",
                "structure_state",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.62,
        ),
        StrategySpec(
            "exhaustion_reversal",
            "Exhaustion Reversal",
            FAMILY_MOVEMENT,
            "strategies.movement.exhaustion_reversal",
            "generate_exhaustion_reversal_candidates",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_RANGE_BOUND, REGIME_HIGH_VOLATILITY, REGIME_MIXED_UNCERTAIN),
            preferred_regimes=(REGIME_HIGH_VOLATILITY, REGIME_RANGE_BOUND),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "volatility_state",
                "trap_state",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.64,
        ),
        StrategySpec(
            "late_day_momentum",
            "Late Day Momentum",
            FAMILY_MOVEMENT,
            "strategies.movement.late_day_momentum",
            "generate_late_day_momentum_candidates",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_OPENING_DISCOVERY),
            preferred_regimes=(REGIME_BULL_TREND, REGIME_BEAR_TREND),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "session_state",
                "momentum_state",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.62,
        ),
        StrategySpec(
            "vwap_reclaim_rejection",
            "VWAP Reclaim Rejection",
            FAMILY_MOVEMENT,
            "strategies.movement.vwap_reclaim",
            "generate_vwap_reclaim_rejection_candidates",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_RANGE_BOUND, REGIME_BULL_TREND, REGIME_BEAR_TREND),
            preferred_regimes=(REGIME_RANGE_BOUND,),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "anchor_state",
                "reclaim_state",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.62,
        ),
        StrategySpec(
            "option_pressure_confirmation",
            "Option Pressure Confirmation",
            FAMILY_MOVEMENT,
            "strategies.movement.option_pressure",
            "generate_option_pressure_candidates",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_HIGH_VOLATILITY, REGIME_MIXED_UNCERTAIN),
            preferred_regimes=(REGIME_HIGH_VOLATILITY, REGIME_MIXED_UNCERTAIN),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "order_flow",
                "depth_truth",
                "oi_delta",
                "iv_truth",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.70,
        ),
        StrategySpec(
            "event_volatility_expansion",
            "Event Volatility Expansion",
            FAMILY_EVENT,
            "strategies.movement.event_volatility_expansion",
            "generate_event_volatility_expansion_candidates",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_HIGH_VOLATILITY, REGIME_MIXED_UNCERTAIN, REGIME_OPENING_DISCOVERY),
            preferred_regimes=(REGIME_HIGH_VOLATILITY, REGIME_MIXED_UNCERTAIN),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "event_state",
                "volatility_state",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.70,
        ),
        StrategySpec(
            "no_trade_chop",
            "No Trade Chop",
            FAMILY_EVENT,
            "strategies.movement.no_trade_chop",
            "generate_no_trade_candidates",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_RANGE_BOUND, REGIME_MIXED_UNCERTAIN),
            preferred_regimes=(REGIME_RANGE_BOUND, REGIME_MIXED_UNCERTAIN),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "feed_health_truth",
            ),
            direction_capabilities=(DIRECTION_NEUTRAL,),
            min_market_state_confidence=0.50,
        ),
        StrategySpec(
            "volatility_trend",
            "Volatility Scaled Trend",
            FAMILY_EVENT,
            "strategies.volatility_trend",
            "volatility_scaled_trend_strategy",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_HIGH_VOLATILITY, REGIME_MIXED_UNCERTAIN),
            preferred_regimes=(REGIME_HIGH_VOLATILITY, REGIME_BULL_TREND, REGIME_BEAR_TREND),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "atr_state",
                "cross_asset_health",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.68,
            description="Volatility-scaled trend strategy with cross-asset confirmation.",
        ),
        StrategySpec(
            "pro_strategy",
            "Pro Strategy Meta",
            FAMILY_PRO_STRATEGY,
            "strategies.pro_layer.pro_strategy_engine",
            "ProStrategyEngine",
            ("NIFTY", "BANKNIFTY", "SENSEX"),
            (REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND, REGIME_HIGH_VOLATILITY, REGIME_MIXED_UNCERTAIN, REGIME_OPENING_DISCOVERY),
            preferred_regimes=(REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE_BOUND),
            blocked_regimes=unsafe,
            required_evidence_keys=(
                "market_state",
                "regime_state",
                "signal_quality",
                "candidate_truth",
                "family_truth",
                "feed_health_truth",
                "quote_truth",
            ),
            direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
            min_market_state_confidence=0.75,
            description="Meta-layer that aggregates orthogonal pro signals and must inherit child-family freshness and contract checks.",
        ),
    )


def build_strategy_spec_registry(
    specs: Iterable[StrategySpec | Mapping[str, Any]] | None = None,
    *,
    source: str = STRATEGY_SPEC_SOURCE,
) -> StrategySpecRegistry:
    normalized = tuple(_coerce_spec(spec) for spec in (specs if specs is not None else build_default_strategy_specs()))
    issues = _validate_specs(normalized)
    return StrategySpecRegistry(
        schema_version=STRATEGY_SPEC_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        specs=normalized,
        issues=issues,
        blockers=_dedupe_sorted(issue.code for issue in issues if issue.severity == "BLOCKER"),
        warnings=_dedupe_sorted(issue.code for issue in issues if issue.severity == "WARNING"),
        metadata={
            "model": STRATEGY_SPEC_SOURCE,
            "scope": "read_only_strategy_spec_registry_no_eligibility_replacement",
            "does_not_import_strategy_modules": True,
        },
    )


def get_strategy_spec(strategy_id: str, registry: StrategySpecRegistry | None = None) -> StrategySpec | None:
    return (registry or build_strategy_spec_registry()).get(strategy_id)


def _validate_specs(specs: tuple[StrategySpec, ...]) -> tuple[StrategySpecIssue, ...]:
    if not specs:
        return (
            StrategySpecIssue(None, STRATEGY_SPEC_EMPTY_REGISTRY, "BLOCKER", "strategy registry cannot be empty"),
        )
    issues: list[StrategySpecIssue] = []
    seen: dict[str, int] = {}
    for spec in specs:
        seen[spec.strategy_id] = seen.get(spec.strategy_id, 0) + 1
    for strategy_id, count in sorted(seen.items()):
        if count > 1:
            issues.append(StrategySpecIssue(strategy_id, STRATEGY_SPEC_DUPLICATE_ID, "BLOCKER", "strategy_id must be unique", "strategy_id"))
    for spec in specs:
        issues.extend(_validate_required_fields(spec))
        issues.extend(_validate_regimes(spec))
        issues.extend(_validate_evidence_contract(spec))
    return tuple(issues)


def _validate_required_fields(spec: StrategySpec) -> tuple[StrategySpecIssue, ...]:
    issues: list[StrategySpecIssue] = []
    for field_name in ("strategy_id", "name", "family", "module_path", "callable_name"):
        if not getattr(spec, field_name):
            issues.append(StrategySpecIssue(spec.strategy_id or None, STRATEGY_SPEC_MISSING_FIELD, "BLOCKER", f"{field_name} is required", field_name))
    for field_name in ("instruments", "declared_regimes", "direction_capabilities"):
        if not getattr(spec, field_name):
            issues.append(StrategySpecIssue(spec.strategy_id or None, STRATEGY_SPEC_MISSING_FIELD, "BLOCKER", f"{field_name} must not be empty", field_name))
    if spec.min_market_state_confidence < 0.0 or spec.min_market_state_confidence > 1.0:
        issues.append(StrategySpecIssue(spec.strategy_id, STRATEGY_SPEC_INVALID, "BLOCKER", "min_market_state_confidence must be between 0 and 1", "min_market_state_confidence"))
    return tuple(issues)


def _validate_regimes(spec: StrategySpec) -> tuple[StrategySpecIssue, ...]:
    issues: list[StrategySpecIssue] = []
    for regime in (*spec.declared_regimes, *spec.blocked_regimes):
        if regime not in _VALID_REGIMES:
            issues.append(StrategySpecIssue(spec.strategy_id, STRATEGY_SPEC_UNKNOWN_REGIME, "BLOCKER", f"unknown regime: {regime}", "declared_regimes"))
    for regime in (regime for regime in spec.declared_regimes if regime in _UNSAFE_REGIMES):
        issues.append(StrategySpecIssue(spec.strategy_id, STRATEGY_SPEC_UNSAFE_REGIME, "BLOCKER", f"unsafe regime cannot be declared tradable metadata: {regime}", "declared_regimes"))
    for regime in (regime for regime in _UNSAFE_REGIMES if regime not in spec.blocked_regimes):
        issues.append(StrategySpecIssue(spec.strategy_id, STRATEGY_SPEC_UNSAFE_REGIME, "WARNING", f"unsafe regime should be explicitly blocked: {regime}", "blocked_regimes"))
    return tuple(issues)


def _validate_evidence_contract(spec: StrategySpec) -> tuple[StrategySpecIssue, ...]:
    issues: list[StrategySpecIssue] = []
    dimensions = _normalize_lower_tuple(spec.required_market_state_dimensions)
    evidence = _normalize_lower_tuple(spec.required_evidence_keys)
    for dimension in _REQUIRED_MARKET_STATE_DIMENSIONS:
        if dimension not in dimensions:
            issues.append(StrategySpecIssue(spec.strategy_id, STRATEGY_SPEC_UNSAFE_EVIDENCE, "BLOCKER", f"missing required market-state dimension: {dimension}", "required_market_state_dimensions"))
    for evidence_key in _DEFAULT_REQUIRED_EVIDENCE_KEYS:
        if evidence_key not in evidence:
            issues.append(StrategySpecIssue(spec.strategy_id, STRATEGY_SPEC_UNSAFE_EVIDENCE, "WARNING", f"recommended evidence key missing: {evidence_key}", "required_evidence_keys"))
    return tuple(issues)


def _coerce_spec(spec: StrategySpec | Mapping[str, Any]) -> StrategySpec:
    if isinstance(spec, StrategySpec):
        return _normalized_spec(spec)
    if not isinstance(spec, Mapping):
        return _normalized_spec(StrategySpec("", "", "", "", "", (), (), metadata={"coercion_error": type(spec).__name__}))
    return _normalized_spec(
        StrategySpec(
            strategy_id=str(spec.get("strategy_id") or ""),
            name=str(spec.get("name") or ""),
            family=str(spec.get("family") or ""),
            module_path=str(spec.get("module_path") or ""),
            callable_name=str(spec.get("callable_name") or ""),
            instruments=_normalize_upper_tuple(spec.get("instruments")),
            declared_regimes=_normalize_upper_tuple(spec.get("declared_regimes")),
            preferred_regimes=_normalize_upper_tuple(spec.get("preferred_regimes")),
            blocked_regimes=_normalize_upper_tuple(spec.get("blocked_regimes")),
            required_market_state_dimensions=_normalize_lower_tuple(spec.get("required_market_state_dimensions") or _REQUIRED_MARKET_STATE_DIMENSIONS),
            required_evidence_keys=_normalize_lower_tuple(spec.get("required_evidence_keys") or _DEFAULT_REQUIRED_EVIDENCE_KEYS),
            direction_capabilities=_normalize_upper_tuple(spec.get("direction_capabilities")),
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
        instruments=_normalize_upper_tuple(spec.instruments),
        declared_regimes=_normalize_upper_tuple(spec.declared_regimes),
        preferred_regimes=_normalize_upper_tuple(spec.preferred_regimes),
        blocked_regimes=_normalize_upper_tuple(spec.blocked_regimes),
        required_market_state_dimensions=_normalize_lower_tuple(spec.required_market_state_dimensions),
        required_evidence_keys=_normalize_lower_tuple(spec.required_evidence_keys),
        direction_capabilities=_normalize_upper_tuple(spec.direction_capabilities),
        min_market_state_confidence=_safe_confidence(spec.min_market_state_confidence),
        description=str(spec.description or "").strip(),
        metadata=_safe_dict(spec.metadata),
        read_only=True,
        append=False,
        source=STRATEGY_SPEC_SOURCE,
    )


def _normalize_upper_tuple(value: Any) -> tuple[str, ...]:
    return tuple(item.upper() for item in _string_tuple(value))


def _normalize_lower_tuple(value: Any) -> tuple[str, ...]:
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
    "FAMILY_MOVEMENT",
    "FAMILY_PAIR_ARBITRAGE",
    "FAMILY_PRO_STRATEGY",
    "FAMILY_VWAP_ORB",
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
