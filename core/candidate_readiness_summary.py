"""Read-only candidate readiness summary contract for EDGE-73.

This module consumes EDGE-72 hard downgrade decisions and produces aggregate
readiness evidence. It does not rank candidates, score edge, select strategies,
or wire runtime behavior.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.candidate_hard_downgrade import (
    DOWNGRADE_DECISION_ADVISORY_ONLY,
    DOWNGRADE_DECISION_BLOCKED,
    DOWNGRADE_DECISION_CANDIDATE_READY,
    CandidateHardDowngradeDecision,
    CandidateHardDowngradeReport,
)

CANDIDATE_READINESS_SUMMARY_SCHEMA_VERSION = 1
CANDIDATE_READINESS_SUMMARY_SOURCE = "candidate_readiness_summary_v1"

READINESS_SUMMARY_EMPTY_INPUT = "candidate_readiness_summary_empty_input"
READINESS_SUMMARY_DOWNGRADE_INVALID = "candidate_readiness_summary_downgrade_invalid"
READINESS_SUMMARY_MALFORMED_DECISION = "candidate_readiness_summary_malformed_decision"
READINESS_SUMMARY_UNKNOWN_DECISION = "candidate_readiness_summary_unknown_decision"

READINESS_STATE_READY = "READY"
READINESS_STATE_ADVISORY_ONLY = "ADVISORY_ONLY"
READINESS_STATE_BLOCKED = "BLOCKED"
READINESS_STATE_INVALID = "INVALID"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"



@dataclass(frozen=True)
class CandidateReadinessSummary:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    readiness_state: str
    total_count: int
    ready_count: int
    advisory_only_count: int
    blocked_count: int
    invalid_count: int
    candidate_ready_ids: tuple[str, ...]
    advisory_only_ids: tuple[str, ...]
    blocked_ids: tuple[str, ...]
    reason_counts: dict[str, int]
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
        return not self.blockers

    @property
    def has_ready_candidates(self) -> bool:
        return self.ready_count > 0

    @property
    def has_only_advisory_candidates(self) -> bool:
        return self.ready_count == 0 and self.advisory_only_count > 0 and self.blocked_count == 0

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "readiness_state": self.readiness_state,
            "total_count": self.total_count,
            "ready_count": self.ready_count,
            "advisory_only_count": self.advisory_only_count,
            "blocked_count": self.blocked_count,
            "invalid_count": self.invalid_count,
            "has_ready_candidates": self.has_ready_candidates,
            "has_only_advisory_candidates": self.has_only_advisory_candidates,
            "candidate_ready_ids": list(self.candidate_ready_ids),
            "advisory_only_ids": list(self.advisory_only_ids),
            "blocked_ids": list(self.blocked_ids),
            "reason_counts": dict(sorted(self.reason_counts.items())),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def summarize_candidate_readiness(
    decisions: CandidateHardDowngradeReport | Iterable[CandidateHardDowngradeDecision | Mapping[str, Any]],
    *,
    source: str = CANDIDATE_READINESS_SUMMARY_SOURCE,
) 
-> CandidateReadinessSummary:
    """Summarize EDGE-72 readiness decisions without ranking or selection."""

    downgrade_invalid = isinstance(decisions, CandidateHardDowngradeReport) and not decisions.valid
    active_decisions, blocked_decisions, downgrade_blockers = _resolve_decisions(decisions)
    report_blockers = _dedupe_sorted(
        (
            *((READINESS_SUMMARY_EMPTY_INPUT,) if not active_decisions and not blocked_decisions else ()),
            *((READINESS_SUMMARY_DOWNGRADE_INVALID,) if downgrade_invalid else ()),
            *(_prefixed_downgrade_blockers(downgrade_blockers) if downgrade_invalid else ()),
        )
    )

    coerced_active = tuple(_coerce_decision(decision) for decision in active_decisions)
    coerced_blocked = tuple(_coerce_decision(decision) for decision in blocked_decisions)
    malformed_blockers = _dedupe_sorted(
        READINESS_SUMMARY_MALFORMED_DECISION
        for decision in (*coerced_active, *coerced_blocked)
        if _is_malformed_decision(decision)
    )
    unknown_decision_warnings = _dedupe_sorted(
        READINESS_SUMMARY_UNKNOWN_DECISION
        for decision in (*coerced_active, *coerced_blocked)
        if decision.decision not in {
            DOWNGRADE_DECISION_CANDIDATE_READY,
            DOWNGRADE_DECISION_ADVISORY_ONLY,
            DOWNGRADE_DECISION_BLOCKED,
        }
    )
    blockers = _dedupe_sorted((*report_blockers, *malformed_blockers))

    ready = tuple(
        decision
        for decision in coerced_active
        if decision.decision == DOWNGRADE_DECISION_CANDIDATE_READY and not blockers
    )
    advisory = tuple(
        decision
        for decision in coerced_active
        if decision.decision == DOWNGRADE_DECISION_ADVISORY_ONLY and not blockers
    )
    blocked = tuple(
        decision
        for decision in (*coerced_blocked, *coerced_active)
        if decision.decision == DOWNGRADE_DECISION_BLOCKED or blockers
    )
    valid_decisions = {
        DOWNGRADE_DECISION_CANDIDATE_READY,
        DOWNGRADE_DECISION_ADVISORY_ONLY,
        DOWNGRADE_DECISION_BLOCKED,
    }
    invalid_count = len(
        [
            decision
            for decision in (*coerced_active, *coerced_blocked)
            if decision.decision not in valid_decisions
        ]
    )

    reason_counts = _reason_counts((*advisory, *blocked))
    readiness_state = _readiness_state(
        blockers=blockers,
        ready_count=len(ready),
        advisory_only_count=len(advisory),
        blocked_count=len(blocked),
    )
    warnings = _dedupe_sorted(
        (
            *unknown_decision_warnings,
            *(warning for decision in (*coerced_active, *coerced_blocked) for warning in decision.warnings),
        )
    )
    return CandidateReadinessSummary(
        schema_version=CANDIDATE_READINESS_SUMMARY_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        readiness_state=readiness_state,
        total_count=len(coerced_active) + len(coerced_blocked),
        ready_count=len(ready),
        advisory_only_count=len(advisory),
        blocked_count=len(blocked),
        invalid_count=invalid_count,
        candidate_ready_ids=tuple(sorted(decision.canonical_candidate_id for decision in ready)),
        advisory_only_ids=tuple(sorted(decision.canonical_candidate_id for decision in advisory)),
        blocked_ids=tuple(sorted(decision.canonical_candidate_id for decision in blocked)),
        reason_counts=reason_counts,
        blockers=blockers,
        warnings=warnings,
        metadata=_metadata(),
    )


def _resolve_decisions(
    decisions: CandidateHardDowngradeReport | Iterable[CandidateHardDowngradeDecision | Mapping[str, Any]],
) -> tuple[
    tuple[CandidateHardDowngradeDecision | Mapping[str, Any], ...],
    tuple[CandidateHardDowngradeDecision | Mapping[str, Any], ...],
    tuple[str, ...],
]:
    if isinstance(decisions, CandidateHardDowngradeReport):
        return tuple(decisions.decisions), tuple(decisions.blocked_decisions), tuple(decisions.blockers)
    if decisions is None:
        return (), (), ()
    return tuple(decisions), (), ()


def _coerce_decision(decision: CandidateHardDowngradeDecision | Mapping[str, Any]) -> CandidateHardDowngradeDecision:
    if isinstance(decision, CandidateHardDowngradeDecision):
        return decision
    if not isinstance(decision, Mapping):
        return CandidateHardDowngradeDecision(
            canonical_candidate_id="",
            strategy_id="",
            decision=DOWNGRADE_DECISION_BLOCKED,
            hard_downgraded=True,
            candidate_ready=False,
            advisory_only=False,
            blocked=True,
            reasons=(READINESS_SUMMARY_MALFORMED_DECISION,),
            blockers=(READINESS_SUMMARY_MALFORMED_DECISION,),
            metadata={"coercion_error": type(decision).__name__},
        )
    decision_value = str(decision.get("decision") or "").strip().upper()
    return CandidateHardDowngradeDecision(
        canonical_candidate_id=_candidate_key(decision.get("canonical_candidate_id")),
        strategy_id=_candidate_key(decision.get("strategy_id")),
        decision=decision_value,
        hard_downgraded=_truthy(decision.get("hard_downgraded")),
        candidate_ready=_truthy(decision.get("candidate_ready")),
        advisory_only=_truthy(decision.get("advisory_only")),
        blocked=_truthy(decision.get("blocked"))€™X\ЫЫњПWЭ\JXЪ\Ъ[Ы‹™Щ]
њ™X\ЫЫњИЉHЬ€

JK€›ШЪЩ\њПWЭ\JXЪ\Ъ[Ы‹™Щ]
›ШЪЩ\њИЉHЬ€

JK€Ш\›љ[™ЬПWЭ\JXЪ\Ъ[Ы‹™Щ]
ќШ\›љ[™ЬИЉHЬ€

JK€X™[ПWЭ\JXЪ\Ъ[Ы‹™Щ]
›X™[ИЉHЬ€

JK€Y]Y]OWЬШY™WЩXЭ
XЪ\Ъ[Ы‹™Щ]
›Y]Y]HЉJK€
B‚‚™Y€Ъ\ЧЫX[›Ь›YYЩXЪ\Ъ[ЫЉXЪ\Ъ[ЫЋ€Ш[™Y]R\™ЭЫ™ЬYQXЪ\Ъ[ЫЉHO€›ЫЫ‚€Y€›ЭXЪ\Ъ[Ы‹Ш[›ЫљXШ[ШШ[™Y]WЪY‚€™]\›€ќYB€Y€XЪ\Ъ[Ы‹™XЪ\Ъ[Ы€OHХУ‘ФђQWСPТTТSУ—Р“РТСQ‚€™]\›€[ЩB€™]\›€›ЭXЪ\Ъ[Ы‹њЭ]YЮWЪY‚‚™Y€Ь™XY[™\ЬЧЬЭ]J€
‹€›ШЪЩ\њО€\VЬЭ‹‹‹—K€™XYWШЫЭ[ќ€[ќ€Yљ\ЫЬћWЫЫ›WШЫЭ[ќ€[ќ€›ШЪЩYШЫЭ[ќ€[ќЉHO€ЭЋ‚€Y€›ШЪЩ\њО‚€™]\›€‘PQS‘TФЧФХUWТS•ђSQ€Y€™XYWШЫЭ[ќ€‚€™]\›€‘PQS‘TФЧФХUWФ‘PQB€Y€Yљ\ЫЬћWЫЫ›WШЫЭ[ќ€[™›ШЪЩYШЫЭ[ќOH‚€™]\›€‘PQS‘TФЧФХUWРQ’TУФ–WУУ“B€™]\›€‘PQS‘TФЧФХUWР“РТСQ‚‚™Y€Ь™X\ЫЫ—ШЫЭ[ќКXЪ\Ъ[ЫњО€]\X›VРШ[™Y]R\™ЭЫ™ЬYQXЪ\Ъ[Ы—JHO€XЭЬЭ‹[ќN‚€ЫЭ[ќ\Ћ€ЫЭ[ќ\–ЬЭ—HHЫЭ[ќ\Љ
B€›Ь€XЪ\Ъ[Ы€[€XЪ\Ъ[ЫњО‚€›Ь€™X\ЫЫ€[€

™XЪ\Ъ[Ы‹њ™X\ЫЫњЛ
™XЪ\Ъ[Ы‹›ШЪЩ\њКN‚€^HЭЉ™X\ЫЫ€Ь€€ЉKњЭљ\

B€Y€^‚€ЫЭ[ќ\–Э^H
ПHB€™]\›€XЭ
ЫЭ[ќ\ЉB‚‚™Y€Ь™Yљ^YЩЭЫ™ЬYWШ›ШЪЩ\њК›ШЪЩ\њО€]\X›VЬЭ—JHO€\VЬЭ‹‹‹—N‚€™]\›€\J€™ЭЫ™ЬYNћШ›ШЪЩ\џH€›Ь€›ШЪЩ\€[€›ШЪЩ\њИY€ЭЉ›ШЪЩ\€Ь€€ЉKњЭљ\

JB‚‚™Y€ЫY]Y]J
HO€XЭЬЭ‹[ћWN‚€™]\›€В€›[Щ[Ћ€РS‘QUWФ‘PQS‘TФЧФХSSPT–WФУХTђСK€њШЫЬHЋ€Ш[™Y]WЬ™XY[™\ЬЧЬЭ[[X\ћWЫ›ЧЬќ[ќ[YWЭЪ\љ[™ЧЫ›ЧЬ[љЪ[™ЧЫ›ЧЬШЫЬљ[™И‹€™Щ\ЧЫ›ЭЪ[\ЬќЬЭ]YЮWЫ[Щ[\ИЋ€ќYK€™Щ\ЧЫ›ЭЩ^XЭ]WЬЭ]YЮWШШ[X›\ИЋ€ќYK€™Щ\ЧЫ›ЭЬ[љЧШШ[™Y]\ИЋ€ќYK€™Щ\ЧЫ›ЭЬШЫЬ™WЩYЩHЋ€ќYK€™Щ\ЧЫ›ЭЬЩ[XЭШШ[™Y]\ИЋ€ќYK€™Щ\ЧЫ›ЭШ[ШШ]WШШ\][Ћ€ќYK€B‚‚™Y€ШШ[™Y]WЪЩ^J[YN€[ћJHO€ЭЋ‚€™]\›€ЭЉ[YHЬ€€ЉKњЭљ\

K›ЭЩ\Љ
Kњ™\XЩJ€‹—ИЉKњ™\XЩJ‹H‹—ИЉB‚‚™Y€Э\J[YN€[ћJHO€\VЬЭ‹‹‹—N‚€Y€[YH\И›Ы™N‚€™]\›€

B€Y€\Ъ[њЭ[ЩJ[YKЭЉN‚€[Y\ИH
[YK
B€[Y€\Ъ[њЭ[ЩJ[YK]\X›JN‚€[Y\ИH\J[YJB€[ЩN‚€[Y\ИH
[YK
B€™]\›€\JЭЉ][JKњЭљ\

H›Ь€][H[€[Y\ИY€ЭЉ][JKњЭљ\

JB‚‚™Y€Эќ]J[YN€[ћJHO€›ЫЫ‚€Y€\Ъ[њЭ[ЩJ[YK›ЫЫ
N‚€™]\›€[YB€Y€[YH[€
›Ы™K€‹“›Ы™HЉN‚€™]\›€[ЩB€Y€\Ъ[њЭ[ЩJ[YK
[ќ›Ш]
JN‚€™]\›€›ЫЫ
[YJB€™]\›€ЭЉ[YJKњЭљ\

K›ЭЩ\Љ
H[€ИЊH‹ќќYH‹ћY\И‹›Ы€‹ћHџB‚‚™Y€ЬШY™WЩXЭ
[YN€[ћJHO€XЭЬЭ‹[ћWN‚€Y€›Э\Ъ[њЭ[ЩJ[YKX\[™КN‚€™]\›€ЯB€™]\›€ЬЭЉЩ^JN€ЬШY™WЪњЫЫ—Э[YJ][JH›Ь€Щ^K][H[€[YKљ][\К
_B‚‚™Y€ЬШY™WЪњЫЫ—Э[YJ[YN€[ћJHO€[ћN‚€Y€\Ъ[њЭ[ЩJ[YKX\[™КN‚€™]\›€ЬЭЉЩ^JN€ЬШY™WЪњЫЫ—Э[YJ][JH›Ь€Щ^K][H[€[YKљ][\К
_B€Y€\Ъ[њЭ[ЩJ[YK
\Э\KЩ]
JN‚€™]\›€ЧЬШY™WЪњЫЫ—Э[YJ][JH›Ь€][H[€[YWB€Y€\Ъ[њЭ[ЩJ[YK
Э‹[ќ›Ш]›ЫЫ
JHЬ€[YH\И›Ы™N‚€™]\›€[YB€™]\›€ЭЉ[YJB‚‚™Y€ЩY\WЬЫЬќY
[Y\О€]\X›VЬЭ—JHO€\VЬЭ‹‹‹—N‚€™]\›€\JЫЬќY
Э[YH›Ь€[YH[€[Y\ИY€[Y_JJB‚‚—ЧШ[ЧИHВ€ђРS‘QUWФ‘PQS‘TФЧФХSSPT–WФРТSPWХ‘T”ТSУ€‹€ђРS‘QUWФ‘PQS‘TФЧФХSSPT–WФУХTђСH‹€ђШ[™Y]T™XY[™\ЬФЭ[[X\ћH‹€”‘PQS‘TФЧФХUWРQ’TУФ–WУУ“H‹€”‘PQS‘TФЧФХUWР“РТСQ‹€”‘PQS‘TФЧФХUWТS•ђSQ‹€”‘PQS‘TФЧФХUWФ‘PQH‹€”‘PQS‘TФЧФХSSPT–WСХУ‘ФђQWТS•ђSQ‹€”‘PQS‘TФЧФХSSPT–WСSTWТS”U‹€”‘PQS‘TФЧФХSSPT–WУPS“Ф“QQСPТTТSУ€‹€”‘PQS‘TФЧФХSSPT–WХS’У“ХУ—СPТTТSУ€‹€њЭ[[X\љ^™WШШ[™Y]WЬ™XY[™\ЬИ‹—B