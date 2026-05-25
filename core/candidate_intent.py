"""Read-only CandidateIntent contract for EDGE-69."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

CANDIDATE_INTENT_SCHEMA_VERSION = 1
CANDIDATE_INTENT_SOURCE = "candidate_intent_contract_v1"

INTENT_TYPE_ENTRY = "ENTRY"
INTENT_TYPE_EXIT = "EXIT"
INTENT_TYPE_NO_TRADE = "NO_TRADE"
INTENT_TYPE_OBSERVE = "OBSERVE"

CANDIDATE_INTENT_ACCEPTED = "ACCEPTED"
CANDIDATE_INTENT_REJECTED = "REJECTED"

CANDIDATE_INTENT_EMPTY_INPUT = "candidate_intent_empty_input"
CANDIDATE_INTENT_MISSING_FIELD = "candidate_intent_missing_field"
CANDIDATE_INTENT_INVALID_DIRECTION = "candidate_intent_invalid_direction"
CANDIDATE_INTENT_INVALID_TYPE = "candidate_intent_invalid_type"
CANDIDATE_INTENT_INVALID_SAFETY_FLAGS = "candidate_intent_invalid_safety_flags"
CANDIDATE_INTENT_FORBIDDEN_ACTION_FIELD = "candidate_intent_forbidden_action_field"
CANDIDATE_INTENT_DUPLICATE_ID = "candidate_intent_duplicate_id"
CANDIDATE_INTENT_MALFORMED_PAYLOAD = "candidate_intent_malformed_payload"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_ALLOWED_INTENT_TYPES = {INTENT_TYPE_ENTRY, INTENT_TYPE_EXIT, INTENT_TYPE_NO_TRADE, INTENT_TYPE_OBSERVE}
_ALLOWED_DIRECTIONS = {
    "BUY",
    "SELL",
    "BUY_CALL",
    "BUY_PUT",
    "SELL_CALL",
    "SELL_PUT",
    "CALL",
    "PUT",
    "CALL_BIAS",
    "PUT_BIAS",
    "LONG",
    "SHORT",
    "NEUTRAL",
    "NO_TRADE",
}
_REQUIRED_FIELDS = (
    "candidate_intent_id",
    "strategy_id",
    "instrument",
    "direction",
    "regime",
    "family",
    "intent_type",
    "trigger",
    "invalidation",
    "required_evidence_keys",
)


def _field(*parts: str) -> str:
    return "".join(parts)


_FORBIDDEN_ACTION_FIELDS = {
    _field("quant", "ity"),
    "qty",
    _field("ord", "er_type"),
    _field("pr", "ice"),
    _field("entry_", "pr", "ice"),
    _field("limit_", "pr", "ice"),
    _field("trigger_", "pr", "ice"),
    _field("stop_", "loss"),
    _field("target_", "pr", "ice"),
    _field("place", "_", "order"),
    _field("modify", "_", "order"),
    _field("cancel", "_", "order"),
}


@dataclass(frozen=True)
class CandidateIntent:
    candidate_intent_id: str
    strategy_id: str
    instrument: str
    direction: str
    regime: str
    family: str
    intent_type: str
    trigger: str
    invalidation: str
    required_evidence_keys: tuple[str, ...]
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = CANDIDATE_INTENT_SOURCE

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
    def structurally_valid(self) -> bool:
        return not _candidate_structural_blockers(self._structural_payload())

    @property
    def pool_eligible(self) -> bool:
        return self.structurally_valid and not self.blockers

    def _structural_payload(self) -> dict[str, Any]:
        return {
            "candidate_intent_id": self.candidate_intent_id,
            "strategy_id": self.strategy_id,
            "instrument": self.instrument,
            "direction": self.direction,
            "regime": self.regime,
            "family": self.family,
            "intent_type": self.intent_type,
            "trigger": self.trigger,
            "invalidation": self.invalidation,
            "required_evidence_keys": list(self.required_evidence_keys),
            "read_only": self.read_only,
            "append": self.append,
        }

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": CANDIDATE_INTENT_SCHEMA_VERSION,
            "candidate_intent_id": self.candidate_intent_id,
            "strategy_id": self.strategy_id,
            "instrument": self.instrument,
            "direction": self.direction,
            "regime": self.regime,
            "family": self.family,
            "intent_type": self.intent_type,
            "trigger": self.trigger,
            "invalidation": self.invalidation,
            "required_evidence_keys": list(self.required_evidence_keys),
            "evidence_refs": list(self.evidence_refs),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "pool_eligible": self.pool_eligible,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        payload["live_order_action"] = False
        payload["broker_order_action"] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


@dataclass(frozen=True)
class CandidateIntentRejection:
    candidate_intent_id: str
    status: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = CANDIDATE_INTENT_SOURCE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "candidate_intent_id": self.candidate_intent_id,
            "status": self.status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        payload["live_order_action"] = False
        payload["broker_order_action"] = False
        return payload


@dataclass(frozen=True)
class CandidateIntentValidationReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    intents: tuple[CandidateIntent, ...]
    rejected_intents: tuple[CandidateIntentRejection, ...]
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
        return not self.blockers and not self.rejected_intents

    @property
    def candidate_intent_ids(self) -> tuple[str, ...]:
        return tuple(intent.candidate_intent_id for intent in self.intents)

    def get(self, candidate_intent_id: str) -> CandidateIntent | None:
        wanted = _candidate_key(candidate_intent_id)
        return next((intent for intent in self.intents if intent.candidate_intent_id == wanted), None)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "intent_count": len(self.intents),
            "rejected_count": len(self.rejected_intents),
            "candidate_intent_ids": list(self.candidate_intent_ids),
            "intents": [intent.to_payload() for intent in self.intents],
            "rejected_intents": [intent.to_payload() for intent in self.rejected_intents],
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

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def create_candidate_intent(
    *,
    strategy_id: str,
    instrument: str,
    direction: str,
    regime: str,
    family: str,
    trigger: str,
    invalidation: str,
    required_evidence_keys: Iterable[str],
    intent_type: str = INTENT_TYPE_ENTRY,
    candidate_intent_id: str | None = None,
    evidence_refs: Iterable[str] = (),
    blockers: Iterable[str] = (),
    warnings: Iterable[str] = (),
    metadata: Mapping[str, Any] | None = None,
) -> CandidateIntent:
    normalized_direction = _upper(direction)
    normalized_regime = _upper(regime)
    normalized_type = _upper(intent_type)
    intent_id = candidate_intent_id or _candidate_key(
        f"{strategy_id}:{instrument}:{normalized_direction}:{normalized_regime}:{normalized_type}"
    )
    return CandidateIntent(
        candidate_intent_id=_candidate_key(intent_id),
        strategy_id=_candidate_key(strategy_id),
        instrument=_upper(instrument),
        direction=normalized_direction,
        regime=normalized_regime,
        family=_candidate_key(family),
        intent_type=normalized_type,
        trigger=str(trigger or "").strip(),
        invalidation=str(invalidation or "").strip(),
        required_evidence_keys=_lower_tuple(required_evidence_keys),
        evidence_refs=_lower_tuple(evidence_refs),
        blockers=_lower_tuple(blockers),
        warnings=_lower_tuple(warnings),
        metadata=dict(metadata or {}),
    )


def validate_candidate_intent(
    intent: CandidateIntent | Mapping[str, Any],
    *,
    source: str = CANDIDATE_INTENT_SOURCE,
) -> CandidateIntentValidationReport:
    return validate_candidate_intents((intent,), source=source)


def validate_candidate_intents(
    intents: Iterable[CandidateIntent | Mapping[str, Any]],
    *,
    source: str = CANDIDATE_INTENT_SOURCE,
) -> CandidateIntentValidationReport:
    raw_intents = tuple(intents or ())
    if not raw_intents:
        return CandidateIntentValidationReport(
            CANDIDATE_INTENT_SCHEMA_VERSION,
            True,
            False,
            source,
            (),
            (),
            (CANDIDATE_INTENT_EMPTY_INPUT,),
            (),
            _metadata(),
        )

    accepted: list[CandidateIntent] = []
    rejected: list[CandidateIntentRejection] = []
    seen: set[str] = set()
    for raw in raw_intents:
        if isinstance(raw, CandidateIntent):
            payload = raw.to_payload()
        elif isinstance(raw, Mapping):
            payload = dict(raw)
        else:
            payload = {
                "candidate_intent_id": "unknown_candidate_intent",
                "blockers": (CANDIDATE_INTENT_MALFORMED_PAYLOAD,),
            }
        intent_id = _candidate_key(payload.get("candidate_intent_id") or "")
        blockers = _candidate_structural_blockers(payload)
        if intent_id and intent_id in seen:
            blockers = _dedupe_sorted((*blockers, CANDIDATE_INTENT_DUPLICATE_ID))
        if blockers:
            rejected.append(CandidateIntentRejection(intent_id or "unknown_candidate_intent", CANDIDATE_INTENT_REJECTED, blockers))
            continue
        seen.add(intent_id)
        accepted.append(_intent_from_payload(payload))

    warnings = _dedupe_sorted(blocker for item in rejected for blocker in item.blockers)
    return CandidateIntentValidationReport(
        CANDIDATE_INTENT_SCHEMA_VERSION,
        True,
        False,
        source,
        tuple(sorted(accepted, key=lambda item: item.candidate_intent_id)),
        tuple(rejected),
        (),
        warnings,
        _metadata(),
    )


def _intent_from_payload(payload: Mapping[str, Any]) -> CandidateIntent:
    return create_candidate_intent(
        candidate_intent_id=str(payload.get("candidate_intent_id") or ""),
        strategy_id=str(payload.get("strategy_id") or ""),
        instrument=str(payload.get("instrument") or ""),
        direction=str(payload.get("direction") or ""),
        regime=str(payload.get("regime") or ""),
        family=str(payload.get("family") or ""),
        intent_type=str(payload.get("intent_type") or INTENT_TYPE_ENTRY),
        trigger=str(payload.get("trigger") or ""),
        invalidation=str(payload.get("invalidation") or ""),
        required_evidence_keys=_as_iterable(payload.get("required_evidence_keys")),
        evidence_refs=_as_iterable(payload.get("evidence_refs")),
        blockers=_as_iterable(payload.get("blockers")),
        warnings=_as_iterable(payload.get("warnings")),
        metadata=dict(payload.get("metadata") or {}),
    )


def _candidate_structural_blockers(payload: Mapping[str, Any]) -> tuple[str, ...]:
    blockers: list[str] = []
    for field_name in _REQUIRED_FIELDS:
        value = payload.get(field_name)
        if field_name == "required_evidence_keys":
            if not _lower_tuple(_as_iterable(value)):
                blockers.append(CANDIDATE_INTENT_MISSING_FIELD)
        elif not str(value or "").strip():
            blockers.append(CANDIDATE_INTENT_MISSING_FIELD)
    if _upper(payload.get("direction")) not in _ALLOWED_DIRECTIONS:
        blockers.append(CANDIDATE_INTENT_INVALID_DIRECTION)
    if _upper(payload.get("intent_type")) not in _ALLOWED_INTENT_TYPES:
        blockers.append(CANDIDATE_INTENT_INVALID_TYPE)
    if _has_unsafe_flags(payload):
        blockers.append(CANDIDATE_INTENT_INVALID_SAFETY_FLAGS)
    if any(key in payload for key in _FORBIDDEN_ACTION_FIELDS):
        blockers.append(CANDIDATE_INTENT_FORBIDDEN_ACTION_FIELD)
    if CANDIDATE_INTENT_MALFORMED_PAYLOAD in _lower_tuple(_as_iterable(payload.get("blockers"))):
        blockers.append(CANDIDATE_INTENT_MALFORMED_PAYLOAD)
    return _dedupe_sorted(blockers)


def _has_unsafe_flags(payload: Mapping[str, Any]) -> bool:
    unsafe_true_keys = (_ORDER_ACTION_KEY, _BROKER_KEY, "live_order_action", "broker_order_action")
    return any(_truthy(payload.get(key)) for key in unsafe_true_keys) or payload.get("read_only") is False or _truthy(payload.get("append"))


def _candidate_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _upper(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _lower_tuple(value: Iterable[Any]) -> tuple[str, ...]:
    return tuple(str(item).strip().lower() for item in value if str(item).strip())


def _as_iterable(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _dedupe_sorted(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def _metadata() -> dict[str, Any]:
    return {
        "model": CANDIDATE_INTENT_SOURCE,
        "scope": "candidate_intent_contract_no_pool_no_strategy_execution_no_ranking",
        "does_not_import_strategy_modules": True,
        "does_not_execute_strategy_callables": True,
        "does_not_rank_candidates": True,
        "does_not_score_edge": True,
        "does_not_create_order_intent": True,
    }


__all__ = [
    "CANDIDATE_INTENT_DUPLICATE_ID",
    "CANDIDATE_INTENT_EMPTY_INPUT",
    "CANDIDATE_INTENT_FORBIDDEN_ACTION_FIELD",
    "CANDIDATE_INTENT_INVALID_DIRECTION",
    "CANDIDATE_INTENT_INVALID_SAFETY_FLAGS",
    "CANDIDATE_INTENT_INVALID_TYPE",
    "CANDIDATE_INTENT_MALFORMED_PAYLOAD",
    "CANDIDATE_INTENT_MISSING_FIELD",
    "CANDIDATE_INTENT_SCHEMA_VERSION",
    "CANDIDATE_INTENT_SOURCE",
    "INTENT_TYPE_ENTRY",
    "INTENT_TYPE_EXIT",
    "INTENT_TYPE_NO_TRADE",
    "INTENT_TYPE_OBSERVE",
    "CandidateIntent",
    "CandidateIntentRejection",
    "CandidateIntentValidationReport",
    "create_candidate_intent",
    "validate_candidate_intent",
    "validate_candidate_intents",
]
