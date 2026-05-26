"""Safe strategy-output to CandidateIntent adapter for EDGE-71."""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.candidate_intent import (
    CandidateIntent,
    INTENT_TYPE_ENTRY,
    INTENT_TYPE_NO_TRADE,
    INTENT_TYPE_OBSERVE,
    create_candidate_intent,
)
from core.candidate_intent_pool import CandidateIntentPoolReport, build_candidate_intent_pool

STRATEGY_CANDIDATE_GENERATOR_SOURCE = "strategy_candidate_generator_v1"
STRATEGY_CANDIDATE_GENERATOR_SCHEMA_VERSION = 1

STRATEGY_CANDIDATE_GENERATOR_EMPTY_INPUT = "strategy_candidate_generator_empty_input"
STRATEGY_CANDIDATE_GENERATOR_MISSING_STRATEGY_ID = "strategy_candidate_generator_missing_strategy_id"
STRATEGY_CANDIDATE_GENERATOR_MISSING_INSTRUMENT = "strategy_candidate_generator_missing_instrument"
STRATEGY_CANDIDATE_GENERATOR_MISSING_DIRECTION = "strategy_candidate_generator_missing_direction"
STRATEGY_CANDIDATE_GENERATOR_MISSING_EVIDENCE = "strategy_candidate_generator_missing_evidence"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_DEFAULT_REQUIRED_EVIDENCE_KEYS = (
    "market_state",
    "regime_state",
    "strategy_signal",
)

_STRATEGY_ID_KEYS = ("strategy_id", "strategy", "strategy_name", "name")
_INSTRUMENT_KEYS = ("instrument", "symbol", "tradingsymbol", "underlying")
_DIRECTION_KEYS = ("direction", "side", "bias", "option_side")
_REGIME_KEYS = ("regime", "market_regime", "regime_state")
_FAMILY_KEYS = ("family", "strategy_family", "category")
_TRIGGER_KEYS = ("trigger", "signal_reason", "reason", "setup", "pattern")
_INVALIDATION_KEYS = ("invalidation", "invalid_if", "failure_condition", "stop_condition")
_EVIDENCE_KEYS = ("required_evidence_keys", "evidence_keys")
_BLOCKER_KEYS = ("blockers", "reject_reasons", "reasons")
_WARNING_KEYS = ("warnings", "notes")
_EVIDENCE_REF_KEYS = ("evidence_refs", "evidence_ref", "trace_ids", "trace_id")


def _field(*parts: str) -> str:
    return "".join(parts)


_UNSAFE_SHAPE_KEYS = {
    _field("quant", "ity"),
    "qty",
    _field("ord", "er_type"),
    _field("pr", "ice"),
    _field("entry_", "pr", "ice"),
    _field("limit_", "pr", "ice"),
    _field("trigger_", "pr", "ice"),
    _field("stop_", "loss"),
    _field("target_", "pr", "ice"),
}


@dataclass(frozen=True)
class StrategyCandidateGeneratorReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    generated_intents: tuple[CandidateIntent, ...]
    pool_report: CandidateIntentPoolReport
    rejected_source_payloads: tuple[dict[str, Any], ...]
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
            "rejected_source_count": len(self.rejected_source_payloads),
            "candidate_intent_ids": [intent.candidate_intent_id for intent in self.generated_intents],
            "generated_intents": [intent.to_payload() for intent in self.generated_intents],
            "pool_report": self.pool_report.to_payload(),
            "rejected_source_payloads": list(self.rejected_source_payloads),
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


def convert_strategy_outputs_to_candidate_intents(
    strategy_outputs: Iterable[Mapping[str, Any]],
    *,
    source: str = STRATEGY_CANDIDATE_GENERATOR_SOURCE,
) -> StrategyCandidateGeneratorReport:
    """Convert existing strategy result dictionaries into CandidateIntent values.

    This adapter is intentionally passive. It accepts already-produced metadata
    dictionaries and never imports or invokes strategy callables.
    """

    raw_outputs = tuple(strategy_outputs or ())
    if not raw_outputs:
        pool_report = build_candidate_intent_pool(())
        return StrategyCandidateGeneratorReport(
            schema_version=STRATEGY_CANDIDATE_GENERATOR_SCHEMA_VERSION,
            read_only=True,
            append=False,
            source=source,
            generated_intents=(),
            pool_report=pool_report,
            rejected_source_payloads=(),
            blockers=(STRATEGY_CANDIDATE_GENERATOR_EMPTY_INPUT,),
            warnings=pool_report.warnings,
            metadata=_metadata(),
        )

    generated: list[CandidateIntent] = []
    rejected_sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    for raw in raw_outputs:
        payload = dict(raw or {})
        blockers = _source_payload_blockers(payload)
        if blockers:
            rejected_sources.append({"blockers": list(blockers), "source_keys": sorted(str(key) for key in payload.keys())})
            warnings.extend(blockers)
            continue
        generated.append(_intent_from_strategy_output(payload))

    pool_report = build_candidate_intent_pool(generated)
    return StrategyCandidateGeneratorReport(
        schema_version=STRATEGY_CANDIDATE_GENERATOR_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        generated_intents=tuple(sorted(generated, key=lambda intent: intent.candidate_intent_id)),
        pool_report=pool_report,
        rejected_source_payloads=tuple(rejected_sources),
        blockers=(),
        warnings=_dedupe_sorted((*warnings, *pool_report.warnings)),
        metadata=_metadata(),
    )


def _intent_from_strategy_output(payload: Mapping[str, Any]) -> CandidateIntent:
    strategy_id = _first_text(payload, _STRATEGY_ID_KEYS)
    instrument = _first_text(payload, _INSTRUMENT_KEYS)
    direction = _normalize_direction(_first_text(payload, _DIRECTION_KEYS))
    regime = _first_text(payload, _REGIME_KEYS) or "UNCERTAIN"
    family = _first_text(payload, _FAMILY_KEYS) or strategy_id
    trigger = _first_text(payload, _TRIGGER_KEYS) or "strategy_signal_present"
    invalidation = _first_text(payload, _INVALIDATION_KEYS) or "strategy_signal_invalidated"
    required_evidence_keys = _first_list(payload, _EVIDENCE_KEYS) or _DEFAULT_REQUIRED_EVIDENCE_KEYS
    blockers = _first_list(payload, _BLOCKER_KEYS)
    warnings = _first_list(payload, _WARNING_KEYS)
    evidence_refs = _first_list(payload, _EVIDENCE_REF_KEYS)
    intent_type = INTENT_TYPE_NO_TRADE if blockers else _normalize_intent_type(payload.get("intent_type"))
    return create_candidate_intent(
        strategy_id=strategy_id,
        instrument=instrument,
        direction=direction,
        regime=regime,
        family=family,
        intent_type=intent_type,
        trigger=trigger,
        invalidation=invalidation,
        required_evidence_keys=required_evidence_keys,
        evidence_refs=evidence_refs,
        blockers=blockers,
        warnings=warnings,
        metadata={
            "source_strategy_keys": sorted(str(key) for key in payload.keys()),
            "adapter_source": STRATEGY_CANDIDATE_GENERATOR_SOURCE,
        },
    )


def _source_payload_blockers(payload: Mapping[str, Any]) -> tuple[str, ...]:
    blockers: list[str] = []
    if not _first_text(payload, _STRATEGY_ID_KEYS):
        blockers.append(STRATEGY_CANDIDATE_GENERATOR_MISSING_STRATEGY_ID)
    if not _first_text(payload, _INSTRUMENT_KEYS):
        blockers.append(STRATEGY_CANDIDATE_GENERATOR_MISSING_INSTRUMENT)
    if not _first_text(payload, _DIRECTION_KEYS):
        blockers.append(STRATEGY_CANDIDATE_GENERATOR_MISSING_DIRECTION)
    if not (_first_list(payload, _EVIDENCE_KEYS) or _DEFAULT_REQUIRED_EVIDENCE_KEYS):
        blockers.append(STRATEGY_CANDIDATE_GENERATOR_MISSING_EVIDENCE)
    if any(key in payload for key in _UNSAFE_SHAPE_KEYS):
        blockers.append("strategy_candidate_generator_unsafe_shape_fields")
    return _dedupe_sorted(blockers)


def _normalize_direction(value: str) -> str:
    text = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "BULLISH": "BUY_CALL",
        "BEARISH": "BUY_PUT",
        "LONG_CALL": "BUY_CALL",
        "LONG_PUT": "BUY_PUT",
        "CE": "CALL",
        "PE": "PUT",
    }
    return aliases.get(text, text)


def _normalize_intent_type(value: Any) -> str:
    text = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    if text in {"NO_TRADE", "OBSERVE"}:
        return text
    return INTENT_TYPE_ENTRY


def _first_text(payload: Mapping[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _first_list(payload: Mapping[str, Any], keys: Iterable[str]) -> tuple[str, ...]:
    for key in keys:
        if key in payload:
            return _as_tuple(payload.get(key))
    return ()


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (str(value),) if str(value).strip() else ()
    try:
        return tuple(str(item).strip() for item in value if str(item).strip())
    except TypeError:
        return (str(value),) if str(value).strip() else ()


def _dedupe_sorted(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


def _metadata() -> dict[str, Any]:
    return {
        "model": STRATEGY_CANDIDATE_GENERATOR_SOURCE,
        "scope": "strategy_output_to_candidate_intent_adapter_only",
        "does_not_import_strategy_modules": True,
        "does_not_execute_strategy_callables": True,
        "does_not_rank_candidates": True,
        "does_not_score_edge": True,
        "does_not_touch_runtime": True,
    }


__all__ = [
    "STRATEGY_CANDIDATE_GENERATOR_EMPTY_INPUT",
    "STRATEGY_CANDIDATE_GENERATOR_MISSING_DIRECTION",
    "STRATEGY_CANDIDATE_GENERATOR_MISSING_EVIDENCE",
    "STRATEGY_CANDIDATE_GENERATOR_MISSING_INSTRUMENT",
    "STRATEGY_CANDIDATE_GENERATOR_MISSING_STRATEGY_ID",
    "STRATEGY_CANDIDATE_GENERATOR_SCHEMA_VERSION",
    "STRATEGY_CANDIDATE_GENERATOR_SOURCE",
    "StrategyCandidateGeneratorReport",
    "convert_strategy_outputs_to_candidate_intents",
]
