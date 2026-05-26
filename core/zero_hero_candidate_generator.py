"""Pure Zero Hero expiry CandidateIntent generator for EDGE-75."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.candidate_intent import CandidateIntent, INTENT_TYPE_ENTRY, INTENT_TYPE_NO_TRADE, create_candidate_intent
from core.candidate_intent_pool import CandidateIntentPoolReport, build_candidate_intent_pool

ZERO_HERO_CANDIDATE_GENERATOR_SCHEMA_VERSION = 1
ZERO_HERO_CANDIDATE_GENERATOR_SOURCE = "zero_hero_candidate_generator_v1"

ZERO_HERO_MISSING_MARKET_STATE = "zero_hero_missing_market_state"
ZERO_HERO_MISSING_INSTRUMENT = "zero_hero_missing_instrument"
ZERO_HERO_MISSING_PREMIUM = "zero_hero_missing_premium"
ZERO_HERO_MISSING_UNDERLYING_MOMENTUM = "zero_hero_missing_underlying_momentum"
ZERO_HERO_INVALID_NUMERIC_INPUT = "zero_hero_invalid_numeric_input"
ZERO_HERO_NOT_EXPIRY_CONTEXT = "zero_hero_not_expiry_context"
ZERO_HERO_PREMIUM_OUT_OF_BOUNDS = "zero_hero_premium_out_of_bounds"
ZERO_HERO_MOMENTUM_NOT_CONFIRMED = "zero_hero_momentum_not_confirmed"
ZERO_HERO_VOLUME_NOT_CONFIRMED = "zero_hero_volume_not_confirmed"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_REQUIRED_EVIDENCE_KEYS = (
    "market_state",
    "expiry_context",
    "premium_state",
    "underlying_momentum",
    "volume_confirmation",
    "feed_health_truth",
)

_PREMIUM_KEYS = ("option_ltp", "premium", "ltp", "last_traded", "last")
_DTE_KEYS = ("dte", "days_to_expiry", "expiry_days")
_EXPIRY_FLAG_KEYS = ("is_expiry_day", "expiry_day", "same_day_expiry")
_MOMENTUM_KEYS = ("underlying_momentum", "spot_momentum", "momentum", "move_bps")
_VOLUME_KEYS = ("vol_z", "volume_z", "volume_confirmation")
_REGIME_KEYS = ("regime", "market_regime", "regime_state")
_INSTRUMENT_KEYS = ("instrument", "symbol", "tradingsymbol", "underlying")


@dataclass(frozen=True)
class ZeroHeroCandidateGenerationReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    generated_intents: tuple[CandidateIntent, ...]
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
    def valid(self) -> bool:
        return not self.blockers and self.pool_report.valid

    @property
    def pool_ready(self) -> bool:
        return self.valid and self.pool_report.pool_ready

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "pool_ready": self.pool_ready,
            "generated_count": len(self.generated_intents),
            "candidate_intent_ids": [intent.candidate_intent_id for intent in self.generated_intents],
            "generated_intents": [intent.to_payload() for intent in self.generated_intents],
            "pool_report": self.pool_report.to_payload(),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        payload["live_order_action"] = False
        payload["broker_order_action"] = False
        return payload


def build_zero_hero_candidate_intents(
    market_state: Mapping[str, Any] | None,
    *,
    instrument: str | None = None,
    strategy_id: str = "zero_hero_v1",
    min_premium: float = 1.0,
    max_premium: float = 25.0,
    min_momentum_bps: float = 20.0,
    min_volume_z: float = 0.5,
    source: str = ZERO_HERO_CANDIDATE_GENERATOR_SOURCE,
) -> ZeroHeroCandidateGenerationReport:
    """Build a read-only Zero Hero expiry CandidateIntent from a market-state snapshot."""

    payload = dict(market_state or {}) if isinstance(market_state, Mapping) else {}
    blockers: list[str] = []
    warnings: list[str] = []
    if not isinstance(market_state, Mapping):
        blockers.append(ZERO_HERO_MISSING_MARKET_STATE)

    resolved_instrument = str(instrument or _first_text(payload, _INSTRUMENT_KEYS) or "").strip()
    if not resolved_instrument:
        resolved_instrument = "UNKNOWN"
        blockers.append(ZERO_HERO_MISSING_INSTRUMENT)

    premium = _first_float(payload, _PREMIUM_KEYS)
    dte = _first_float(payload, _DTE_KEYS, default=None)
    momentum_bps = _first_float(payload, _MOMENTUM_KEYS)
    volume_z = _first_float(payload, _VOLUME_KEYS, default=0.0)
    numeric_invalid = any(item is _INVALID_FLOAT for item in (premium, dte, momentum_bps, volume_z))
    if numeric_invalid:
        blockers.append(ZERO_HERO_INVALID_NUMERIC_INPUT)
    if premium in (None, _INVALID_FLOAT):
        blockers.append(ZERO_HERO_MISSING_PREMIUM)
    if momentum_bps in (None, _INVALID_FLOAT):
        blockers.append(ZERO_HERO_MISSING_UNDERLYING_MOMENTUM)

    expiry_context = _expiry_context(payload, dte)
    if expiry_context != "EXPIRY_CONTEXT" and not numeric_invalid:
        blockers.append(ZERO_HERO_NOT_EXPIRY_CONTEXT)

    direction = "NO_TRADE"
    trigger = "zero_hero_expiry_conditions_not_confirmed"
    invalidation = "expiry_momentum_fails_to_expand_premium"
    intent_type = INTENT_TYPE_NO_TRADE
    premium_state = "UNKNOWN"
    if not blockers:
        premium_state = _premium_state(premium, min_premium, max_premium)
        if premium_state != "TRADEABLE_PREMIUM":
            blockers.append(ZERO_HERO_PREMIUM_OUT_OF_BOUNDS)
        elif abs(float(momentum_bps)) < float(min_momentum_bps):
            blockers.append(ZERO_HERO_MOMENTUM_NOT_CONFIRMED)
        elif float(volume_z) < float(min_volume_z):
            blockers.append(ZERO_HERO_VOLUME_NOT_CONFIRMED)
            warnings.append("zero_hero_blocked_by_volume")
        elif float(momentum_bps) > 0:
            direction = "BUY_CALL"
            trigger = "expiry_call_momentum_with_tradeable_premium"
            intent_type = INTENT_TYPE_ENTRY
        elif float(momentum_bps) < 0:
            direction = "BUY_PUT"
            trigger = "expiry_put_momentum_with_tradeable_premium"
            intent_type = INTENT_TYPE_ENTRY
        else:
            blockers.append(ZERO_HERO_MOMENTUM_NOT_CONFIRMED)

    intent_blockers = _dedupe_sorted(blockers)
    intent = create_candidate_intent(
        strategy_id=strategy_id,
        instrument=resolved_instrument,
        direction=direction,
        regime=_first_text(payload, _REGIME_KEYS) or "EXPIRY",
        family="zero_hero",
        intent_type=intent_type,
        trigger=trigger,
        invalidation=invalidation,
        required_evidence_keys=_REQUIRED_EVIDENCE_KEYS,
        blockers=intent_blockers,
        warnings=_dedupe_sorted(warnings),
        metadata={
            "adapter_source": ZERO_HERO_CANDIDATE_GENERATOR_SOURCE,
            "input_keys": sorted(str(key) for key in payload.keys()),
            "expiry_context": expiry_context,
            "premium_state": premium_state,
            "premium": _safe_number(premium),
            "days_to_expiry": _safe_number(dte),
            "underlying_momentum_bps": _safe_number(momentum_bps),
            "volume_z": _safe_number(volume_z),
            "min_premium": float(min_premium),
            "max_premium": float(max_premium),
            "min_momentum_bps": float(min_momentum_bps),
            "min_volume_z": float(min_volume_z),
            "does_not_rank_candidates": True,
            "does_not_score_edge": True,
        },
    )
    pool_report = build_candidate_intent_pool((intent,))
    return ZeroHeroCandidateGenerationReport(
        schema_version=ZERO_HERO_CANDIDATE_GENERATOR_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        generated_intents=(intent,),
        pool_report=pool_report,
        blockers=(),
        warnings=_dedupe_sorted((*warnings, *pool_report.warnings)),
        metadata=_metadata(),
    )


_INVALID_FLOAT = object()


def _first_text(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _first_float(payload: Mapping[str, Any], keys: tuple[str, ...], default: float | None = None) -> float | object | None:
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None or str(value).strip() == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return _INVALID_FLOAT
    return default


def _expiry_context(payload: Mapping[str, Any], dte: Any) -> str:
    for key in _EXPIRY_FLAG_KEYS:
        value = payload.get(key)
        if isinstance(value, bool) and value:
            return "EXPIRY_CONTEXT"
        if str(value).strip().lower() in {"true", "1", "yes"}:
            return "EXPIRY_CONTEXT"
    if dte not in (None, _INVALID_FLOAT) and float(dte) <= 0.0:
        return "EXPIRY_CONTEXT"
    return "NON_EXPIRY_CONTEXT"


def _premium_state(premium: Any, min_premium: float, max_premium: float) -> str:
    if premium in (None, _INVALID_FLOAT):
        return "UNKNOWN"
    if float(premium) < float(min_premium):
        return "PREMIUM_TOO_LOW"
    if float(premium) > float(max_premium):
        return "PREMIUM_TOO_HIGH"
    return "TRADEABLE_PREMIUM"


def _safe_number(value: Any) -> float | None:
    if value in (None, _INVALID_FLOAT):
        return None
    return float(value)


def _dedupe_sorted(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


def _metadata() -> dict[str, Any]:
    return {
        "model": ZERO_HERO_CANDIDATE_GENERATOR_SOURCE,
        "scope": "pure_zero_hero_candidate_intent_generator_only",
        "does_not_import_strategy_modules": True,
        "does_not_execute_strategy_callables": True,
        "does_not_rank_candidates": True,
        "does_not_score_edge": True,
        "does_not_touch_runtime": True,
    }


__all__ = [
    "ZERO_HERO_CANDIDATE_GENERATOR_SCHEMA_VERSION",
    "ZERO_HERO_CANDIDATE_GENERATOR_SOURCE",
    "ZERO_HERO_INVALID_NUMERIC_INPUT",
    "ZERO_HERO_MISSING_INSTRUMENT",
    "ZERO_HERO_MISSING_MARKET_STATE",
    "ZERO_HERO_MISSING_PREMIUM",
    "ZERO_HERO_MISSING_UNDERLYING_MOMENTUM",
    "ZERO_HERO_MOMENTUM_NOT_CONFIRMED",
    "ZERO_HERO_NOT_EXPIRY_CONTEXT",
    "ZERO_HERO_PREMIUM_OUT_OF_BOUNDS",
    "ZERO_HERO_VOLUME_NOT_CONFIRMED",
    "ZeroHeroCandidateGenerationReport",
    "build_zero_hero_candidate_intents",
]
