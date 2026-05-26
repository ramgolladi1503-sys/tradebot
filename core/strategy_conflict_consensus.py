"""Pure strategy conflict and consensus contract for EDGE-79."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.candidate_intent import CandidateIntent, INTENT_TYPE_ENTRY
from core.candidate_intent_pool import CandidateIntentPoolReport, build_candidate_intent_pool

STRATEGY_CONSENSUS_SCHEMA_VERSION = 1
STRATEGY_CONSENSUS_SOURCE = "strategy_conflict_consensus_v1"

CONSENSUS_STATUS_READY = "CONSENSUS_READY"
CONSENSUS_STATUS_BLOCKED = "CONSENSUS_BLOCKED"

CONSENSUS_EMPTY_CANDIDATES = "consensus_empty_candidates"
CONSENSUS_NO_ELIGIBLE_ENTRY = "consensus_no_eligible_entry"
CONSENSUS_DIRECTION_CONFLICT = "consensus_direction_conflict"
CONSENSUS_FAMILY_CONFLICT = "consensus_family_conflict"
CONSENSUS_UNSUPPORTED_DIRECTION = "consensus_unsupported_direction"
CONSENSUS_MISSING_INSTRUMENT = "consensus_missing_instrument"
CONSENSUS_CANDIDATE_NOT_POOL_ELIGIBLE = "consensus_candidate_not_pool_eligible"
CONSENSUS_NON_ENTRY_INTENT = "consensus_non_entry_intent"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_CALL_DIRECTIONS = {"BUY_CALL", "CALL", "CALL_BIAS"}
_PUT_DIRECTIONS = {"BUY_PUT", "PUT", "PUT_BIAS"}
_SUPPORTED_DIRECTIONS = _CALL_DIRECTIONS | _PUT_DIRECTIONS


@dataclass(frozen=True)
class StrategyConsensusDecision:
    consensus_id: str
    instrument: str
    status: str
    direction_group: str
    candidate_intent_ids: tuple[str, ...]
    family_ids: tuple[str, ...]
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = STRATEGY_CONSENSUS_SOURCE

    @property
    def ready(self) -> bool:
        return self.status == CONSENSUS_STATUS_READY and not self.blockers

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
            "consensus_id": self.consensus_id,
            "instrument": self.instrument,
            "status": self.status,
            "ready": self.ready,
            "direction_group": self.direction_group,
            "candidate_intent_ids": list(self.candidate_intent_ids),
            "family_ids": list(self.family_ids),
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
class StrategyConsensusReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    decisions: tuple[StrategyConsensusDecision, ...]
    pool_report: CandidateIntentPoolReport
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def ready_decisions(self) -> tuple[StrategyConsensusDecision, ...]:
        return tuple(decision for decision in self.decisions if decision.ready)

    @property
    def blocked_decisions(self) -> tuple[StrategyConsensusDecision, ...]:
        return tuple(decision for decision in self.decisions if not decision.ready)

    @property
    def consensus_ready(self) -> bool:
        return not self.blockers and bool(self.ready_decisions) and self.pool_report.valid

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
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "consensus_ready": self.consensus_ready,
            "decision_count": len(self.decisions),
            "ready_count": len(self.ready_decisions),
            "blocked_count": len(self.blocked_decisions),
            "ready_consensus_ids": [decision.consensus_id for decision in self.ready_decisions],
            "blocked_consensus_ids": [decision.consensus_id for decision in self.blocked_decisions],
            "decisions": [decision.to_payload() for decision in self.decisions],
            "pool_report": self.pool_report.to_payload(),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        _mark_non_action(payload)
        return payload


def build_strategy_conflict_consensus(
    candidates: Iterable[CandidateIntent | Mapping[str, Any]],
    *,
    source: str = STRATEGY_CONSENSUS_SOURCE,
) -> StrategyConsensusReport:
    """Build read-only consensus decisions from eligible CandidateIntent values."""

    pool_report = build_candidate_intent_pool(tuple(candidates or ()))
    decisions: list[StrategyConsensusDecision] = []
    eligible_entries: list[CandidateIntent] = []

    for entry in pool_report.eligible_intents:
        intent = entry.intent
        blockers = _intent_blockers(intent)
        if blockers:
            decisions.append(_blocked_intent_decision(intent, blockers=blockers, source=source))
        else:
            eligible_entries.append(intent)

    for entry in pool_report.blocked_intents:
        decisions.append(
            _blocked_intent_decision(
                entry.intent,
                blockers=_dedupe((CONSENSUS_CANDIDATE_NOT_POOL_ELIGIBLE, *entry.blockers)),
                source=source,
            )
        )

    grouped: dict[str, list[CandidateIntent]] = defaultdict(list)
    for intent in eligible_entries:
        grouped[_instrument_key(intent.instrument)].append(intent)

    for instrument, intents in grouped.items():
        decisions.extend(_instrument_decisions(instrument, intents, source=source))

    report_blockers = _report_blockers(pool_report, decisions)
    return StrategyConsensusReport(
        schema_version=STRATEGY_CONSENSUS_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        decisions=tuple(sorted(decisions, key=lambda item: item.consensus_id)),
        pool_report=pool_report,
        blockers=report_blockers,
        warnings=_dedupe((*pool_report.warnings,)),
        metadata={
            "model": STRATEGY_CONSENSUS_SOURCE,
            "scope": "pure_strategy_conflict_consensus_contract_no_runtime_wiring",
            "grouping": "instrument_direction_family",
            "does_not_import_strategy_modules": True,
            "does_not_execute_strategy_callables": True,
            "does_not_rank_candidates": True,
            "does_not_score_edge": True,
            "does_not_touch_runtime": True,
            "does_not_emit_lifecycle_mutation": True,
        },
    )


def _instrument_decisions(
    instrument: str,
    intents: list[CandidateIntent],
    *,
    source: str,
) -> tuple[StrategyConsensusDecision, ...]:
    by_direction: dict[str, list[CandidateIntent]] = defaultdict(list)
    for intent in intents:
        by_direction[_direction_group(intent.direction)].append(intent)

    if len(by_direction) > 1:
        return (
            StrategyConsensusDecision(
                consensus_id=_consensus_id(instrument, "conflict"),
                instrument=instrument,
                status=CONSENSUS_STATUS_BLOCKED,
                direction_group="CONFLICT",
                candidate_intent_ids=_candidate_ids(intents),
                family_ids=_family_ids(intents),
                blockers=(CONSENSUS_DIRECTION_CONFLICT,),
                metadata={
                    "direction_groups": sorted(by_direction),
                    "reason": "opposing_direction_groups_for_same_instrument",
                },
                source=source,
            ),
        )

    direction_group = next(iter(by_direction.keys()), "UNKNOWN")
    same_direction_intents = next(iter(by_direction.values()), [])
    duplicate_families = _duplicate_families(same_direction_intents)
    if duplicate_families:
        return (
            StrategyConsensusDecision(
                consensus_id=_consensus_id(instrument, direction_group),
                instrument=instrument,
                status=CONSENSUS_STATUS_BLOCKED,
                direction_group=direction_group,
                candidate_intent_ids=_candidate_ids(same_direction_intents),
                family_ids=_family_ids(same_direction_intents),
                blockers=(CONSENSUS_FAMILY_CONFLICT,),
                metadata={
                    "duplicate_families": duplicate_families,
                    "reason": "multiple_candidates_from_same_family_for_same_direction",
                },
                source=source,
            ),
        )

    return (
        StrategyConsensusDecision(
            consensus_id=_consensus_id(instrument, direction_group),
            instrument=instrument,
            status=CONSENSUS_STATUS_READY,
            direction_group=direction_group,
            candidate_intent_ids=_candidate_ids(same_direction_intents),
            family_ids=_family_ids(same_direction_intents),
            metadata={
                "family_count": len(_family_ids(same_direction_intents)),
                "candidate_count": len(same_direction_intents),
                "reason": "same_direction_family_consensus",
            },
            source=source,
        ),
    )


def _intent_blockers(intent: CandidateIntent) -> tuple[str, ...]:
    blockers: list[str] = []
    if intent.intent_type != INTENT_TYPE_ENTRY:
        blockers.append(CONSENSUS_NON_ENTRY_INTENT)
    if _direction_group(intent.direction) == "UNKNOWN":
        blockers.append(CONSENSUS_UNSUPPORTED_DIRECTION)
    if not _instrument_key(intent.instrument):
        blockers.append(CONSENSUS_MISSING_INSTRUMENT)
    return _dedupe(blockers)


def _blocked_intent_decision(
    intent: CandidateIntent,
    *,
    blockers: tuple[str, ...],
    source: str,
) -> StrategyConsensusDecision:
    instrument = _instrument_key(intent.instrument) or "UNKNOWN"
    return StrategyConsensusDecision(
        consensus_id=_consensus_id(instrument, intent.candidate_intent_id),
        instrument=instrument,
        status=CONSENSUS_STATUS_BLOCKED,
        direction_group=_direction_group(intent.direction),
        candidate_intent_ids=(intent.candidate_intent_id,),
        family_ids=(_family_key(intent.family),),
        blockers=_dedupe(blockers),
        warnings=intent.warnings,
        metadata={
            "candidate_intent_id": intent.candidate_intent_id,
            "strategy_id": intent.strategy_id,
            "intent_type": intent.intent_type,
            "does_not_touch_runtime": True,
            "does_not_emit_lifecycle_mutation": True,
        },
        source=source,
    )


def _report_blockers(
    pool_report: CandidateIntentPoolReport,
    decisions: list[StrategyConsensusDecision],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not decisions:
        blockers.append(CONSENSUS_EMPTY_CANDIDATES)
    if not any(decision.ready for decision in decisions):
        blockers.append(CONSENSUS_NO_ELIGIBLE_ENTRY)
    blockers.extend(pool_report.blockers)
    return _dedupe(blockers)


def _direction_group(direction: Any) -> str:
    key = str(direction or "").strip().upper().replace(" ", "_").replace("-", "_")
    if key in _CALL_DIRECTIONS:
        return "CALL"
    if key in _PUT_DIRECTIONS:
        return "PUT"
    if key in _SUPPORTED_DIRECTIONS:
        return key
    return "UNKNOWN"


def _instrument_key(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _family_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _candidate_ids(intents: Iterable[CandidateIntent]) -> tuple[str, ...]:
    return tuple(sorted(intent.candidate_intent_id for intent in intents))


def _family_ids(intents: Iterable[CandidateIntent]) -> tuple[str, ...]:
    return tuple(sorted({_family_key(intent.family) for intent in intents}))


def _duplicate_families(intents: Iterable[CandidateIntent]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for intent in intents:
        family = _family_key(intent.family)
        if family in seen:
            duplicates.add(family)
        seen.add(family)
    return tuple(sorted(duplicates))


def _consensus_id(instrument: str, suffix: str) -> str:
    return f"{_instrument_key(instrument).lower()}:{str(suffix).lower().replace(' ', '_').replace('-', '_')}:consensus"


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ORDER_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "CONSENSUS_CANDIDATE_NOT_POOL_ELIGIBLE",
    "CONSENSUS_DIRECTION_CONFLICT",
    "CONSENSUS_EMPTY_CANDIDATES",
    "CONSENSUS_FAMILY_CONFLICT",
    "CONSENSUS_MISSING_INSTRUMENT",
    "CONSENSUS_NO_ELIGIBLE_ENTRY",
    "CONSENSUS_NON_ENTRY_INTENT",
    "CONSENSUS_STATUS_BLOCKED",
    "CONSENSUS_STATUS_READY",
    "CONSENSUS_UNSUPPORTED_DIRECTION",
    "STRATEGY_CONSENSUS_SCHEMA_VERSION",
    "STRATEGY_CONSENSUS_SOURCE",
    "StrategyConsensusDecision",
    "StrategyConsensusReport",
    "build_strategy_conflict_consensus",
]
