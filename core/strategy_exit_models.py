"""Pure strategy-specific exit model contract for EDGE-77."""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.candidate_intent import CandidateIntent, INTENT_TYPE_ENTRY
from core.candidate_intent_pool import CandidateIntentPoolReport, build_candidate_intent_pool

STRATEGY_EXIT_MODEL_SCHEMA_VERSION = 1
STRATEGY_EXIT_MODEL_SOURCE = "strategy_specific_exit_model_v1"

STRATEGY_EXIT_MODEL_STATUS_READY = "EXIT_MODEL_READY"
STRATEGY_EXIT_MODEL_STATUS_BLOCKED = "EXIT_MODEL_BLOCKED"

EXIT_MODEL_EMPTY_CANDIDATES = "exit_model_empty_candidates"
EXIT_MODEL_CANDIDATE_NOT_POOL_ELIGIBLE = "exit_model_candidate_not_pool_eligible"
EXIT_MODEL_NON_ENTRY_INTENT = "exit_model_non_entry_intent"
EXIT_MODEL_UNSUPPORTED_FAMILY = "exit_model_unsupported_family"
EXIT_MODEL_UNSUPPORTED_DIRECTION = "exit_model_unsupported_direction"
EXIT_MODEL_OPTION_CONFIRMATION_REQUIRED = "exit_model_option_confirmation_required"
EXIT_MODEL_OPTION_CONFIRMATION_NOT_READY = "exit_model_option_confirmation_not_ready"
EXIT_MODEL_INVALID_POLICY = "exit_model_invalid_policy"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_BUY_OPTION_DIRECTIONS = {"BUY_CALL", "BUY_PUT", "CALL", "PUT"}


@dataclass(frozen=True)
class ExitPolicySpec:
    family: str
    model_type: str
    initial_risk_pct: float
    profit_take_pct: float
    trailing_activation_pct: float
    max_hold_seconds: int
    review_interval_seconds: int
    invalidation_signals: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class StrategyExitModel:
    model_id: str
    candidate_intent_id: str
    strategy_id: str
    family: str
    direction: str
    status: str
    policy: dict[str, Any]
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = STRATEGY_EXIT_MODEL_SOURCE

    @property
    def ready(self) -> bool:
        return self.status == STRATEGY_EXIT_MODEL_STATUS_READY and not self.blockers

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
            "model_id": self.model_id,
            "candidate_intent_id": self.candidate_intent_id,
            "strategy_id": self.strategy_id,
            "family": self.family,
            "direction": self.direction,
            "status": self.status,
            "ready": self.ready,
            "policy": dict(self.policy),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class StrategyExitModelReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    exit_models: tuple[StrategyExitModel, ...]
    pool_report: CandidateIntentPoolReport
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
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    @property
    def valid(self) -> bool:
        return not self.blockers and self.pool_report.valid

    @property
    def ready_models(self) -> tuple[StrategyExitModel, ...]:
        return tuple(model for model in self.exit_models if model.ready)

    @property
    def blocked_models(self) -> tuple[StrategyExitModel, ...]:
        return tuple(model for model in self.exit_models if not model.ready)

    @property
    def exit_model_ready(self) -> bool:
        return self.valid and bool(self.ready_models)

    @property
    def ready_candidate_intent_ids(self) -> tuple[str, ...]:
        return tuple(model.candidate_intent_id for model in self.ready_models)

    @property
    def blocked_candidate_intent_ids(self) -> tuple[str, ...]:
        return tuple(model.candidate_intent_id for model in self.blocked_models)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "exit_model_ready": self.exit_model_ready,
            "model_count": len(self.exit_models),
            "ready_count": len(self.ready_models),
            "blocked_count": len(self.blocked_models),
            "ready_candidate_intent_ids": list(self.ready_candidate_intent_ids),
            "blocked_candidate_intent_ids": list(self.blocked_candidate_intent_ids),
            "exit_models": [model.to_payload() for model in self.exit_models],
            "pool_report": self.pool_report.to_payload(),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        _mark_non_action(payload)
        return payload


def build_strategy_specific_exit_models(
    candidates: Iterable[CandidateIntent | Mapping[str, Any]],
    *,
    option_confirmation_report: Any | None = None,
    require_option_confirmation: bool = False,
    source: str = STRATEGY_EXIT_MODEL_SOURCE,
) -> StrategyExitModelReport:
    pool_report = build_candidate_intent_pool(tuple(candidates or ()))
    confirmed_ids = _confirmed_ids(option_confirmation_report)
    confirmation_supplied = option_confirmation_report is not None

    models = [
        _model_for_intent(
            entry.intent,
            blockers=(),
            warnings=entry.warnings,
            confirmed_ids=confirmed_ids,
            confirmation_supplied=confirmation_supplied,
            require_option_confirmation=require_option_confirmation,
            source=source,
        )
        for entry in pool_report.eligible_intents
    ]
    models.extend(
        _blocked_model(
            entry.intent,
            blockers=_dedupe(
                (
                    EXIT_MODEL_CANDIDATE_NOT_POOL_ELIGIBLE,
                    *entry.blockers,
                )
            ),
            warnings=entry.warnings,
            source=source,
        )
        for entry in pool_report.blocked_intents
    )

    return StrategyExitModelReport(
        schema_version=STRATEGY_EXIT_MODEL_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        exit_models=tuple(sorted(models, key=lambda item: item.model_id)),
        pool_report=pool_report,
        blockers=() if models else (EXIT_MODEL_EMPTY_CANDIDATES,),
        warnings=_dedupe((*pool_report.warnings,)),
        metadata={
            "model": STRATEGY_EXIT_MODEL_SOURCE,
            "scope": "pure_strategy_specific_exit_model_contract_no_runtime_wiring",
            "supported_families": sorted(_POLICIES),
            "requires_option_confirmation": bool(require_option_confirmation),
            "option_confirmation_supplied": confirmation_supplied,
            "does_not_import_strategy_modules": True,
            "does_not_execute_strategy_callables": True,
            "does_not_rank_candidates": True,
            "does_not_score_edge": True,
            "does_not_touch_runtime": True,
            "does_not_emit_lifecycle_mutation": True,
        },
    )


def _model_for_intent(
    intent: CandidateIntent,
    *,
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
    confirmed_ids: frozenset[str],
    confirmation_supplied: bool,
    require_option_confirmation: bool,
    source: str,
) -> StrategyExitModel:
    model_blockers = list(blockers)
    if intent.intent_type != INTENT_TYPE_ENTRY:
        model_blockers.append(EXIT_MODEL_NON_ENTRY_INTENT)
    if _direction_key(intent.direction) not in _BUY_OPTION_DIRECTIONS:
        model_blockers.append(EXIT_MODEL_UNSUPPORTED_DIRECTION)
    family = _family_key(intent.family)
    policy = _POLICIES.get(family)
    if policy is None:
        model_blockers.append(EXIT_MODEL_UNSUPPORTED_FAMILY)
    if require_option_confirmation and not confirmation_supplied:
        model_blockers.append(EXIT_MODEL_OPTION_CONFIRMATION_REQUIRED)
    if confirmation_supplied and intent.candidate_intent_id not in confirmed_ids:
        model_blockers.append(EXIT_MODEL_OPTION_CONFIRMATION_NOT_READY)

    blockers_tuple = _dedupe(model_blockers)
    if blockers_tuple or policy is None:
        return _blocked_model(intent, blockers=blockers_tuple, warnings=warnings, source=source)

    payload = _policy_payload(policy, intent)
    if not _policy_valid(payload):
        return _blocked_model(intent, blockers=(EXIT_MODEL_INVALID_POLICY,), warnings=warnings, source=source)
    return StrategyExitModel(
        model_id=_model_id(intent),
        candidate_intent_id=intent.candidate_intent_id,
        strategy_id=intent.strategy_id,
        family=family,
        direction=intent.direction,
        status=STRATEGY_EXIT_MODEL_STATUS_READY,
        policy=payload,
        warnings=_dedupe(warnings),
        metadata=_model_metadata(intent, policy),
        source=source,
    )


def _blocked_model(
    intent: CandidateIntent,
    *,
    blockers: tuple[str, ...],
    source: str,
    warnings: tuple[str, ...] = (),
) -> StrategyExitModel:
    return StrategyExitModel(
        model_id=_model_id(intent),
        candidate_intent_id=intent.candidate_intent_id,
        strategy_id=intent.strategy_id,
        family=_family_key(intent.family),
        direction=intent.direction,
        status=STRATEGY_EXIT_MODEL_STATUS_BLOCKED,
        policy={},
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        metadata={
            "candidate_intent_id": intent.candidate_intent_id,
            "strategy_id": intent.strategy_id,
            "family": intent.family,
            "intent_type": intent.intent_type,
            "does_not_touch_runtime": True,
            "does_not_emit_lifecycle_mutation": True,
        },
        source=source,
    )


def _policy_payload(policy: ExitPolicySpec, intent: CandidateIntent) -> dict[str, Any]:
    return {
        "family": policy.family,
        "model_type": policy.model_type,
        "direction_profile": _direction_profile(intent.direction),
        "initial_risk_pct": float(policy.initial_risk_pct),
        "profit_take_pct": float(policy.profit_take_pct),
        "trailing_activation_pct": float(policy.trailing_activation_pct),
        "max_hold_seconds": int(policy.max_hold_seconds),
        "review_interval_seconds": int(policy.review_interval_seconds),
        "invalidation_signals": list(policy.invalidation_signals),
        "notes": list(policy.notes),
        "read_only_guidance_only": True,
    }


def _policy_valid(policy: Mapping[str, Any]) -> bool:
    numeric_keys = (
        "initial_risk_pct",
        "profit_take_pct",
        "trailing_activation_pct",
        "max_hold_seconds",
        "review_interval_seconds",
    )
    try:
        return all(float(policy[key]) > 0 for key in numeric_keys)
    except (KeyError, TypeError, ValueError):
        return False


def _model_metadata(intent: CandidateIntent, policy: ExitPolicySpec) -> dict[str, Any]:
    return {
        "candidate_intent_id": intent.candidate_intent_id,
        "strategy_id": intent.strategy_id,
        "family": policy.family,
        "intent_type": intent.intent_type,
        "candidate_trigger": intent.trigger,
        "candidate_invalidation": intent.invalidation,
        "does_not_rank_candidates": True,
        "does_not_score_edge": True,
        "does_not_touch_runtime": True,
        "does_not_emit_lifecycle_mutation": True,
    }


def _confirmed_ids(report: Any | None) -> frozenset[str]:
    if report is None:
        return frozenset()
    ids = getattr(report, "confirmed_candidate_intent_ids", None)
    if ids is None and isinstance(report, Mapping):
        ids = report.get("confirmed_candidate_intent_ids")
    if ids is None and hasattr(report, "to_payload"):
        payload = report.to_payload()
        if isinstance(payload, Mapping):
            ids = payload.get("confirmed_candidate_intent_ids")
    try:
        return frozenset(_candidate_key(item) for item in ids or ())
    except TypeError:
        return frozenset()


def _direction_profile(direction: str) -> str:
    direction_key = _direction_key(direction)
    if direction_key in {"BUY_CALL", "CALL"}:
        return "LONG_CALL_PREMIUM"
    if direction_key in {"BUY_PUT", "PUT"}:
        return "LONG_PUT_PREMIUM"
    return "UNSUPPORTED_DIRECTION"


def _direction_key(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _family_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _candidate_key(value: Any) -> str:
    return _family_key(value)


def _model_id(intent: CandidateIntent) -> str:
    return _candidate_key(f"{intent.candidate_intent_id}:exit_model")


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ORDER_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


_POLICIES: dict[str, ExitPolicySpec] = {
    "breakout": ExitPolicySpec(
        family="breakout",
        model_type="trend_continuation_long_option",
        initial_risk_pct=0.35,
        profit_take_pct=0.85,
        trailing_activation_pct=0.45,
        max_hold_seconds=1800,
        review_interval_seconds=60,
        invalidation_signals=(
            "price_returns_inside_breakout_range",
            "volume_confirmation_fades",
            "option_confirmation_not_ready",
            "feed_health_not_ready",
        ),
        notes=(
            "breakout_needs_room_for_continuation",
            "trail_only_after_extension_confirms",
        ),
    ),
    "vwap": ExitPolicySpec(
        family="vwap",
        model_type="vwap_trend_follow_long_option",
        initial_risk_pct=0.30,
        profit_take_pct=0.65,
        trailing_activation_pct=0.35,
        max_hold_seconds=1500,
        review_interval_seconds=60,
        invalidation_signals=(
            "price_returns_to_vwap_neutral_zone",
            "vwap_slope_loses_confirmation",
            "option_confirmation_not_ready",
            "feed_health_not_ready",
        ),
        notes=(
            "vwap_model_respects_mean_anchor_retests",
            "do_not_hold_when_vwap_context_turns_neutral",
        ),
    ),
    "mean_reversion": ExitPolicySpec(
        family="mean_reversion",
        model_type="anchor_reversion_long_option",
        initial_risk_pct=0.25,
        profit_take_pct=0.45,
        trailing_activation_pct=0.25,
        max_hold_seconds=900,
        review_interval_seconds=45,
        invalidation_signals=(
            "price_extends_away_from_anchor",
            "oscillator_confirmation_fails",
            "option_confirmation_not_ready",
            "feed_health_not_ready",
        ),
        notes=(
            "mean_reversion_requires_faster_feedback",
            "take_profit_before_reversion_edge_decays",
        ),
    ),
    "zero_hero": ExitPolicySpec(
        family="zero_hero",
        model_type="expiry_momentum_long_option",
        initial_risk_pct=0.45,
        profit_take_pct=1.10,
        trailing_activation_pct=0.60,
        max_hold_seconds=300,
        review_interval_seconds=15,
        invalidation_signals=(
            "premium_expansion_fails",
            "underlying_momentum_fades",
            "option_confirmation_not_ready",
            "feed_health_not_ready",
        ),
        notes=(
            "expiry_premium_decay_requires_fast_review",
            "zero_hero_exit_model_is_aggressive_by_design",
        ),
    ),
}


__all__ = [
    "EXIT_MODEL_CANDIDATE_NOT_POOL_ELIGIBLE",
    "EXIT_MODEL_EMPTY_CANDIDATES",
    "EXIT_MODEL_INVALID_POLICY",
    "EXIT_MODEL_NON_ENTRY_INTENT",
    "EXIT_MODEL_OPTION_CONFIRMATION_NOT_READY",
    "EXIT_MODEL_OPTION_CONFIRMATION_REQUIRED",
    "EXIT_MODEL_UNSUPPORTED_DIRECTION",
    "EXIT_MODEL_UNSUPPORTED_FAMILY",
    "STRATEGY_EXIT_MODEL_SCHEMA_VERSION",
    "STRATEGY_EXIT_MODEL_SOURCE",
    "STRATEGY_EXIT_MODEL_STATUS_BLOCKED",
    "STRATEGY_EXIT_MODEL_STATUS_READY",
    "ExitPolicySpec",
    "StrategyExitModel",
    "StrategyExitModelReport",
    "build_strategy_specific_exit_models",
]
