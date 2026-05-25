"""Deterministic Opportunity Score V1 contract for roadmap PR73."""

from __future__ import annotations

import json
import time
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
from core.candidate_readiness_summary import (
    READINESS_STATE_READY,
    CandidateReadinessSummary,
)

OPPORTUNITY_SCORE_SCHEMA_VERSION = 1
OPPORTUNITY_SCORE_SOURCE = "opportunity_score_v1"

OPPORTUNITY_SCORE_EMPTY_INPUT = "opportunity_score_empty_input"
OPPORTUNITY_SCORE_READINESS_INVALID = "opportunity_score_readiness_invalid"
OPPORTUNITY_SCORE_MALFORMED_DECISION = "opportunity_score_malformed_decision"
OPPORTUNITY_SCORE_UNKNOWN_DECISION = "opportunity_score_unknown_decision"
OPPORTUNITY_SCORE_COMPRESSION_WARNING = "opportunity_score_compression_warning"
OPPORTUNITY_SCORE_ADVISORY_CAP = "opportunity_score_advisory_cap"
OPPORTUNITY_SCORE_BLOCKED_ZERO = "opportunity_score_blocked_zero"

SCORE_COMPONENT_EDGE = "edge"
SCORE_COMPONENT_MOMENTUM = "momentum"
SCORE_COMPONENT_LIQUIDITY = "liquidity"
SCORE_COMPONENT_SPREAD = "spread"
SCORE_COMPONENT_VOLATILITY = "volatility"
SCORE_COMPONENT_REGIME_FIT = "regime_fit"
SCORE_COMPONENT_DATA_QUALITY = "data_quality"
SCORE_COMPONENT_TIME_DECAY_RISK = "time_decay_risk"

SCORE_COMPONENT_KEYS = (
    SCORE_COMPONENT_EDGE,
    SCORE_COMPONENT_MOMENTUM,
    SCORE_COMPONENT_LIQUIDITY,
    SCORE_COMPONENT_SPREAD,
    SCORE_COMPONENT_VOLATILITY,
    SCORE_COMPONENT_REGIME_FIT,
    SCORE_COMPONENT_DATA_QUALITY,
    SCORE_COMPONENT_TIME_DECAY_RISK,
)

_COMPONENT_WEIGHTS = {
    SCORE_COMPONENT_EDGE: 0.20,
    SCORE_COMPONENT_MOMENTUM: 0.15,
    SCORE_COMPONENT_LIQUIDITY: 0.15,
    SCORE_COMPONENT_SPREAD: 0.10,
    SCORE_COMPONENT_VOLATILITY: 0.10,
    SCORE_COMPONENT_REGIME_FIT: 0.15,
    SCORE_COMPONENT_DATA_QUALITY: 0.10,
    SCORE_COMPONENT_TIME_DECAY_RISK: 0.05,
}
_READY_DEFAULTS = {
    SCORE_COMPONENT_EDGE: 0.60,
    SCORE_COMPONENT_MOMENTUM: 0.55,
    SCORE_COMPONENT_LIQUIDITY: 0.65,
    SCORE_COMPONENT_SPREAD: 0.60,
    SCORE_COMPONENT_VOLATILITY: 0.55,
    SCORE_COMPONENT_REGIME_FIT: 0.65,
    SCORE_COMPONENT_DATA_QUALITY: 0.70,
    SCORE_COMPONENT_TIME_DECAY_RISK: 0.55,
}
_ADVISORY_DEFAULTS = {
    SCORE_COMPONENT_EDGE: 0.35,
    SCORE_COMPONENT_MOMENTUM: 0.35,
    SCORE_COMPONENT_LIQUIDITY: 0.40,
    SCORE_COMPONENT_SPREAD: 0.35,
    SCORE_COMPONENT_VOLATILITY: 0.35,
    SCORE_COMPONENT_REGIME_FIT: 0.40,
    SCORE_COMPONENT_DATA_QUALITY: 0.30,
    SCORE_COMPONENT_TIME_DECAY_RISK: 0.30,
}
_COMPRESSION_THRESHOLD = 5.0
_ADVISORY_SCORE_CAP = 40.0
_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class OpportunityScore:
    canonical_candidate_id: str
    strategy_id: str
    decision: str
    score: float
    component_scores: dict[str, float]
    weighted_contributions: dict[str, float]
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = OPPORTUNITY_SCORE_SOURCE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def valid(self) -> bool:
        return not self.blockers

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "canonical_candidate_id": self.canonical_candidate_id,
            "strategy_id": self.strategy_id,
            "decision": self.decision,
            "score": self.score,
            "component_scores": dict(sorted(self.component_scores.items())),
            "weighted_contributions": dict(
                sorted(self.weighted_contributions.items())
            ),
            "valid": self.valid,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


@dataclass(frozen=True)
class OpportunityScoreReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    scores: tuple[OpportunityScore, ...]
    blocked_scores: tuple[OpportunityScore, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    score_compressed: bool
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
    def scored_candidate_ids(self) -> tuple[str, ...]:
        return tuple(score.canonical_candidate_id for score in self.scores)

    def get(self, canonical_candidate_id: str) -> OpportunityScore | None:
        wanted = _candidate_key(canonical_candidate_id)
        for score in (*self.scores, *self.blocked_scores):
            if score.canonical_candidate_id == wanted:
                return score
        return None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "score_count": len(self.scores),
            "blocked_score_count": len(self.blocked_scores),
            "scored_candidate_ids": list(self.scored_candidate_ids),
            "score_compressed": self.score_compressed,
            "scores": [score.to_payload() for score in self.scores],
            "blocked_scores": [score.to_payload() for score in self.blocked_scores],
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


def score_opportunities(
    decisions: CandidateHardDowngradeReport
    | Iterable[CandidateHardDowngradeDecision | Mapping[str, Any]],
    *,
    readiness_summary: CandidateReadinessSummary | Mapping[str, Any] | None = None,
    component_overrides: Mapping[str, Mapping[str, float]] | None = None,
    source: str = OPPORTUNITY_SCORE_SOURCE,
) -> OpportunityScoreReport:
    """Score candidate readiness evidence without ranking or selection."""

    active, blocked, downgrade_blockers = _resolve_decisions(decisions)
    report_blockers = list(_input_blockers(active, blocked, downgrade_blockers))
    if readiness_summary is not None and not _summary_valid(readiness_summary):
        report_blockers.append(OPPORTUNITY_SCORE_READINESS_INVALID)

    blockers = _dedupe_sorted(report_blockers)
    overrides = component_overrides or {}
    all_decisions = tuple(_coerce_decision(decision) for decision in (*active, *blocked))

    scored: list[OpportunityScore] = []
    blocked_scores: list[OpportunityScore] = []
    for decision in all_decisions:
        result = _score_decision(
            decision,
            forced_blockers=blockers,
            component_overrides=overrides.get(decision.canonical_candidate_id, {}),
        )
        if result.valid and result.decision != DOWNGRADE_DECISION_BLOCKED:
            scored.append(result)
        else:
            blocked_scores.append(result)

    score_compressed = _score_compressed(scored)
    warnings = _dedupe_sorted(
        (
            *((OPPORTUNITY_SCORE_COMPRESSION_WARNING,) if score_compressed else ()),
            *(warning for score in (*scored, *blocked_scores) for warning in score.warnings),
        )
    )
    return OpportunityScoreReport(
        schema_version=OPPORTUNITY_SCORE_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        scores=tuple(sorted(scored, key=lambda item: item.canonical_candidate_id)),
        blocked_scores=tuple(
            sorted(blocked_scores, key=lambda item: item.canonical_candidate_id)
        ),
        blockers=blockers,
        warnings=warnings,
        score_compressed=score_compressed,
        metadata=_metadata(),
    )


def _resolve_decisions(
    decisions: CandidateHardDowngradeReport
    | Iterable[CandidateHardDowngradeDecision | Mapping[str, Any]],
) -> tuple[
    tuple[CandidateHardDowngradeDecision | Mapping[str, Any], ...],
    tuple[CandidateHardDowngradeDecision | Mapping[str, Any], ...],
    tuple[str, ...],
]:
    if isinstance(decisions, CandidateHardDowngradeReport):
        return (
            tuple(decisions.decisions),
            tuple(decisions.blocked_decisions),
            tuple(decisions.blockers),
        )
    if decisions is None:
        return (), (), ()
    return tuple(decisions), (), ()


def _input_blockers(
    active: tuple[Any, ...],
    blocked: tuple[Any, ...],
    downgrade_blockers: tuple[str, ...],
) -> tuple[str, ...]:
    if not active and not blocked:
        return (OPPORTUNITY_SCORE_EMPTY_INPUT,)
    return tuple(f"downgrade:{blocker}" for blocker in downgrade_blockers if blocker)


def _score_decision(
    decision: CandidateHardDowngradeDecision,
    *,
    forced_blockers: tuple[str, ...],
    component_overrides: Mapping[str, float],
) -> OpportunityScore:
    decision_blockers = _dedupe_sorted(
        (*forced_blockers, *_decision_blockers(decision))
    )
    component_scores = _component_scores(decision, component_overrides)
    contributions = {
        key: round(component_scores[key] * _COMPONENT_WEIGHTS[key] * 100.0, 4)
        for key in SCORE_COMPONENT_KEYS
    }
    raw_score = round(sum(contributions.values()), 4)
    warnings = list(decision.warnings)

    if decision.decision == DOWNGRADE_DECISION_BLOCKED or decision_blockers:
        score = 0.0
        decision_blockers = _dedupe_sorted(
            (*decision_blockers, OPPORTUNITY_SCORE_BLOCKED_ZERO)
        )
    elif decision.decision == DOWNGRADE_DECISION_ADVISORY_ONLY:
        score = min(raw_score, _ADVISORY_SCORE_CAP)
        warnings.append(OPPORTUNITY_SCORE_ADVISORY_CAP)
    else:
        score = raw_score

    return OpportunityScore(
        canonical_candidate_id=_candidate_key(decision.canonical_candidate_id),
        strategy_id=_candidate_key(decision.strategy_id),
        decision=decision.decision,
        score=round(score, 4),
        component_scores=component_scores,
        weighted_contributions=contributions,
        blockers=decision_blockers,
        warnings=_dedupe_sorted(warnings),
        metadata={
            "score_formula": "sum(component_score * component_weight) * 100",
            "component_weights": dict(_COMPONENT_WEIGHTS),
            "source_decision_source": decision.source,
            "source_decision_read_only": decision.read_only,
            "source_decision_append": decision.append,
            "source_decision_reasons": list(decision.reasons),
        },
    )


def _coerce_decision(
    decision: CandidateHardDowngradeDecision | Mapping[str, Any],
) -> CandidateHardDowngradeDecision:
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
            reasons=(OPPORTUNITY_SCORE_MALFORMED_DECISION,),
            blockers=(OPPORTUNITY_SCORE_MALFORMED_DECISION,),
            metadata={"coercion_error": type(decision).__name__},
        )
    return CandidateHardDowngradeDecision(
        canonical_candidate_id=_candidate_key(decision.get("canonical_candidate_id")),
        strategy_id=_candidate_key(decision.get("strategy_id")),
        decision=str(decision.get("decision") or "").strip().upper(),
        hard_downgraded=_truthy(decision.get("hard_downgraded")),
        candidate_ready=_truthy(decision.get("candidate_ready")),
        advisory_only=_truthy(decision.get("advisory_only")),
        blocked=_truthy(decision.get("blocked")),
        reasons=_tuple(decision.get("reasons") or ()),
        blockers=_tuple(decision.get("blockers") or ()),
        warnings=_tuple(decision.get("warnings") or ()),
        labels=_tuple(decision.get("labels") or ()),
        metadata=_safe_dict(decision.get("metadata")),
    )


def _decision_blockers(decision: CandidateHardDowngradeDecision) -> tuple[str, ...]:
    blockers: list[str] = []
    if not decision.canonical_candidate_id or not decision.strategy_id:
        blockers.append(OPPORTUNITY_SCORE_MALFORMED_DECISION)
    if decision.decision not in {
        DOWNGRADE_DECISION_CANDIDATE_READY,
        DOWNGRADE_DECISION_ADVISORY_ONLY,
        DOWNGRADE_DECISION_BLOCKED,
    }:
        blockers.append(OPPORTUNITY_SCORE_UNKNOWN_DECISION)
    blockers.extend(decision.blockers)
    return _dedupe_sorted(blockers)


def _component_scores(
    decision: CandidateHardDowngradeDecision,
    overrides: Mapping[str, float],
) -> dict[str, float]:
    if decision.decision == DOWNGRADE_DECISION_CANDIDATE_READY:
        defaults = _READY_DEFAULTS
    elif decision.decision == DOWNGRADE_DECISION_ADVISORY_ONLY:
        defaults = _ADVISORY_DEFAULTS
    else:
        defaults = {key: 0.0 for key in SCORE_COMPONENT_KEYS}
    return {
        key: _bounded_score(overrides.get(key, defaults[key]))
        for key in SCORE_COMPONENT_KEYS
    }


def _score_compressed(scores: Iterable[OpportunityScore]) -> bool:
    values = [score.score for score in scores if score.valid]
    if len(values) < 2:
        return False
    return max(values) - min(values) <= _COMPRESSION_THRESHOLD


def _summary_valid(summary: CandidateReadinessSummary | Mapping[str, Any]) -> bool:
    if isinstance(summary, CandidateReadinessSummary):
        return summary.valid and summary.readiness_state == READINESS_STATE_READY
    if not isinstance(summary, Mapping):
        return False
    return bool(summary.get("valid")) and summary.get("readiness_state") == READINESS_STATE_READY


def _metadata() -> dict[str, Any]:
    return {
        "model": OPPORTUNITY_SCORE_SOURCE,
        "roadmap_item": "PR73",
        "roadmap_title": "Opportunity Score V1",
        "score_components": list(SCORE_COMPONENT_KEYS),
        "does_not_rank_candidates": True,
        "does_not_select_candidates": True,
        "does_not_wire_runtime": True,
        "does_not_call_broker": True,
        "does_not_allocate_capital": True,
    }


def _bounded_score(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return round(min(1.0, max(0.0, numeric)), 4)


def _candidate_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, Iterable):
        values = tuple(value)
    else:
        values = (value,)
    return tuple(str(item).strip() for item in values if str(item).strip())


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _safe_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _safe_json_value(item) for key, item in value.items()}


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _dedupe_sorted(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


__all__ = [
    "OPPORTUNITY_SCORE_SCHEMA_VERSION",
    "OPPORTUNITY_SCORE_SOURCE",
    "OPPORTUNITY_SCORE_EMPTY_INPUT",
    "OPPORTUNITY_SCORE_READINESS_INVALID",
    "OPPORTUNITY_SCORE_MALFORMED_DECISION",
    "OPPORTUNITY_SCORE_UNKNOWN_DECISION",
    "OPPORTUNITY_SCORE_COMPRESSION_WARNING",
    "SCORE_COMPONENT_KEYS",
    "OpportunityScore",
    "OpportunityScoreReport",
    "score_opportunities",
]
