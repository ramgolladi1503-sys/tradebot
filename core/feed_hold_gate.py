"""Read-only feed hold gate for candidate and ranking flows.

This module consumes canonical feed-health truth and returns read-only evidence.
It does not reconnect feeds, resubscribe tokens, mutate strategy candidates,
write files, call brokers, or create order intent.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from core.candidate_ranking import CandidateRankingReport, RANKING_SCHEMA_VERSION, rank_candidates
from core.directional_balance import DirectionalBalanceReport
from core.feed_health_truth import FeedHealthTruthDecision, SymbolFeedTruth, classify_feed_health_truth
from core.opportunity_scoring import OpportunityScoreRecord, OpportunityScoreReport
from config import feed_runtime_reliability as reliability_cfg

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
    *,
    symbol: str | None = None,
) -> CandidateRankingReport:
    """Return ranking output, or a zero-rank hold report when feed truth blocks it."""

    scoped_feed_health = _scope_certified_symbol_truth(feed_health, symbol) if symbol else None
    hold = classify_feed_hold(scoped_feed_health if scoped_feed_health is not None else feed_health)
    if not hold.hold_active:
        ranking = rank_candidates(scores, directional_balance)
        if scoped_feed_health is not None:
            return replace(
                ranking,
                metadata={
                    **ranking.metadata,
                    "feed_hold_scope": "explicit_symbol",
                    "feed_hold_symbol": str(symbol or "").strip().upper(),
                },
            )
        return ranking

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
            "feed_hold_scope": "global_or_unknown",
            "source_score_count": len(source_scores),
            "source_scorer": source_metadata.get("scorer") if isinstance(source_metadata, dict) else None,
            "feed_hold": hold.to_dict(),
        },
    )


_LOCAL_SYMBOL_REASONS = {
    "option_feed_blocked",
    "option_ticks_stale",
    "option_age_missing",
    "symbol_feed_unknown",
}
_SAFE_RUNTIME_STATES = {"", "RUNNING", "LIVE", "HEALTHY", "OK", "DEGRADED_LOCAL", "VERIFYING_RECOVERY"}
_SAFE_FEED_STATES = {"", "LIVE", "RUNNING", "HEALTHY", "OK", "DEGRADED_LOCAL", "VERIFYING_RECOVERY"}


def _scope_certified_symbol_truth(
    feed_health: FeedHealthTruthDecision | Mapping[str, Any] | None,
    symbol: str | None,
) -> FeedHealthTruthDecision | None:
    """Allow cross-symbol isolation only from an explicit healthy symbol row.

    Any absent/opaque contract, global blocker, persisted aggregate snapshot,
    unknown target, or non-local reason returns None so the caller retains the
    original aggregate decision and fails closed.
    """
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return None
    payload = feed_health.to_payload() if isinstance(feed_health, FeedHealthTruthDecision) else feed_health
    if not isinstance(payload, Mapping):
        return None
    context = payload.get("context")
    if not isinstance(context, Mapping):
        return None
    if context.get("feed_ok_scope") != "symbol_aggregate":
        return None
    if context.get("global_feed_blocked") is not False:
        return None
    if payload.get("websocket_ok") is not True:
        return None
    if context.get("runtime_snapshot_source") is not None:
        return None
    if context.get("runtime_snapshot_feed_fresh") is not None:
        return None
    runtime_state = str(context.get("runtime_state") or "").strip().upper()
    feed_state = str(context.get("feed_state") or "").strip().upper()
    if runtime_state not in _SAFE_RUNTIME_STATES or feed_state not in _SAFE_FEED_STATES:
        return None
    if payload.get("global_feed_ok") not in (True, False):
        return None

    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, (tuple, list)):
        return None
    rows: dict[str, Mapping[str, Any]] = {}
    for raw in raw_symbols:
        if not isinstance(raw, Mapping):
            return None
        name = str(raw.get("symbol") or "").strip().upper()
        if not name or name in rows:
            return None
        rows[name] = raw
    target = rows.get(normalized)
    if target is None or target.get("feed_ok") is not True:
        return None
    if target.get("reason_code") != "ok" or target.get("reasons") not in ((), []):
        return None
    target_context = target.get("context")
    target_context = target_context if isinstance(target_context, Mapping) else {}
    option_age = target.get("option_last_tick_age_sec")
    option_max_age = target_context.get("max_option_tick_age_sec")
    if any(
        type(value) not in (int, float) or not math.isfinite(float(value))
        for value in (option_age, option_max_age)
    ):
        return None
    if float(option_age) < 0.0 or float(option_max_age) <= 0.0 or float(option_age) > float(option_max_age):
        return None
    if target.get("option_feed_block_reason") not in (None, "", "OK", "NONE", "HEALTHY", "FRESH"):
        return None
    underlying = target_context.get("underlying_feed_identity")
    session_identity = target_context.get("feed_session_identity")
    if not isinstance(underlying, Mapping) or not isinstance(session_identity, Mapping):
        return None
    token = underlying.get("instrument_token")
    if type(token) is not int or token <= 0:
        return None
    if type(underlying.get("generated_epoch")) not in (int, float) or type(underlying.get("max_age_sec")) not in (int, float):
        return None
    if type(underlying.get("age_sec")) not in (int, float) or type(underlying.get("receipt_epoch")) not in (int, float):
        return None
    if any(type(underlying.get(key)) is not int or underlying.get(key) < 0 for key in ("feed_epoch", "reconnect_generation")):
        return None
    if underlying.get("symbol") != normalized or underlying.get("status") != "HEALTHY":
        return None
    if underlying.get("identity_domain") not in {"INDEX_SPOT", "STOCK_SPOT"}:
        return None
    if underlying.get("active_subscription") is not True or underlying.get("subscription_succeeded") is not True:
        return None
    session_id = str(session_identity.get("feed_session_id") or "")
    if session_identity.get("provider") != "kite" or session_identity.get("token_domain") != "kite_instrument_token":
        return None
    if not session_id or underlying.get("feed_session_id") != session_id:
        return None
    for key in ("feed_epoch", "reconnect_generation"):
        expected = session_identity.get(key)
        observed = underlying.get(key)
        if type(expected) is not int or expected < 0 or type(observed) is not int or observed != expected:
            return None
    receipt = underlying.get("receipt_epoch")
    generated = underlying.get("generated_epoch")
    age = underlying.get("age_sec")
    max_age = underlying.get("max_age_sec")
    if any(type(value) not in (int, float) or not math.isfinite(float(value)) for value in (receipt, generated, age, max_age)):
        return None
    if float(age) < 0.0 or float(max_age) <= 0.0 or float(age) > float(max_age):
        return None
    if float(generated) < float(receipt) or abs((float(generated) - float(receipt)) - float(age)) > 0.01:
        return None
    observation_epoch = session_identity.get("observed_epoch")
    if type(observation_epoch) not in (int, float) or not math.isfinite(float(observation_epoch)):
        return None
    if abs(float(observation_epoch) - float(generated)) > 0.01:
        return None
    now_epoch = time.time()
    max_snapshot_age = getattr(reliability_cfg, "FEED_TRUTH_SNAPSHOT_MAX_AGE_SEC", 3.0)
    if type(max_snapshot_age) not in (int, float) or not math.isfinite(float(max_snapshot_age)) or float(max_snapshot_age) <= 0.0:
        return None
    if float(observation_epoch) > now_epoch or now_epoch - float(observation_epoch) > float(max_snapshot_age):
        return None

    reasons = payload.get("reasons")
    if not isinstance(reasons, (tuple, list)):
        return None
    for reason in reasons:
        text = str(reason or "")
        prefix, separator, suffix = text.partition(":")
        if not separator or prefix.strip().upper() == normalized:
            return None
        if prefix.strip().upper() not in rows or suffix.strip().lower() not in _LOCAL_SYMBOL_REASONS:
            return None
        if rows[prefix.strip().upper()].get("feed_ok") is not False:
            return None

    domains = payload.get("domains")
    if not isinstance(domains, Mapping):
        return None
    for raw_domain in domains.values():
        if not isinstance(raw_domain, Mapping) or str(raw_domain.get("state") or "").upper() == "UNHEALTHY":
            return None

    target_truth = SymbolFeedTruth(
        symbol=normalized,
        feed_ok=True,
        reason_code="ok",
        reasons=(),
        option_feed_block_reason=target.get("option_feed_block_reason"),
        option_last_tick_age_sec=target.get("option_last_tick_age_sec"),
        context=dict(target.get("context") or {}),
    )
    scoped_context = dict(context)
    scoped_context.update({"ranking_scope": "explicit_symbol", "ranking_symbol": normalized})
    return FeedHealthTruthDecision(
        feed_ok=True,
        reason_code="ok",
        reasons=(),
        global_feed_ok=payload.get("global_feed_ok"),
        websocket_ok=True,
        symbols=(target_truth,),
        context=scoped_context,
        domains={str(key): dict(value) for key, value in domains.items()},
        overall_state="HEALTHY",
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
