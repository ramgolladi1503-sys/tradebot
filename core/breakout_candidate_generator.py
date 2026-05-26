"""Pure breakout CandidateIntent generator for EDGE-72."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.candidate_intent import CandidateIntent, INTENT_TYPE_ENTRY, INTENT_TYPE_NO_TRADE, create_candidate_intent
from core.candidate_intent_pool import CandidateIntentPoolReport, build_candidate_intent_pool

BREAKOUT_CANDIDATE_GENERATOR_SCHEMA_VERSION = 1
BREAKOUT_CANDIDATE_GENERATOR_SOURCE = "breakout_candidate_generator_v1"

BREAKOUT_MISSING_MARKET_STATE = "breakout_missing_market_state"
BREAKOUT_MISSING_INSTRUMENT = "breakout_missing_instrument"
BREAKOUT_MISSING_LTP = "breakout_missing_ltp"
BREAKOUT_MISSING_RANGE = "breakout_missing_range"
BREAKOUT_INVALID_RANGE = "breakout_invalid_range"
BREAKOUT_NO_RANGE_BREAK = "breakout_no_range_break"
BREAKOUT_VOLUME_NOT_CONFIRMED = "breakout_volume_not_confirmed"
BREAKOUT_INVALID_NUMERIC_INPUT = "breakout_invalid_numeric_input"
BREAKOUT_INVALID_PARAMETER = "breakout_invalid_parameter"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_REQUIRED_EVIDENCE_KEYS = (
    "market_state",
    "regime_state",
    "breakout_range",
    "volume_confirmation",
    "feed_health_truth",
)

_LTP_KEYS = ("ltp", "last_traded", "last")
_RANGE_HIGH_KEYS = ("orb_high", "range_high", "opening_range_high")
_RANGE_LOW_KEYS = ("orb_low", "range_low", "opening_range_low")
_VOLUME_KEYS = ("vol_z", "volume_z", "volume_confirmation")
_REGIME_KEYS = ("regime", "market_regime", "regime_state")
_INSTRUMENT_KEYS = ("instrument", "symbol", "tradingsymbol", "underlying")


@dataclass(frozen=True)
class BreakoutCandidateGenerationReport:
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


def build_breakout_candidate_intents(
    market_state: Mapping[str, Any] | None,
    *,
    instrument: str | None = None,
    strategy_id: str = "breakout_v1",
    min_volume_z: float = 0.5,
    source: str = BREAKOUT_CANDIDATE_GENERATOR_SOURCE,
) -> BreakoutCandidateGenerationReport:
    """Build a read-only breakout CandidateIntent from a market-state snapshot."""

    payload = dict(market_state or {}) if isinstance(market_state, Mapping) else {}
    blockers: list[str] = []
    warnings: list[str] = []
    if not isinstance(market_state, Mapping):
        blockers.append(BREAKOUT_MISSING_MARKET_STATE)

    min_volume_z_value = _threshold(min_volume_z, allow_zero=True)
    if min_volume_z_value is _INVALID_FLOAT:
        blockers.append(BREAKOUT_INVALID_PARAMETER)

    resolved_instrument = str(instrument or _first_text(payload, _INSTRUMENT_KEYS) or "").strip()
    if not resolved_instrument:
        resolved_instrument = "UNKNOWN"
        blockers.append(BREAKOUT_MISSING_INSTRUMENT)

    ltp = _first_float(payload, _LTP_KEYS)
    range_high = _first_float(payload, _RANGE_HIGH_KEYS)
    range_low = _first_float(payload, _RANGE_LOW_KEYS)
    volume_z = _first_float(payload, _VOLUME_KEYS, default=0.0)
    numeric_invalid = any(item is _INVALID_FLOAT for item in (ltp, range_high, range_low, volume_z))
    if numeric_invalid:
        blockers.append(BREAKOUT_INVALID_NUMERIC_INPUT)
    if ltp in (None, _INVALID_FLOAT):
        blockers.append(BREAKOUT_MISSING_LTP)
    if range_high in (None, _INVALID_FLOAT) or range_low in (None, _INVALID_FLOAT):
        blockers.append(BREAKOUT_MISSING_RANGE)
    elif float(range_high) <= float(range_low):
        blockers.append(BREAKOUT_INVALID_RANGE)

    direction = "NO_TRADE"
    trigger = "breakout_conditions_not_confirmed"
    invalidation = "breakout_range_remains_intact"
    intent_type = INTENT_TYPE_NO_TRADE
    if not blockers:
        if float(ltp) > float(range_high):
            direction = "BUY_CALL"
            trigger = "ltp_cleared_opening_range_high"
            invalidation = "ltp_returns_inside_opening_range"
        elif float(ltp) < float(range_low):
            direction = "BUY_PUT"
            trigger = "ltp_broke_opening_range_low"
            invalidation = "ltp_returns_inside_opening_range"
        else:
            blockers.append(BREAKOUT_NO_RANGE_BREAK)
        if direction != "NO_TRADE":
            if float(volume_z) < float(min_volume_z_value):
                blockers.append(BREAKOUT_VOLUME_NOT_CONFIRMED)
                warnings.append("breakout_hypothesis_blocked_by_volume")
            else:
                intent_type = INTENT_TYPE_ENTRY

    intent_blockers = _dedupe_sorted(blockers)
    intent = create_candidate_intent(
        strategy_id=strategy_id,
        instrument=resolved_instrument,
        direction=direction,
        regime=_first_text(payload, _REGIME_KEYS) or "UNCERTAIN",
        family="breakout",
        intent_type=intent_type,
        trigger=trigger,
        invalidation=invalidation,
        required_evidence_keys=_REQUIRED_EVIDENCE_KEYS,
        blockers=intent_blockers,
        warnings=_dedupe_sorted(warnings),
        metadata={
            "adapter_source": BREAKOUT_CANDIDATE_GENERATOR_SOURCE,
            "input_keys": sorted(str(key) for key in payload.keys()),
            "range_position": _range_position(ltp, range_high, range_low),
            "volume_z": _safe_number(volume_z),
            "min_volume_z": _safe_number(min_volume_z_value),
            "does_not_rank_candidates": True,
            "does_not_score_edge": True,
        },
    )
    pool_report = build_candidate_intent_pool((intent,))
    return BreakoutCandidateGenerationReport(
        schema_version=BREAKOUT_CANDIDATE_GENERATOR_SCHEMA_VERSION,
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


def _range_position(ltp: Any, range_high: Any, range_low: Any) -> str:
    if any(value in (None, _INVALID_FLOAT) for value in (ltp, range_high, range_low)):
        return "UNKNOWN"
    if float(range_high) <= float(range_low):
        return "INVALID_RANGE"
    if float(ltp) > float(range_high):
        return "ABOVE_RANGE"
    if float(ltp) < float(range_low):
        return "BELOW_RANGE"
    return "INSIDE_RANGE"


def _safe_number(value: Any) -> float | None:
    if value in (None, _INVALID_FLOAT):
        return None
    return float(value)


def _dedupe_sorted(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


def _metadata() -> dict[str, Any]:
    return {
        "model": BREAKOUT_CANDIDATE_GENERATOR_SOURCE,
        "scope": "pure_breakout_candidate_intent_generator_only",
        "does_not_import_strategy_modules": True,
        "does_not_execute_strategy_callables": True,
        "does_not_rank_candidates": True,
        "does_not_score_edge": True,
        "does_not_touch_runtime": True,
    }


__all__ = [
    "BREAKOUT_CANDIDATE_GENERATOR_SCHEMA_VERSION",
    "BREAKOUT_CANDIDATE_GENERATOR_SOURCE",
    "BREAKOUT_INVALID_NUMERIC_INPUT",
    "BREAKOUT_INVALID_PARAMETER",
    "BREAKOUT_INVALID_RANGE",
    "BREAKOUT_MISSING_INSTRUMENT",
    "BREAKOUT_MISSING_LTP",
    "BREAKOUT_MISSING_MARKET_STATE",
    "BREAKOUT_MISSING_RANGE",
    "BREAKOUT_NO_RANGE_BREAK",
    "BREAKOUT_VOLUME_NOT_CONFIRMED",
    "BreakoutCandidateGenerationReport",
    "build_breakout_candidate_intents",
]
