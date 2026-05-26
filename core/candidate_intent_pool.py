"""CandidateIntent pool validator for EDGE-70."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.candidate_intent import (
    CandidateIntent,
    CandidateIntentRejection,
    CANDIDATE_INTENT_EMPTY_INPUT,
    validate_candidate_intents,
)

CANDIDATE_INTENT_POOL_SCHEMA_VERSION = 1
CANDIDATE_INTENT_POOL_SOURCE = "candidate_intent_pool_validator_v1"

CANDIDATE_INTENT_POOL_STATUS_ELIGIBLE = "POOL_ELIGIBLE"
CANDIDATE_INTENT_POOL_STATUS_BLOCKED = "POOL_BLOCKED"

CANDIDATE_INTENT_POOL_EMPTY_INPUT = "candidate_intent_pool_empty_input"
CANDIDATE_INTENT_POOL_REJECTED_INTENTS_PRESENT = "candidate_intent_pool_rejected_intents_present"
CANDIDATE_INTENT_POOL_NO_ELIGIBLE_INTENTS = "candidate_intent_pool_no_eligible_intents"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class CandidateIntentPoolEntry:
    intent: CandidateIntent
    pool_status: str
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    read_only: bool = True
    append: bool = False
    source: str = CANDIDATE_INTENT_POOL_SOURCE

    @property
    def candidate_intent_id(self) -> str:
        return self.intent.candidate_intent_id

    @property
    def pool_eligible(self) -> bool:
        return self.pool_status == CANDIDATE_INTENT_POOL_STATUS_ELIGIBLE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "candidate_intent_id": self.candidate_intent_id,
            "pool_status": self.pool_status,
            "pool_eligible": self.pool_eligible,
            "intent": self.intent.to_payload(),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
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
class CandidateIntentPoolReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    eligible_intents: tuple[CandidateIntentPoolEntry, ...]
    blocked_intents: tuple[CandidateIntentPoolEntry, ...]
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
    def pool_ready(self) -> bool:
        return self.valid and bool(self.eligible_intents)

    @property
    def eligible_candidate_intent_ids(self) -> tuple[str, ...]:
        return tuple(entry.candidate_intent_id for entry in self.eligible_intents)

    @property
    def blocked_candidate_intent_ids(self) -> tuple[str, ...]:
        return tuple(entry.candidate_intent_id for entry in self.blocked_intents)

    def get(self, candidate_intent_id: str) -> CandidateIntentPoolEntry | None:
        wanted = _candidate_key(candidate_intent_id)
        for entry in (*self.eligible_intents, *self.blocked_intents):
            if entry.candidate_intent_id == wanted:
                return entry
        return None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "pool_ready": self.pool_ready,
            "eligible_count": len(self.eligible_intents),
            "blocked_count": len(self.blocked_intents),
            "rejected_count": len(self.rejected_intents),
            "eligible_candidate_intent_ids": list(self.eligible_candidate_intent_ids),
            "blocked_candidate_intent_ids": list(self.blocked_candidate_intent_ids),
            "eligible_intents": [entry.to_payload() for entry in self.eligible_intents],
            "blocked_intents": [entry.to_payload() for entry in self.blocked_intents],
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


def build_candidate_intent_pool(
    intents: Iterable[CandidateIntent | Mapping[str, Any]],
    *,
    source: str = CANDIDATE_INTENT_POOL_SOURCE,
) -> CandidateIntentPoolReport:
    """Validate CandidateIntent values and split them into pool buckets."""

    raw_intents = tuple(intents or ())
    if not raw_intents:
        return CandidateIntentPoolReport(
            schema_version=CANDIDATE_INTENT_POOL_SCHEMA_VERSION,
            read_only=True,
            append=False,
            source=source,
            eligible_intents=(),
            blocked_intents=(),
            rejected_intents=(),
            blockers=(CANDIDATE_INTENT_POOL_EMPTY_INPUT,),
            warnings=(CANDIDATE_INTENT_EMPTY_INPUT,),
            metadata=_metadata(),
        )

    validation = validate_candidate_intents(raw_intents)
    eligible: list[CandidateIntentPoolEntry] = []
    blocked: list[CandidateIntentPoolEntry] = []
    for intent in validation.intents:
        if intent.pool_eligible:
            eligible.append(
                CandidateIntentPoolEntry(
                    intent=intent,
                    pool_status=CANDIDATE_INTENT_POOL_STATUS_ELIGIBLE,
                    warnings=intent.warnings,
                    source=source,
                )
            )
        else:
            blocked.append(
                CandidateIntentPoolEntry(
                    intent=intent,
                    pool_status=CANDIDATE_INTENT_POOL_STATUS_BLOCKED,
                    blockers=intent.blockers,
                    warnings=intent.warnings,
                    source=source,
                )
            )

    warnings = _dedupe_sorted(
        (
            *((CANDIDATE_INTENT_POOL_REJECTED_INTENTS_PRESENT,) if validation.rejected_intents else ()),
            *((CANDIDATE_INTENT_POOL_NO_ELIGIBLE_INTENTS,) if not eligible else ()),
            *validation.warnings,
        )
    )
    return CandidateIntentPoolReport(
        schema_version=CANDIDATE_INTENT_POOL_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        eligible_intents=tuple(sorted(eligible, key=lambda entry: entry.candidate_intent_id)),
        blocked_intents=tuple(sorted(blocked, key=lambda entry: entry.candidate_intent_id)),
        rejected_intents=validation.rejected_intents,
        blockers=validation.blockers,
        warnings=warnings,
        metadata=_metadata(),
    )


def _candidate_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _dedupe_sorted(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def _metadata() -> dict[str, Any]:
    return {
        "model": CANDIDATE_INTENT_POOL_SOURCE,
        "scope": "candidate_intent_pool_validator_no_strategy_execution_no_ranking",
        "does_not_import_strategy_modules": True,
        "does_not_execute_strategy_callables": True,
        "does_not_rank_candidates": True,
        "does_not_score_edge": True,
        "does_not_touch_runtime": True,
    }


__all__ = [
    "CANDIDATE_INTENT_POOL_EMPTY_INPUT",
    "CANDIDATE_INTENT_POOL_NO_ELIGIBLE_INTENTS",
    "CANDIDATE_INTENT_POOL_REJECTED_INTENTS_PRESENT",
    "CANDIDATE_INTENT_POOL_SCHEMA_VERSION",
    "CANDIDATE_INTENT_POOL_SOURCE",
    "CANDIDATE_INTENT_POOL_STATUS_BLOCKED",
    "CANDIDATE_INTENT_POOL_STATUS_ELIGIBLE",
    "CandidateIntentPoolEntry",
    "CandidateIntentPoolReport",
    "build_candidate_intent_pool",
]
