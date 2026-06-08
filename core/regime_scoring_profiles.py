"""Read-only regime-aware scoring profile resolver.

This module prepares profile-adjusted component weights for future scoring work.
It does not score candidates, rank rows, submit orders, call brokers, touch depth
subscriptions, tune live thresholds, or change dashboard behavior.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.movement_regime import MovementRegimeResult, REGIME_LABELS
from core.opportunity_scoring import COMPONENT_WEIGHTS

PROFILE_SCHEMA_VERSION = 1
SECONDARY_REGIME_THRESHOLD = 0.55

PROFILE_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "TREND_UP": {
        "price_structure": 1.15,
        "option_confirmation": 1.12,
        "regime_alignment": 1.18,
        "timing": 1.08,
        "volatility": 0.90,
    },
    "TREND_DOWN": {
        "price_structure": 1.15,
        "option_confirmation": 1.12,
        "regime_alignment": 1.18,
        "timing": 1.08,
        "volatility": 0.90,
    },
    "RANGE": {
        "price_structure": 1.12,
        "liquidity": 1.08,
        "freshness": 1.08,
        "regime_alignment": 1.12,
        "volatility": 0.82,
    },
    "CHOP": {
        "liquidity": 1.20,
        "freshness": 1.20,
        "option_confirmation": 0.85,
        "price_structure": 0.80,
        "timing": 0.75,
        "confluence": 0.80,
    },
    "COMPRESSION": {
        "price_structure": 1.15,
        "option_confirmation": 1.10,
        "timing": 1.12,
        "volatility": 1.22,
        "confluence": 1.08,
    },
    "VOLATILITY_EXPANSION": {
        "volatility": 1.30,
        "freshness": 1.15,
        "liquidity": 1.15,
        "timing": 1.12,
        "price_structure": 0.95,
    },
    "TRAP_RISK": {
        "price_structure": 0.82,
        "option_confirmation": 1.18,
        "liquidity": 1.08,
        "freshness": 1.08,
        "confluence": 0.80,
        "timing": 0.88,
    },
    "EXHAUSTION_RISK": {
        "price_structure": 0.90,
        "option_confirmation": 1.14,
        "timing": 1.16,
        "freshness": 1.10,
        "confluence": 1.10,
        "regime_alignment": 0.92,
    },
    "EXPIRY_CONTEXT": {
        "liquidity": 1.22,
        "freshness": 1.18,
        "option_confirmation": 1.12,
        "volatility": 1.08,
        "price_structure": 0.92,
    },
    "INCONCLUSIVE": {
        "liquidity": 1.12,
        "freshness": 1.12,
        "price_structure": 0.90,
        "option_confirmation": 0.92,
        "timing": 0.88,
        "confluence": 0.90,
    },
}

PROFILE_RATIONALE: dict[str, tuple[str, ...]] = {
    "TREND_UP": (
        "trend_up_profile_prioritizes_price_structure_regime_alignment_and_call_confirmation",
        "trend_profile_keeps_volatility_secondary_to_directional_confirmation",
    ),
    "TREND_DOWN": (
        "trend_down_profile_prioritizes_price_structure_regime_alignment_and_put_confirmation",
        "trend_profile_keeps_volatility_secondary_to_directional_confirmation",
    ),
    "RANGE": (
        "range_profile_prioritizes_price_location_liquidity_and_freshness",
        "range_profile_reduces_volatility_weight_to_avoid_chasing_noise",
    ),
    "CHOP": (
        "chop_profile_prioritizes_liquidity_and_freshness_before_any_directional_score",
        "chop_profile_reduces_timing_price_structure_and_confluence_weight",
    ),
    "COMPRESSION": (
        "compression_profile_prioritizes_breakout_structure_timing_and_volatility_expansion",
        "compression_profile_requires_option_confirmation_before_promotion",
    ),
    "VOLATILITY_EXPANSION": (
        "volatility_expansion_profile_prioritizes_volatility_freshness_liquidity_and_timing",
        "volatility_expansion_profile_reduces_static_price_structure_weight",
    ),
    "TRAP_RISK": (
        "trap_risk_profile_reduces_price_structure_and_confluence_trust",
        "trap_risk_profile_requires_stronger_option_confirmation_and_freshness",
    ),
    "EXHAUSTION_RISK": (
        "exhaustion_profile_prioritizes_timing_freshness_and_confirmation",
        "exhaustion_profile_reduces_regime_alignment_trust_until_reversal_confirms",
    ),
    "EXPIRY_CONTEXT": (
        "expiry_profile_prioritizes_liquidity_freshness_and_option_confirmation",
        "expiry_profile_reduces_static_price_structure_weight_due_to_expiry_noise",
    ),
    "INCONCLUSIVE": (
        "inconclusive_profile_prioritizes_liquidity_and_freshness_safety",
        "inconclusive_profile_reduces_directional_components_until_regime_clarifies",
    ),
}

PROFILE_WARNINGS: dict[str, tuple[str, ...]] = {
    "CHOP": ("profile_chop_should_not_promote_directional_candidates",),
    "TRAP_RISK": ("profile_trap_risk_requires_extra_confirmation",),
    "EXHAUSTION_RISK": ("profile_exhaustion_risk_requires_reversal_confirmation",),
    "EXPIRY_CONTEXT": ("profile_expiry_context_requires_liquidity_and_freshness_guard",),
    "INCONCLUSIVE": ("profile_inconclusive_regime_requires_advisory_bias",),
}

PROFILE_RECOMMENDED_SCORE_CAPS: dict[str, float] = {
    "CHOP": 0.20,
    "TRAP_RISK": 0.45,
    "EXHAUSTION_RISK": 0.55,
    "EXPIRY_CONTEXT": 0.75,
    "INCONCLUSIVE": 0.35,
}

PROFILE_RECOMMENDED_PENALTIES: dict[str, dict[str, float]] = {
    "CHOP": {"chop_regime_penalty": 0.35},
    "TRAP_RISK": {"trap_risk_regime_penalty": 0.25},
    "EXHAUSTION_RISK": {"exhaustion_risk_regime_penalty": 0.15},
    "EXPIRY_CONTEXT": {"expiry_context_risk_penalty": 0.10},
    "INCONCLUSIVE": {"inconclusive_regime_penalty": 0.25},
}


@dataclass(frozen=True)
class RegimeScoringProfile:
    """Read-only score profile selected from a movement-regime result."""

    schema_version: int
    read_only: bool
    append: bool
    primary_regime: str
    selected_profiles: tuple[str, ...]
    regime_scores: dict[str, float]
    base_component_weights: dict[str, float]
    adjusted_component_weights: dict[str, float]
    weight_multipliers: dict[str, float]
    rationale: tuple[str, ...]
    warnings: tuple[str, ...]
    recommended_score_cap: float | None = None
    recommended_penalties: dict[str, float] = field(default_factory=dict)
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "is_order_action": False,
            "append": self.append,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
            "primary_regime": self.primary_regime,
            "selected_profiles": list(self.selected_profiles),
            "regime_scores": dict(self.regime_scores),
            "base_component_weights": dict(self.base_component_weights),
            "adjusted_component_weights": dict(self.adjusted_component_weights),
            "weight_multipliers": dict(self.weight_multipliers),
            "rationale": list(self.rationale),
            "warnings": list(self.warnings),
            "recommended_score_cap": self.recommended_score_cap,
            "recommended_penalties": dict(self.recommended_penalties),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def resolve_regime_scoring_profile(
    regime: MovementRegimeResult | Mapping[str, Any],
    *,
    base_component_weights: Mapping[str, float] | None = None,
    secondary_threshold: float = SECONDARY_REGIME_THRESHOLD,
) -> RegimeScoringProfile:
    """Resolve adjusted component weights for a movement regime.

    The output is advisory/read-only. It is meant for a future scoring PR to
    consume after this profile contract is stable.
    """

    regime_result = _coerce_regime(regime)
    base_weights = _normalize_weights(dict(base_component_weights or COMPONENT_WEIGHTS))
    selected_profiles = _selected_profiles(regime_result, secondary_threshold=secondary_threshold)
    multipliers = _combined_multipliers(selected_profiles, regime_result.scores)
    adjusted_weights = _normalize_weights(
        {component: base_weights[component] * multipliers.get(component, 1.0) for component in base_weights}
    )
    rationale = _merge_profile_texts(selected_profiles, PROFILE_RATIONALE)
    warnings = tuple(sorted(set(regime_result.warnings + _merge_profile_texts(selected_profiles, PROFILE_WARNINGS))))
    recommended_cap = _combined_recommended_cap(selected_profiles)
    recommended_penalties = _combined_recommended_penalties(selected_profiles)

    return RegimeScoringProfile(
        schema_version=PROFILE_SCHEMA_VERSION,
        read_only=True,
        append=False,
        primary_regime=regime_result.primary_regime,
        selected_profiles=selected_profiles,
        regime_scores=dict(regime_result.scores),
        base_component_weights=base_weights,
        adjusted_component_weights=adjusted_weights,
        weight_multipliers={key: _round(multipliers.get(key, 1.0)) for key in base_weights},
        rationale=rationale,
        warnings=warnings,
        recommended_score_cap=recommended_cap,
        recommended_penalties=recommended_penalties,
        metadata={
            "profile_resolver": "regime_scoring_profile_v1",
            "scope": "read_only_no_execution_no_ranking",
            "secondary_threshold": float(secondary_threshold),
            "base_weight_sum": _round(sum(base_weights.values())),
            "adjusted_weight_sum": _round(sum(adjusted_weights.values())),
        },
    )


def _coerce_regime(regime: MovementRegimeResult | Mapping[str, Any]) -> MovementRegimeResult:
    if isinstance(regime, MovementRegimeResult):
        return regime
    if isinstance(regime, Mapping):
        return MovementRegimeResult(**dict(regime))
    raise TypeError("regime_scoring_profile_expected_movement_regime")


def _selected_profiles(regime: MovementRegimeResult, *, secondary_threshold: float) -> tuple[str, ...]:
    selected: list[str] = [regime.primary_regime]
    for label in REGIME_LABELS:
        if label == regime.primary_regime:
            continue
        score = _safe_float(regime.scores.get(label), default=0.0)
        if score >= secondary_threshold:
            selected.append(label)
    return tuple(selected)


def _combined_multipliers(selected_profiles: tuple[str, ...], scores: Mapping[str, float]) -> dict[str, float]:
    multipliers = {component: 1.0 for component in COMPONENT_WEIGHTS}
    for profile in selected_profiles:
        profile_score = _safe_float(scores.get(profile), default=1.0 if profile == selected_profiles[0] else 0.0)
        influence = 1.0 if profile == selected_profiles[0] else max(0.25, profile_score)
        for component, multiplier in PROFILE_ADJUSTMENTS.get(profile, {}).items():
            if component not in multipliers:
                continue
            adjusted = 1.0 + ((float(multiplier) - 1.0) * influence)
            multipliers[component] *= adjusted
    return {component: _round(max(0.05, value)) for component, value in multipliers.items()}


def _normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    cleaned = {str(key): max(0.0, _safe_float(value, default=0.0)) for key, value in weights.items()}
    total = sum(cleaned.values())
    if total <= 0.0:
        raise ValueError("regime_scoring_profile_weights_sum_zero")
    return {key: _round(value / total) for key, value in sorted(cleaned.items())}


def _merge_profile_texts(selected_profiles: tuple[str, ...], source: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for profile in selected_profiles:
        for item in source.get(profile, ()):
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
    return tuple(out)


def _combined_recommended_cap(selected_profiles: tuple[str, ...]) -> float | None:
    caps = [PROFILE_RECOMMENDED_SCORE_CAPS[profile] for profile in selected_profiles if profile in PROFILE_RECOMMENDED_SCORE_CAPS]
    if not caps:
        return None
    return _round(min(caps))


def _combined_recommended_penalties(selected_profiles: tuple[str, ...]) -> dict[str, float]:
    penalties: dict[str, float] = {}
    for profile in selected_profiles:
        for key, value in PROFILE_RECOMMENDED_PENALTIES.get(profile, {}).items():
            penalties[key] = max(penalties.get(key, 0.0), _round(value))
    return dict(sorted(penalties.items()))


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    if not math.isfinite(out):
        return default
    return out


def _round(value: float) -> float:
    return round(float(value), 6)


__all__ = [
    "PROFILE_ADJUSTMENTS",
    "PROFILE_RECOMMENDED_PENALTIES",
    "PROFILE_RECOMMENDED_SCORE_CAPS",
    "PROFILE_SCHEMA_VERSION",
    "PROFILE_WARNINGS",
    "RegimeScoringProfile",
    "resolve_regime_scoring_profile",
]
