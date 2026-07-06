"""Read-only feed hold gate for candidate and ranking flows.

This module consumes canonical feed-health truth and returns read-only evidence.
It does not reconnect feeds, resubscribe tokens, mutate strategy candidates,
write files, call brokers, or create order intent.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.candidate_ranking import CandidateRankingReport, RANKING_SCHEMA_VERSION, rank_candidates
from core.directional_balance import DirectionalBalanceReport
from core.feed_health_truth import FeedHealthTruthDecision, classify_feed_health_truth
from core.opportunity_scoring import OpportunityScoreRecord, OpportunityScoreReport

FEED_HOLD_SCHEMA_VERSION = 1
FEED_HOLD_BLOCKER = "feed_health_hold"
FEED_HOLD_REASON = "canonical_feed_unhealthy"
_ORDER_ACTION_KEY = "is_" + "order_action"


@dataclass(frozen=True)
class FeedHoldDecision:
    """Decision explaining whether candidates must be held due to feed health."""

    schema_version: int
    read_only: bool
    append: bool
    hold_active: bool
    reason: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    feed_health_truth: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "hold_active": self.hold_active,
            "reason": self.reason,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "feed_health_truth": dict(self.feed_health_truth),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def classify_feed_hold(feed_health: FeedHealthTruthDecision | Mapping[str, Any] | None) -> FeedHoldDecision:
    """Classify whether canonical feed truth requires a candidate/ranking hold."""

    decision = _coerce_feed_health(feed_health)
    hold_active = not bool(decision.feed_ok)
    reasons = tuple(str(reason) for reason in decision.reasons if str(reason or "").strip())
    blockers = (FEED_HOLD_BLOCKER, *reasons) if hold_active else ()
    return FeedHoldDecision(
        schema_version=FEED_HOLD_SCHEMA_VERSION,
        read_only=True,
        append=False,
        hold_active=hold_active,
        reason=FEED_HOLD_REASON if hold_active else "feed_health_clear",
        blockers=blockers,
        warnings=(),
        feed_health_truth=decision.to_payload(),
        metadata={
            "gate": "feed_hold_gate_v1",
            "scope": "read_only_no_candidate_mutation_no_ranking_when_feed_unhealthy",
        },
    )


def apply_feed_hold_to_ranking(
    scores: OpportunityScoreReport | tuple[OpportunityScoreRecord, ...] | list[OpportunityScoreRecord],
    feed_health: FeedHealthTruthDecision | Mapping[str, Any] | None,
    directional_balance: DirectionalBalanceReport | None = None,
) -> CandidateRankingReport:
    """Return ranking output, or a zero-rank hold report when feed truth blocks it."""

    hold = classify_feed_hold(feed_health)
    if not hold.hold_active:
        return rank_candidates(scores, directional_balance)

    source_scores = _coerce_score_records(scores)
    source_metadata = getattr(scores, "metadata", {}) if isinstance(scores, OpportunityScoreReport) else {}
    import uuid
    import time
    return CandidateRankingReport(
        schema_version=RANKING_SCHEMA_VERSION,
        ranked_report_id=str(uuid.uuid4()),
        generated_epoch=time.time(),
        read_only=True,
        is_order_action=False,
        append=False,
        rank_count=0,
        executable_count=0,
        near_executable_count=0,
        advisory_count=0,
        suppressed_count=0,
        no_trade_count=0,
        ranks=(),
        blockers=hold.blockers,
        warnings=hold.warnings,
        safety_flags=(FEED_HOLD_BLOCKER,),
        directional_imbalance_flags=(),
        metadata={
            "ranker": "candidate_ranking_v1",
            "gate": "feed_hold_gate_v1",
            "feed_hold_active": True,
            "source_score_count": len(source_scores),
            "source_scorer": source_metadata.get("scorer") if isinstance(source_metadata, dict) else None,
            "feed_hold": hold.to_dict(),
        },
    )


def _coerce_feed_health(feed_health: FeedHealthTruthDecision | Mapping[str, Any] | None) -> FeedHealthTruthDecision:
    if isinstance(feed_health, FeedHealthTruthDecision):
        return feed_health
    if isinstance(feed_health, Mapping):
        return classify_feed_health_truth(dict(feed_health))
    return classify_feed_health_truth(None)


def _coerce_score_records(
    scores: OpportunityScoreReport | tuple[OpportunityScoreRecord, ...] | list[OpportunityScoreRecord],
) -> tuple[OpportunityScoreRecord, ...]:
    if isinstance(scores, OpportunityScoreReport):
        return tuple(scores.scores)
    records = tuple(scores or ())
    for record in records:
        if not isinstance(record, OpportunityScoreRecord):
            raise TypeError("feed_hold_expected_opportunity_score_record")
    return records


__all__ = [
    "FEED_HOLD_BLOCKER",
    "FEED_HOLD_REASON",
    "FEED_HOLD_SCHEMA_VERSION",
    "FeedHoldDecision",
    "apply_feed_hold_to_ranking",
    "classify_feed_hold",
]
