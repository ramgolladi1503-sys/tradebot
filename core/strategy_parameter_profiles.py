"""Strategy parameter profiles and WFA evidence store interface.

The profile store is read-only. It exposes exact-profile and compatibility-alias
resolution with deterministic hashing so inventory-managed generators can prove
which profile identity they used and whether any embedded fallback remains.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Iterable, Mapping, Protocol

EXPERIMENTAL = "EXPERIMENTAL"
ADVISORY_ONLY = "ADVISORY_ONLY"
PAPER_EXECUTABLE = "PAPER_EXECUTABLE"
MANUAL_APPROVAL_ELIGIBLE = "MANUAL_APPROVAL_ELIGIBLE"
PROMOTED = "PROMOTED"
DISABLED = "DISABLED"

EXACT_PROFILE = "EXACT_PROFILE"
COMPATIBILITY_ALIAS = "COMPATIBILITY_ALIAS"
EMBEDDED_FALLBACK = "EMBEDDED_FALLBACK"
MISSING_PROFILE = "MISSING_PROFILE"
AMBIGUOUS_PROFILE = "AMBIGUOUS_PROFILE"
PROFILE_VALUE_DRIFT = "PROFILE_VALUE_DRIFT"


def _normalize_hash_value(value: Any) -> Any:
    """Normalize values into a stable, explicit representation for hashing."""

    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": str(value)}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("profile_parameter_not_finite")
        return {"type": "float", "value": format(Decimal(str(value)).normalize(), "f")}
    if isinstance(value, str) or value is None:
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_hash_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_hash_value(item) for item in value]
    return str(value)


def build_profile_parameter_hash(
    *,
    resolved_profile_id: str,
    profile_version: str,
    params: Mapping[str, Any],
) -> str:
    """Return a deterministic hash for the effective parameter payload."""

    payload = {
        "profile_id": str(resolved_profile_id or "").strip(),
        "profile_version": str(profile_version or "").strip(),
        "parameters": _normalize_hash_value(dict(params)),
    }
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class StrategyParameterProfile:
    strategy_id: str
    strategy_version: str
    instrument: str
    regime_bucket: str
    session_bucket: str
    expiry_context: str
    volatility_bucket: str
    params: dict[str, float | int | str | bool] = field(default_factory=dict)
    requested_profile_id: str = ""
    resolved_profile_id: str = ""
    resolution_source: str = EXACT_PROFILE
    warnings: tuple[str, ...] = field(default_factory=tuple)
    promotion_state: str = ADVISORY_ONLY
    params_hash: str = field(init=False)

    def __post_init__(self) -> None:
        requested_profile_id = str(self.requested_profile_id or "").strip() or str(self.strategy_id).strip()
        resolved_profile_id = str(self.resolved_profile_id or "").strip() or requested_profile_id
        resolution_source = str(self.resolution_source or "").strip() or EXACT_PROFILE
        if resolution_source not in {
            EXACT_PROFILE,
            COMPATIBILITY_ALIAS,
            EMBEDDED_FALLBACK,
        }:
            raise ValueError(f"invalid_resolution_source:{resolution_source}")
        warnings = tuple(
            str(warning).strip()
            for warning in (self.warnings or ())
            if str(warning).strip()
        )
        promotion_state = str(self.promotion_state or "").strip() or ADVISORY_ONLY
        object.__setattr__(self, "requested_profile_id", requested_profile_id)
        object.__setattr__(self, "resolved_profile_id", resolved_profile_id)
        object.__setattr__(self, "resolution_source", resolution_source)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "promotion_state", promotion_state)
        object.__setattr__(
            self,
            "params_hash",
            build_profile_parameter_hash(
                resolved_profile_id=resolved_profile_id,
                profile_version=self.strategy_version,
                params=self.params,
            ),
        )

    @property
    def profile_version(self) -> str:
        return self.strategy_version

    @property
    def parameter_hash(self) -> str:
        return self.params_hash

    @property
    def parameters(self) -> dict[str, float | int | str | bool]:
        return dict(self.params)

    def to_resolution_record(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "requested_profile_id": self.requested_profile_id,
            "resolved_profile_id": self.resolved_profile_id,
            "profile_version": self.profile_version,
            "resolution_source": self.resolution_source,
            "promotion_state": self.promotion_state,
            "parameter_hash": self.parameter_hash,
            "parameters": dict(self.params),
            "warnings": tuple(self.warnings),
        }


_CANONICAL_PROFILE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "opening_drive_v1": {
        "strategy_id": "opening_drive",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {
            "MAX_OPENING_DRIVE_MINUTES": 20,
            "MIN_OPEN_MOVE_PCT": 0.0015,
            "MIN_VWAP_ALIGNMENT_PCT": 0.0005,
        },
    },
    "opening_range_breakout_v1": {
        "strategy_id": "opening_range_breakout",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {
            "MIN_RETEST_MINUTES": 15,
            "MAX_RETEST_MINUTES": 90,
            "MAX_RETEST_DISTANCE_PCT": 0.0018,
            "MIN_BREAKOUT_DISTANCE_PCT": 0.0008,
        },
    },
    "compression_breakout_v1": {
        "strategy_id": "compression_breakout",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {
            "MAX_RANGE_WIDTH_PCT": 0.35,
            "MAX_ATR_RATIO": 0.75,
            "MIN_COMPRESSION_SCORE": 0.5,
            "MIN_BREAKOUT_DISTANCE_PCT": 0.0008,
            "MIN_VWAP_ALIGNMENT_PCT": 0.0004,
        },
    },
    "trend_pullback_v1": {
        "strategy_id": "trend_pullback",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {
            "MIN_TREND_SCORE": 0.45,
            "MAX_PULLBACK_DISTANCE_PCT": 0.0035,
            "MIN_STRUCTURE_RESUME_PCT": 0.0004,
        },
    },
    "vwap_reclaim_rejection_v1": {
        "strategy_id": "vwap_reclaim_rejection",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {
            "MIN_VWAP_DISTANCE_PCT": 0.00035,
            "MAX_VWAP_ENTRY_DISTANCE_PCT": 0.0035,
            "MAX_CHOP_SCORE": 0.55,
        },
    },
    "failed_breakout_trap_v1": {
        "strategy_id": "failed_breakout_trap",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {
            "MAX_REENTRY_DISTANCE_PCT": 0.0035,
            "MIN_FAILED_BREAK_DISTANCE_PCT": 0.0006,
            "MIN_TRAP_EVIDENCE_SCORE": 0.45,
        },
    },
    "exhaustion_reversal_v1": {
        "strategy_id": "exhaustion_reversal",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {
            "MIN_STRETCH_FROM_VWAP_PCT": 0.005,
            "MAX_ENTRY_STRETCH_PCT": 0.018,
            "MIN_EXHAUSTION_SCORE": 0.5,
            "MAX_CONTINUATION_PRESSURE_SCORE": 0.55,
        },
    },
    "mean_reversion_extension_v1": {
        "strategy_id": "mean_reversion_extension",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {
            "MIN_RANGE_OR_CHOP_SCORE": 0.45,
            "MIN_EXTENSION_FROM_VWAP_PCT": 0.0035,
            "MAX_EXTENSION_FROM_VWAP_PCT": 0.014,
            "MAX_TREND_CONTINUATION_SCORE": 0.55,
        },
    },
    "event_volatility_expansion_v1": {
        "strategy_id": "event_volatility_expansion",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {
            "MIN_VOL_EXPANSION_SCORE": 0.4,
            "MIN_IMPULSE_FROM_VWAP_PCT": 0.0025,
            "MAX_CHASE_DISTANCE_PCT": 0.014,
            "MIN_VOLUME_Z": 1.2,
            "MIN_ATR_EXPANSION_RATIO": 1.15,
        },
    },
    "late_day_momentum_v1": {
        "strategy_id": "late_day_momentum",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {
            "MIN_MINUTES_SINCE_OPEN": 240,
            "MIN_MINUTES_TO_CLOSE": 20,
            "MIN_DIRECTIONAL_SCORE": 0.45,
            "MIN_VWAP_DISTANCE_PCT": 0.002,
            "MAX_CHASE_DISTANCE_PCT": 0.012,
            "MAX_CHOP_SCORE": 0.5,
        },
    },
    "no_trade_engine_v1": {
        "strategy_id": "no_trade_engine",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {},
    },
    "option_pressure_v1": {
        "strategy_id": "option_pressure",
        "strategy_version": "v1",
        "instrument": "ANY",
        "regime_bucket": "ANY",
        "session_bucket": "ANY",
        "expiry_context": "ANY",
        "volatility_bucket": "ANY",
        "params": {
            "MIN_PRESSURE_SCORE": 0.45,
        },
    },
}


COMPATIBILITY_PROFILE_ALIASES: dict[str, str] = {
    "opening_range_retest_v1": "opening_range_breakout_v1",
    "option_pressure_confirmation_v1": "option_pressure_v1",
}


EMBEDDED_PROFILE_DEFAULTS: dict[str, dict[str, float | int | str | bool]] = {
    "mean_reversion_extension_v1": {
        "MIN_RANGE_OR_CHOP_SCORE": 0.45,
        "MIN_EXTENSION_FROM_VWAP_PCT": 0.0035,
        "MAX_EXTENSION_FROM_VWAP_PCT": 0.014,
        "MAX_TREND_CONTINUATION_SCORE": 0.55,
    },
    "compression_breakout_v1": {
        "MAX_RANGE_WIDTH_PCT": 0.35,
        "MAX_ATR_RATIO": 0.75,
        "MIN_COMPRESSION_SCORE": 0.50,
        "MIN_BREAKOUT_DISTANCE_PCT": 0.0008,
        "MIN_VWAP_ALIGNMENT_PCT": 0.0004,
    },
    "trend_pullback_v1": {
        "MIN_TREND_SCORE": 0.45,
        "MAX_PULLBACK_DISTANCE_PCT": 0.0035,
        "MIN_STRUCTURE_RESUME_PCT": 0.0004,
    },
    "vwap_reclaim_rejection_v1": {
        "MIN_VWAP_DISTANCE_PCT": 0.00035,
        "MAX_VWAP_ENTRY_DISTANCE_PCT": 0.0035,
        "MAX_CHOP_SCORE": 0.55,
    },
    "opening_drive_v1": {
        "MAX_OPENING_DRIVE_MINUTES": 20,
        "MIN_OPEN_MOVE_PCT": 0.0015,
        "MIN_VWAP_ALIGNMENT_PCT": 0.0005,
    },
    "failed_breakout_trap_v1": {
        "MAX_REENTRY_DISTANCE_PCT": 0.0035,
        "MIN_FAILED_BREAK_DISTANCE_PCT": 0.0006,
        "MIN_TRAP_EVIDENCE_SCORE": 0.45,
    },
    "exhaustion_reversal_v1": {
        "MIN_STRETCH_FROM_VWAP_PCT": 0.005,
        "MAX_ENTRY_STRETCH_PCT": 0.018,
        "MIN_EXHAUSTION_SCORE": 0.50,
        "MAX_CONTINUATION_PRESSURE_SCORE": 0.55,
    },
    "event_volatility_expansion_v1": {
        "MIN_VOL_EXPANSION_SCORE": 0.40,
        "MIN_IMPULSE_FROM_VWAP_PCT": 0.0025,
        "MAX_CHASE_DISTANCE_PCT": 0.014,
        "MIN_VOLUME_Z": 1.2,
        "MIN_ATR_EXPANSION_RATIO": 1.15,
    },
    "late_day_momentum_v1": {
        "MIN_MINUTES_SINCE_OPEN": 240,
        "MIN_MINUTES_TO_CLOSE": 20,
        "MIN_DIRECTIONAL_SCORE": 0.45,
        "MIN_VWAP_DISTANCE_PCT": 0.002,
        "MAX_CHASE_DISTANCE_PCT": 0.012,
        "MAX_CHOP_SCORE": 0.50,
    },
    "opening_range_retest_v1": {
        "MIN_RETEST_MINUTES": 15,
        "MAX_RETEST_MINUTES": 90,
        "MAX_RETEST_DISTANCE_PCT": 0.0018,
        "MIN_BREAKOUT_DISTANCE_PCT": 0.0008,
    },
    "option_pressure_confirmation_v1": {
        "MIN_PRESSURE_SCORE": 0.45,
    },
    "no_trade_engine_v1": {},
}


def _canonical_profile(profile_id: str) -> StrategyParameterProfile:
    definition = _CANONICAL_PROFILE_DEFINITIONS[profile_id]
    return StrategyParameterProfile(
        requested_profile_id=profile_id,
        resolved_profile_id=profile_id,
        resolution_source=EXACT_PROFILE,
        warnings=(),
        **definition,
    )


DEFAULT_PROFILES: dict[str, StrategyParameterProfile] = {
    profile_id: _canonical_profile(profile_id)
    for profile_id in _CANONICAL_PROFILE_DEFINITIONS
}


def _validate_profile_alias_map(
    aliases: Mapping[str, str] | Iterable[tuple[str, str]] | None = None,
    *,
    canonical_profile_ids: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    raw_alias_entries = (
        tuple(COMPATIBILITY_PROFILE_ALIASES.items())
        if aliases is None
        else tuple(aliases.items() if isinstance(aliases, Mapping) else aliases)
    )
    canonical_ids = set(DEFAULT_PROFILES if canonical_profile_ids is None else canonical_profile_ids)
    alias_targets: dict[str, list[str]] = {}
    for raw_alias, raw_target in raw_alias_entries:
        alias = str(raw_alias or "").strip()
        target = str(raw_target or "").strip()
        if not alias or not target:
            raise ValueError("profile_alias_missing_identifier")
        alias_targets.setdefault(alias, []).append(target)
    for alias, targets in alias_targets.items():
        if len(targets) > 1:
            raise ValueError(f"profile_alias_duplicate:{alias}")
    alias_map = {alias: targets[0] for alias, targets in alias_targets.items()}
    validated: dict[str, str] = {}
    for raw_alias, raw_target in alias_map.items():
        alias = str(raw_alias or "").strip()
        target = str(raw_target or "").strip()
        if not alias or not target:
            raise ValueError("profile_alias_missing_identifier")
        if alias in canonical_ids:
            raise ValueError(f"profile_alias_collides_with_canonical:{alias}")
        if alias == target:
            raise ValueError(f"profile_alias_cycle:{alias}:{target}")
        if target in alias_map:
            raise ValueError(f"profile_alias_target_is_alias:{alias}:{target}")
        if target not in canonical_ids:
            raise ValueError(f"profile_alias_target_missing:{alias}:{target}")
        validated[alias] = target
    return validated


def validate_profile_alias_map(
    aliases: Mapping[str, str] | Iterable[tuple[str, str]] | None = None,
    *,
    canonical_profile_ids: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Validate a compatibility-alias map and return its normalized form."""

    return _validate_profile_alias_map(
        aliases,
        canonical_profile_ids=canonical_profile_ids,
    )


def _profile_defaults_match(
    requested_profile_id: str,
    resolved_profile_id: str,
    *,
    embedded_defaults: Mapping[str, Any] | None = None,
) -> bool:
    if embedded_defaults is None:
        return True
    canonical_defaults = EMBEDDED_PROFILE_DEFAULTS.get(requested_profile_id)
    if canonical_defaults is None:
        return True
    return dict(canonical_defaults) == dict(embedded_defaults) and resolved_profile_id in DEFAULT_PROFILES


def classify_profile_resolution(
    requested_profile_id: str,
    version: str = "v1",
) -> str:
    """Classify how a requested profile relates to the profile store."""

    requested = str(requested_profile_id or "").strip()
    if not requested:
        return MISSING_PROFILE
    exact = DEFAULT_PROFILES.get(requested)
    if exact is not None and exact.strategy_version == version:
        embedded_defaults = EMBEDDED_PROFILE_DEFAULTS.get(requested)
        if embedded_defaults is not None and dict(embedded_defaults) != dict(exact.params):
            return PROFILE_VALUE_DRIFT
        return EXACT_PROFILE
    target = VALIDATED_COMPATIBILITY_PROFILE_ALIASES.get(requested)
    if target is not None:
        profile = DEFAULT_PROFILES.get(target)
        if profile is None or profile.strategy_version != version:
            return MISSING_PROFILE
        embedded_defaults = EMBEDDED_PROFILE_DEFAULTS.get(requested)
        if embedded_defaults is None:
            return COMPATIBILITY_ALIAS
        if dict(embedded_defaults) != dict(profile.params):
            return PROFILE_VALUE_DRIFT
        return COMPATIBILITY_ALIAS
    if requested in EMBEDDED_PROFILE_DEFAULTS:
        return EMBEDDED_FALLBACK
    return MISSING_PROFILE


VALIDATED_COMPATIBILITY_PROFILE_ALIASES = _validate_profile_alias_map()

@dataclass
class StrategyEvidenceDecision:
    strategy_id: str
    strategy_version: str
    params_hash: str
    instrument: str
    regime_bucket: str
    session_bucket: str
    promotion_state: str
    evidence_status: str
    evidence_reason: str
    sample_size: int | None = None
    last_updated: float | None = None

class StrategyEvidenceStore(Protocol):
    def get_promotion_state(
        self,
        strategy_id: str,
        strategy_version: str,
        params_hash: str,
        instrument: str,
        regime_bucket: str,
        session_bucket: str,
    ) -> StrategyEvidenceDecision:
        ...

class DefaultStrategyEvidenceStore:
    def get_promotion_state(
        self,
        strategy_id: str,
        strategy_version: str,
        params_hash: str,
        instrument: str,
        regime_bucket: str,
        session_bucket: str,
    ) -> StrategyEvidenceDecision:
        return StrategyEvidenceDecision(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            params_hash=params_hash,
            instrument=instrument,
            regime_bucket=regime_bucket,
            session_bucket=session_bucket,
            promotion_state=ADVISORY_ONLY,
            evidence_status="UNKNOWN",
            evidence_reason="Default strategy evidence store assumes ADVISORY_ONLY",
        )

def get_default_profile(strategy_id: str, version: str = "v1") -> StrategyParameterProfile | None:
    requested_profile_id = str(strategy_id or "").strip()
    if not requested_profile_id or str(version or "").strip() != "v1":
        return None

    exact_profile = DEFAULT_PROFILES.get(requested_profile_id)
    if exact_profile is not None:
        embedded_defaults = EMBEDDED_PROFILE_DEFAULTS.get(requested_profile_id)
        if embedded_defaults is not None and dict(embedded_defaults) != dict(exact_profile.params):
            return None
        return replace(
            exact_profile,
            requested_profile_id=requested_profile_id,
            resolved_profile_id=requested_profile_id,
            resolution_source=EXACT_PROFILE,
            warnings=(),
        )

    compatibility_target = VALIDATED_COMPATIBILITY_PROFILE_ALIASES.get(requested_profile_id)
    if compatibility_target is None:
        return None

    canonical_profile = DEFAULT_PROFILES.get(compatibility_target)
    if canonical_profile is None:
        return None

    embedded_defaults = EMBEDDED_PROFILE_DEFAULTS.get(requested_profile_id)
    if embedded_defaults is None:
        return replace(
            canonical_profile,
            requested_profile_id=requested_profile_id,
            resolved_profile_id=compatibility_target,
            resolution_source=COMPATIBILITY_ALIAS,
            warnings=(f"compatibility_alias:{requested_profile_id}->{compatibility_target}",),
        )
    if dict(embedded_defaults) != dict(canonical_profile.params):
        return None

    return replace(
        canonical_profile,
        requested_profile_id=requested_profile_id,
        resolved_profile_id=compatibility_target,
        resolution_source=COMPATIBILITY_ALIAS,
        warnings=(f"compatibility_alias:{requested_profile_id}->{compatibility_target}",),
    )


def build_profile_resolution_record(
    strategy_id: str,
    version: str = "v1",
) -> dict[str, Any]:
    """Return a serializable resolution record for evidence and tests."""

    profile = get_default_profile(strategy_id, version)
    classification = classify_profile_resolution(strategy_id, version)
    if profile is None:
        return {
            "strategy_id": str(strategy_id or "").strip(),
            "requested_profile_id": str(strategy_id or "").strip(),
            "resolved_profile_id": None,
            "profile_version": str(version or "").strip(),
            "resolution_source": classification
            if classification in {EXACT_PROFILE, COMPATIBILITY_ALIAS, EMBEDDED_FALLBACK}
            else None,
            "parameter_hash": None,
            "parameters": {},
            "warnings": (),
            "mismatch_classification": classification,
        }
    record = profile.to_resolution_record()
    record["mismatch_classification"] = classification
    return record
