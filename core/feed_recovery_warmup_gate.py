"""Read-only feed recovery warmup gate for ranking flows.

This module consumes canonical feed-health truth plus explicit recovery context.
It does not reconnect feeds, resubscribe tokens, mutate candidates, write files,
call brokers, or create order intent.
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

FEED_RECOVERY_WARMUP_SCHEMA_VERSION = 1
FEED_RECOVERY_WARMUP_BLOCKER = "feed_recovery_warmup"
FEED_RECOVERY_WARMUP_REASON = "feed_recovery_warmup_required"
_ORDER_ACTION_KEY = "is_" + "order_action"


@dataclass(frozen=True)
class FeedRecoveryWarmupDecision:
    """Decision explaining whether feed recovery must warm up before ranking."""

    schema_version: int
    read_only: bool
    append: bool
    warmup_active: bool
    warmup_required: bool
    feed_recovered: bool
    warmup_complete: bool
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
            "warmup_active": self.warmup_active,
            "warmup_required": self.warmup_required,
            "feed_recovered": self.feed_recovered,
            "warmup_complete": self.warmup_complete,
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


def classify_feed_recovery_warmup(
    feed_health: FeedHealthTruthDecision | Mapping[str, Any] | None,
    *,
    previous_feed_ok: bool | None = None,
    recovered_at_epoch: float | int | None = None,
    now_epoch: float | int | None = None,
    healthy_sample_count: int = 0,
    min_warmup_sec: float = 5.0,
    min_healthy_samples: int = 2,
) -> FeedRecoveryWarmupDecision:
    """Classify whether a recovered feed still needs warmup before ranking.

    Warmup is required only when the caller supplies explicit recovery context:
    previous feed health was unhealthy and current canonical feed truth is healthy.
    Missing or insufficient recovery evidence fails closed while warmup is required.
    """

    decision = _coerce_feed_health(feed_health)
    current_feed_ok = bool(decision.feed_ok)
    recovered = previous_feed_ok is False and current_feed_ok
    min_seconds = _non_negative_float(min_warmup_sec)
    required_samples = _non_negative_int(min_healthy_samples)
    sample_count = _non_negative_int(healthy_sample_count)
    now = float(time.time() if now_epoch is None else now_epoch)
    recovered_at = _optional_float(recovered_at_epoch)
    elapsed_sec = None if recovered_at is None else max(0.0, now - recovered_at)

    blockers: list[str] = []
    warnings: list[str] = []
    warmup_required = False
    warmup_complete = True
    reason = "feed_recovery_warmup_clear"

    if not current_feed_ok:
        warmup_required = True
        warmup_complete = False
        reason = "canonical_feed_unhealthy"
        _append_unique(blockers, FEED_RECOVERY_WARMUP_BLOCKER)
        for feed_reason in decision.reasons:
            _append_unique(blockers, str(feed_reason))
    elif recovered:
        warmup_required = True
        warmup_complete = True
        if recovered_at is None:
            warmup_complete = False
            reason = "feed_recovered_at_missing"
            _append_unique(blockers, FEED_RECOVERY_WARMUP_BLOCKER)
            _append_unique(blockers, "recovered_at_missing")
        elif elapsed_sec < min_seconds:
            warmup_complete = False
            reason = FEED_RECOVERY_WARMUP_REASON
            _append_unique(blockers, FEED_RECOVERY_WARMUP_BLOCKER)
            _append_unique(blockers, "warmup_elapsed_sec_below_minimum")
        if sample_count < required_samples:
            warmup_complete = False
            reason = FEED_RECOVERY_WARMUP_REASON if reason == "feed_recovery_warmup_clear" else reason
            _append_unique(blockers, FEED_RECOVERY_WARMUP_BLOCKER)
            _append_unique(blockers, "healthy_sample_count_below_minimum")
        if warmup_complete:
            reason = "feed_recovery_warmup_complete"
    elif previous_feed_ok is None:
        _append_unique(warnings, "previous_feed_state_unknown_no_recovery_warmup_applied")

    warmup_active = warmup_required and not warmup_complete
    return FeedRecoveryWarmupDecision(
        schema_version=FEED_RECOVERY_WARMUP_SCHEMA_VERSION,
        read_only=True,
        append=False,
        warmup_active=warmup_active,
        warmup_required=warmup_required,
        feed_recovered=recovered,
        warmup_complete=warmup_complete,
        reason=reason,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        feed_health_truth=decision.to_payload(),
        metadata={
            "gate": "feed_recovery_warmup_gate_v1",
            "scope": "read_only_no_reconnect_no_resubscribe_no_candidate_mutation",
            "previous_feed_ok": previous_feed_ok,
            "current_feed_ok": current_feed_ok,
            "recovered_at_epoch": recovered_at,
            "now_epoch": now,
            "elapsed_sec": elapsed_sec,
            "min_warmup_sec": min_seconds,
            "healthy_sample_count": sample_count,
            "min_healthy_samples": required_samples,
        },
    )


def apply_feed_recovery_warmup_to_ranking(
    scores: OpportunityScoreReport | tuple[OpportunityScoreRecord, ...] | list[OpportunityScoreRecord],
    feed_health: FeedHealthTruthDecision | Mapping[str, Any] | None,
    directional_balance: DirectionalBalanceReport | None = None,
    *,
    previous_feed_ok: bool | None = None,
    recovered_at_epoch: float | int | None = None,
    now_epoch: float | int | None = None,
    healthy_sample_count: int = 0,
    min_warmup_sec: float = 5.0,
    min_healthy_samples: int = 2,
) -> CandidateRankingReport:
    """Return ranking output, or zero-rank output while recovery warmup is active."""

    warmup = classify_feed_recovery_warmup(
        feed_health,
        previous_feed_ok=previous_feed_ok,
        recovered_at_epoch=recovered_at_epoch,
        now_epoch=now_epoch,
        healthy_sample_count=healthy_sample_count,
        min_warmup_sec=min_warmup_sec,
        min_healthy_samples=min_healthy_samples,
    )
    if not warmup.warmup_active:
        return rank_candidates(scores, directional_balance)

    source_scores = _coerce_score_records(scores)
    source_metadata = getattr(scores, "metadata", {}) if isinstance(scores, OpportunityScoreReport) else {}
    return CandidateRankingReport(
        schema_version=RANKING_SCHEMA_VERSION,
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
        blockers=warmup.blockers,
        warnings=warmup.warnings,
        safety_flags=(FEED_RECOVERY_WARMUP_BLOCKER,),
        directional_imbalance_flags=(),
        metadata={
            "ranker": "candidate_ranking_v1",
            "gate": "feed_recovery_warmup_gate_v1",
            "feed_recovery_warmup_active": True,
            "source_score_count": len(source_scores),
            "source_scorer": source_metadata.get("scorer") if isinstance(source_metadata, dict) else None,
            "feed_recovery_warmup": warmup.to_dict(),
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
            raise TypeError("feed_recovery_warmup_expected_opportunity_score_record")
    return records


def _optional_float(value: float | int | None) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _non_negative_float(value: float | int) -> float:
    try:
        return max(0.0, float(value))
    except Exception:
        return 0.0


def _non_negative_int(value: int) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return 0


def _append_unique(values: list[str], value: str | None) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


__all__ = [
    "FEED_RECOVERY_WARMUP_BLOCKER",
    "FEED_RECOVERY_WARMUP_REASON",
    "FEED_RECOVERY_WARMUP_SCHEMA_VERSION",
    "FeedRecoveryWarmupDecision",
    "apply_feed_recovery_warmup_to_ranking",
    "classify_feed_recovery_warmup",
]
