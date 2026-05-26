"""Pure mean-reversion CandidateIntent generator for EDGE-74."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.candidate_intent import CandidateIntent, INTENT_TYPE_ENTRY, INTENT_TYPE_NO_TRADE, create_candidate_intent
from core.candidate_intent_pool import CandidateIntentPoolReport, build_candidate_intent_pool

MEAN_REVERSION_CANDIDATE_GENERATOR_SCHEMA_VERSION = 1
MEAN_REVERSION_CANDIDATE_GENERATOR_SOURCE = "mean_reversion_candidate_generator_v1"

MEAN_REVERSION_MISSING_MARKET_STATE = "mean_reversion_missing_market_state"
MEAN_REVERSION_MISSING_INSTRUMENT = "mean_reversion_missing_instrument"
MEAN_REVERSION_MISSING_LTP = "mean_reversion_missing_ltp"
MEAN_REVERSION_MISSING_ANCHOR = "mean_reversion_missing_anchor"
MEAN_REVERSION_INVALID_NUMERIC_INPUT = "mean_reversion_invalid_numeric_input"
MEAN_REVERSION_INVALID_PARAMETER = "mean_reversion_invalid_parameter"
MEAN_REVERSION_DEVIATION_TOO_SMALL = "mean_reversion_deviation_too_small"
MEAN_REVERSION_OSCILLATOR_NOT_CONFIRMED = "mean_reversion_oscillator_not_confirmed"
MEAN_REVERSION_NO_EXTREME = "mean_reversion_no_extreme"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_REQUIRED_EVIDENCE_KEYS = (
    "market_state",
    "regime_state",
    "mean_reversion_anchor",
    "oscillator_confirmation",
    "feed_health_truth",
)

_LTP_KEYS = ("ltp", "last_traded", "last")
_ANCHOR_KEYS = ("vwap", "session_vwap", "mean_anchor", "anchor_price")
_OSCILLATOR_KEYS = ("rsi_mom", "rsi_momentum", "oscillator", "momentum")
_REGIME_KEYS = ("regime", "market_regime", "regime_state")
_INSTRUMENT_KEYS = ("instrument", "symbol", "tradingsymbol", "underlying")


@dataclass(frozen=True)
class MeanReversionCandidateGenerationReport:
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


def build_mean_reversion_candidate_intents(
    market_state: Mapping[str, Any] | None,
    *,
    instrument: str | None = None,
    strategy_id: str = "mean_reversion_v1",
    min_deviation_bps: float = 30.0,
    min_oscillator_confirmation: float = 0.0,
    source: str = MEAN_REVERSION_CANDIDATE_GENERATOR_SOURCE,
) -> MeanReversionCandidateGenerationReport:
    """Build a read-only mean-reversion CandidateIntent from a market-state snapshot."""

    payload = dict(market_state or {}) if isinstance(market_state, Mapping) else {}
    blockers: list[str] = []
    warnings: list[str] = []
    if not isinstance(market_state, Mapping):
        blockers.append(MEAN_REVERSION_MISSING_MARKET_STATE)

    min_deviation_bps_value = _threshold(min_deviation_bps, allow_zero=False)
    min_oscillator_confirmation_value = _threshold(min_oscillator_confirmation, allow_zero=True)
    if _INVALID_FLOAT in (min_deviation_bps_value, min_oscillator_confirmation_value):
        blockers.append(MEAN_REVERSION_INVALID_PARAMETER)

    resolved_instrument = str(instrument or _first_text(payload, _INSTRUMENT_KEYS) or "").strip()
    if not resolved_instrument:
        resolved_instrument = "UNKNOWN"
        blockers.append(MEAN_REVERSION_MISSING_INSTRUMENT)

    ltp = _first_float(payload, _LTP_KEYS)
    anchor = _first_float(payload, _ANCHOR_KEYS)
    oscillator = _first_float(payload, _OSCILLATOR_KEYS, default=0.0)
    numeric_invalid = any(item is _INVALID_FLOAT for item in (ltp, anchor, oscillator))
    if numeric_invalid:
        blockers.append(MEAN_REVERSION_INVALID_NUMERIC_INPUT)
    if ltp in (None, _INVALID_FLOAT):
        blockers.append(MEAN_REVERSION_MISSING_LTP)
    if anchor in (None, _INVALID_FLOAT):
        blockers.append(MEAN_REVERSION_MISSING_ANCHOR)

    direction = "NO_TRADE"
    trigger = "mean_reversion_conditions_not_confirmed"
    invalidation = "price_fails_to_revert_toward_anchor"
    intent_type = INTENT_TYPE_NO_TRADE
    deviation_bps = None
    if not blockers:
        deviation_bps = ((float(ltp) - float(anchor)) / float(anchor)) * 10000.0
        if abs(deviation_bps) < float(min_deviation_bps_value):
            blockers.append(MEAN_REVERSION_DEVIATION_TOO_SMALL)
        elif deviation_bps > 0:
            direction = "BUY_PUT"
            trigger = "price_extended_above_anchor_with_reversal_confirmation"
            if float(oscillator) > -float(min_oscillator_confirmation_value):
                blockers.append(MEAN_REVERSION_OSCILLATOR_NOT_CONFIRMED)
                warnings.append("mean_reversion_down_blocked_by_oscillator")
        elif deviation_bps < 0:
            direction = "BUY_CALL"
            trigger = "price_extended_below_anchor_with_reversal_confirmation"
            if float(oscillator) < float(min_oscillator_confirmation_value):
                blockers.append(MEAN_REVERSION_OSCILLATOR_NOT_CONFIRMED)
                warnings.append("mean_reversion_up_blocked_by_oscillator")
        else:
            blockers.append(MEAN_REVERSION_NO_EXTREME)
        if direction != "NO_TRADE" and not blockers:
            intent_type = INTENT_TYPE_ENTRY

    intent_blockers = _dedupe_sorted(blockers)
    intent = create_candidate_intent(
        strategy_id=strategy_id,
        instrument=resolved_instrument,
        direction=direction,
        regime=_first_text(payload, _REGIME_KEYS) or "UNCERTAIN",
        family="mean_reversion",
        intent_type=intent_type,
        trigger=trigger,
        invalidation=invalidation,
        required_evidence_keys=_REQUIRED_EVIDENCE_KEYS,
        blockers=intent_blockers,
        warnings=_dedupe_sorted(warnings),
        metadata={
            "adapter_source": MEAN_REVERSION_CANDIDATE_GENERATOR_SOURCE,
            "input_keys": sorted(str(key) for key in payload.keys()),
            "reversion_state": _reversion_state(ltp, anchor, deviation_bps, min_deviation_bps_value),
            "deviation_bps": _safe_number(deviation_bps),
            "oscillator": _safe_number(oscillator),
            "min_deviation_bps": _safe_number(min_deviation_bps_value),
            "min_oscillator_confirmation": _safe_number(min_oscillator_confirmation_value),
            "does_not_rank_candidates": True,
            "does_not_score_edge": True,
        },
    )
    pool_report = build_candidate_intent_pool((intent,))
    return MeanReversionCandidateGenerationReport(
        schema_version=MEAN_REVERSION_CANDIDATE_GENERATOR_SCHEMA_VERSION,
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


def _threshold(value: Any, *, allow_zero: bool) -> float | object:
    parsed = _to_finite_float(value)
    if parsed is _INVALID_FLOAT:
        return _INVALID_FLOAT
    if parsed < 0 or (parsed == 0 and not allow_zero):
        return _INVALID_FLOAT
    return parsed


def _to_finite_float(value: Any) -> float | object:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return _INVALID_FLOAT
    if not math.isfinite(parsed):
        return _INVALID_FLOAT
    return parsed


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
        return _to_finite_float(value)
    return default


def _reversion_state(ltp: Any, anchor: Any, deviation_bps: Any, min_deviation_bps: Any) -> str:
    if any(value in (None, _INVALID_FLOAT) for value in (ltp, anchor, min_deviation_bps)):
        return "UNKNOWN"
    if deviation_bps in (None, _INVALID_FLOAT):
        return "UNKNOWN"
    if abs(float(deviation_bps)) < float(min_deviation_bps):
        return "NEUTRAL_ZONE"
    if float(deviation_bps) > 0:
        return "EXTENDED_ABOVE_ANCHOR"
    if float(deviation_bps) < 0:
        return "EXTENDED_BELOW_ANCHOR"
    return "AT_ANCHOR"


def _safe_number(value: Any) -> float | None:
    if value in (None, _INVALID_FLOAT):
        return None
    return float(value)


def _dedupe_sorted(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


def _metadata() -> dict[str, Any]:
    return {
        "model": MEAN_REVERSION_CANDIDATE_GENERATOR_SOURCE,
        "scope": "pure_mean_reversion_candidate_intent_generator_only",
        "does_not_import_strategy_modules": True,
        "does_not_execute_strategy_callables": True,
        "does_not_rank_candidates": True,
        "does_not_score_edge": True,
        "does_not_touch_runtime": True,
    }


__all__ = [
    "MEAN_REVERSION_CANDIDATE_GENERATOR_SCHEMA_VERSION",
    "MEAN_REVERSION_CANDIDATE_GENERATOR_SOURCE",
    "MEAN_REVERSION_DEVIATION_TOO_SMALL",
    "MEAN_REVERSION_INVALID_NUMERIC_INPUT",
    "MEAN_REVERSION_INVALID_PARAMETER",
    "MEAN_REVERSION_MISSING_ANCHOR",
    "MEAN_REVERSION_MISSING_INSTRUMENT",
    "MEAN_REVERSION_MISSING_LTP",
    "MEAN_REVERSION_MISSING_MARKET_STATE",
    "MEAN_REVERSION_NO_EXTREME",
    "MEAN_REVERSION_OSCILLATOR_NOT_CONFIRMED",
    "MeanReversionCandidateGenerationReport",
    "build_mean_reversion_candidate_intents",
]
