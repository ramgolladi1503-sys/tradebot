"""Canonical read-only NoTradeOracle for EDGE-80.

The oracle explains why the bot should not trade from existing evidence.
It does not submit orders, create order intent, call external execution APIs,
append runtime files, reconnect feeds, resubscribe tokens, rank candidates,
score edge, or change dashboard behavior.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from core.candidate_ranking import CandidateRankingReport
from core.feed_health_truth import FeedHealthTruthDecision, classify_feed_health_truth
from core.feed_hold_gate import FeedHoldDecision, classify_feed_hold
from core.live_indicator_readiness import LiveIndicatorReadinessReport
from core.market_close_feed_state import FEED_STATE_HEALTHY, MarketCloseFeedStateDecision
from core.opportunity_scoring import OpportunityScoreReport

NO_TRADE_ORACLE_SCHEMA_VERSION = 1
NO_TRADE_ORACLE_SOURCE = "no_trade_oracle_v1"

NO_TRADE_REQUIRED = "NO_TRADE_REQUIRED"
TRADE_ALLOWED_BY_SUPPLIED_EVIDENCE = "TRADE_ALLOWED_BY_SUPPLIED_EVIDENCE"

CATEGORY_EVIDENCE = "evidence"
CATEGORY_FEED = "feed"
CATEGORY_MARKET = "market"
CATEGORY_INDICATOR = "indicator_readiness"
CATEGORY_CANDIDATE = "candidate_quality"
CATEGORY_EXECUTABLE = "executable_truth"

MISSING_EVIDENCE_REASON = "missing_no_trade_evidence"
FEED_HEALTH_BLOCKED_REASON = "feed_health_blocked"
FEED_HOLD_ACTIVE_REASON = "feed_hold_active"
MARKET_FEED_STATE_BLOCKED_REASON = "market_close_feed_state_blocked"
INDICATOR_READINESS_BLOCKED_REASON = "indicator_readiness_blocked"
NO_SCORED_CANDIDATES_REASON = "no_scored_candidates"
NO_SCORE_ELIGIBLE_CANDIDATES_REASON = "no_score_eligible_candidates"
NO_RANKED_CANDIDATES_REASON = "no_ranked_candidates"
NO_EXECUTABLE_RANKS_REASON = "no_executable_ranked_candidates"
EXECUTABLE_TRUTH_BLOCKED_REASON = "executable_truth_blocked"

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class NoTradeReason:
    """One deterministic reason explaining why trading should be blocked."""

    category: str
    reason_code: str
    severity: int
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "reason_code": self.reason_code,
            "severity": self.severity,
            "message": self.message,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class NoTradeOracleReport:
    """Read-only canonical explanation report for no-trade decisions."""

    schema_version: int
    read_only: bool
    append: bool
    source: str
    status: str
    no_trade_required: bool
    primary_reason: str
    reasons: tuple[NoTradeReason, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence_sources: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

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
            "status": self.status,
            "no_trade_required": self.no_trade_required,
            "primary_reason": self.primary_reason,
            "reason_count": len(self.reasons),
            "reasons": [reason.to_dict() for reason in self.reasons],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "evidence_sources": list(self.evidence_sources),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_no_trade_oracle_report(
    *,
    feed_health: FeedHealthTruthDecision | Mapping[str, Any] | None = None,
    feed_hold: FeedHoldDecision | Mapping[str, Any] | None = None,
    market_close_feed_state: MarketCloseFeedStateDecision | Mapping[str, Any] | None = None,
    indicator_readiness: LiveIndicatorReadinessReport | Mapping[str, Any] | None = None,
    scoring: OpportunityScoreReport | Mapping[str, Any] | None = None,
    ranking: CandidateRankingReport | Mapping[str, Any] | None = None,
    executable_truths: Iterable[Mapping[str, Any] | Any] | None = None,
    candidate_count: int | None = None,
    now_epoch: float | None = None,
    source: str = NO_TRADE_ORACLE_SOURCE,
) -> NoTradeOracleReport:
    """Build canonical no-trade evidence from already computed read-only reports."""

    generated_epoch = float(time.time() if now_epoch is None else now_epoch)
    reasons: list[NoTradeReason] = []
    warnings: list[str] = []
    evidence_sources: list[str] = []

    feed_payload = _feed_health_payload(feed_health)
    if feed_payload is not None:
        evidence_sources.append("feed_health_truth")
        if not bool(feed_payload.get("feed_ok")):
            reasons.append(
                _reason(
                    CATEGORY_FEED,
                    FEED_HEALTH_BLOCKED_REASON,
                    90,
                    "Canonical feed health is not OK.",
                    {
                        "reason_code": feed_payload.get("reason_code"),
                        "reasons": list(_list(feed_payload.get("reasons"))),
                        "websocket_ok": feed_payload.get("websocket_ok"),
                        "global_feed_ok": feed_payload.get("global_feed_ok"),
                    },
                )
            )

    feed_hold_payload = _feed_hold_payload(feed_hold, feed_health)
    if feed_hold_payload is not None:
        evidence_sources.append("feed_hold_gate")
        if bool(feed_hold_payload.get("hold_active")):
            reasons.append(
                _reason(
                    CATEGORY_FEED,
                    FEED_HOLD_ACTIVE_REASON,
                    88,
                    "Feed hold gate is active; candidates must not be promoted.",
                    {
                        "reason": feed_hold_payload.get("reason"),
                        "blockers": list(_list(feed_hold_payload.get("blockers"))),
                    },
                )
            )

    market_payload = _payload(market_close_feed_state)
    if market_payload is not None:
        evidence_sources.append("market_close_feed_state")
        if not bool(market_payload.get("feed_ok")) or market_payload.get("state") != FEED_STATE_HEALTHY:
            reasons.append(
                _reason(
                    CATEGORY_MARKET,
                    MARKET_FEED_STATE_BLOCKED_REASON,
                    _market_severity(str(market_payload.get("state") or "")),
                    "Market/feed close-state evidence blocks trading.",
                    {
                        "state": market_payload.get("state"),
                        "decision_gate_reason": market_payload.get("decision_gate_reason"),
                        "ws_connected": market_payload.get("ws_connected"),
                        "websocket_ok": market_payload.get("websocket_ok"),
                        "ltp_age_sec": market_payload.get("ltp_age_sec"),
                        "option_feed_age_sec": market_payload.get("option_feed_age_sec"),
                        "cycle_latency_sec": market_payload.get("cycle_latency_sec"),
                        "market_closed": market_payload.get("market_closed"),
                        "close_window_active": market_payload.get("close_window_active"),
                    },
                )
            )

    indicator_payload = _payload(indicator_readiness)
    if indicator_payload is not None:
        evidence_sources.append("live_indicator_readiness")
        if not bool(indicator_payload.get("indicators_ready")):
            blocked_decisions = [
                _indicator_decision_summary(decision)
                for decision in _list(indicator_payload.get("decisions"))
                if isinstance(decision, Mapping) and not bool(decision.get("ready"))
            ]
            reasons.append(
                _reason(
                    CATEGORY_INDICATOR,
                    INDICATOR_READINESS_BLOCKED_REASON,
                    75,
                    "Indicator readiness is not complete for supplied symbols.",
                    {
                        "blockers": list(_list(indicator_payload.get("blockers"))),
                        "blocked_count": indicator_payload.get("blocked_count"),
                        "ready_count": indicator_payload.get("ready_count"),
                        "blocked_decisions": blocked_decisions,
                    },
                )
            )

    scoring_payload = _payload(scoring)
    if scoring_payload is not None:
        evidence_sources.append("opportunity_scoring")
        score_count = _int(scoring_payload.get("score_count"))
        score_eligible_count = _int(scoring_payload.get("score_eligible_count"))
        if score_count == 0:
            reasons.append(
                _reason(
                    CATEGORY_CANDIDATE,
                    NO_SCORED_CANDIDATES_REASON,
                    70,
                    "No scored candidates exist for promotion.",
                    {"score_count": score_count},
                )
            )
        elif score_eligible_count == 0:
            reasons.append(
                _reason(
                    CATEGORY_CANDIDATE,
                    NO_SCORE_ELIGIBLE_CANDIDATES_REASON,
                    68,
                    "Scoring produced no score-eligible candidates.",
                    {
                        "score_count": score_count,
                        "advisory_count": scoring_payload.get("advisory_count"),
                        "suppressed_count": scoring_payload.get("suppressed_count"),
                        "no_trade_count": scoring_payload.get("no_trade_count"),
                        "blockers": list(_list(scoring_payload.get("blockers"))),
                        "safety_flags": list(_list(scoring_payload.get("safety_flags"))),
                    },
                )
            )

    ranking_payload = _payload(ranking)
    if ranking_payload is not None:
        evidence_sources.append("candidate_ranking")
        rank_count = _int(ranking_payload.get("rank_count"))
        executable_count = _int(ranking_payload.get("executable_count"))
        if rank_count == 0:
            reasons.append(
                _reason(
                    CATEGORY_CANDIDATE,
                    NO_RANKED_CANDIDATES_REASON,
                    72,
                    "Ranking produced no ranked candidates.",
                    {
                        "rank_count": rank_count,
                        "blockers": list(_list(ranking_payload.get("blockers"))),
                        "safety_flags": list(_list(ranking_payload.get("safety_flags"))),
                    },
                )
            )
        elif executable_count == 0:
            reasons.append(
                _reason(
                    CATEGORY_CANDIDATE,
                    NO_EXECUTABLE_RANKS_REASON,
                    69,
                    "Ranking produced no executable candidates.",
                    {
                        "rank_count": rank_count,
                        "near_executable_count": ranking_payload.get("near_executable_count"),
                        "advisory_count": ranking_payload.get("advisory_count"),
                        "suppressed_count": ranking_payload.get("suppressed_count"),
                        "no_trade_count": ranking_payload.get("no_trade_count"),
                        "blockers": list(_list(ranking_payload.get("blockers"))),
                        "safety_flags": list(_list(ranking_payload.get("safety_flags"))),
                    },
                )
            )

    executable_payloads = tuple(_payload(item) for item in tuple(executable_truths or ()))
    executable_payloads = tuple(item for item in executable_payloads if item is not None)
    if executable_payloads:
        evidence_sources.append("executable_truth")
        blocked = tuple(item for item in executable_payloads if _execution_allowed(item) is False)
        allowed = tuple(item for item in executable_payloads if _execution_allowed(item) is True)
        if blocked and not allowed:
            reasons.append(
                _reason(
                    CATEGORY_EXECUTABLE,
                    EXECUTABLE_TRUTH_BLOCKED_REASON,
                    80,
                    "Executable-truth evidence blocks every supplied candidate.",
                    {
                        "blocked_count": len(blocked),
                        "allowed_count": len(allowed),
                        "blocked_reasons": list(
                            _dedupe(
                                str(reason)
                                for payload in blocked
                                for reason in _list(payload.get("reasons", (payload.get("reason_code"),)))
                            )
                        ),
                    },
                )
            )

    if candidate_count is not None and _int(candidate_count) == 0:
        reasons.append(
            _reason(
                CATEGORY_CANDIDATE,
                NO_RANKED_CANDIDATES_REASON,
                71,
                "Candidate source reported zero candidates.",
                {"candidate_count": 0},
            )
        )

    if not evidence_sources:
        reasons.append(
            _reason(
                CATEGORY_EVIDENCE,
                MISSING_EVIDENCE_REASON,
                100,
                "No no-trade evidence was supplied; failing closed.",
                {"expected_sources": _expected_sources()},
            )
        )

    ordered_reasons = tuple(sorted(reasons, key=lambda item: (-item.severity, item.category, item.reason_code)))
    no_trade_required = bool(ordered_reasons)
    blockers = tuple(_dedupe(reason.reason_code for reason in ordered_reasons))
    status = NO_TRADE_REQUIRED if no_trade_required else TRADE_ALLOWED_BY_SUPPLIED_EVIDENCE
    return NoTradeOracleReport(
        schema_version=NO_TRADE_ORACLE_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        status=status,
        no_trade_required=no_trade_required,
        primary_reason=ordered_reasons[0].reason_code if ordered_reasons else "no_no_trade_blockers",
        reasons=ordered_reasons,
        blockers=blockers,
        warnings=tuple(_dedupe(warnings)),
        evidence_sources=tuple(_dedupe(evidence_sources)),
        metadata={
            "oracle": NO_TRADE_ORACLE_SOURCE,
            "scope": "read_only_explanation_only_no_runtime_wiring",
            "fail_closed_on_missing_evidence": True,
            "does_not_submit_orders": True,
            "does_not_call_external_execution": True,
            "does_not_append_runtime_files": True,
            "does_not_rank_candidates": True,
            "does_not_score_edge": True,
            "expected_sources": _expected_sources(),
        },
        generated_epoch=generated_epoch,
    )


def _feed_health_payload(feed_health: FeedHealthTruthDecision | Mapping[str, Any] | None) -> dict[str, Any] | None:
    if feed_health is None:
        return None
    if isinstance(feed_health, FeedHealthTruthDecision):
        return feed_health.to_payload()
    if isinstance(feed_health, Mapping):
        if "feed_ok" in feed_health or "reason_code" in feed_health:
            return dict(feed_health)
        return classify_feed_health_truth(dict(feed_health)).to_payload()
    return None


def _feed_hold_payload(
    feed_hold: FeedHoldDecision | Mapping[str, Any] | None,
    feed_health: FeedHealthTruthDecision | Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if feed_hold is not None:
        return _payload(feed_hold)
    if feed_health is not None:
        return classify_feed_hold(feed_health).to_dict()
    return None


def _payload(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    for method_name in ("to_payload", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            out = method()
            return dict(out) if isinstance(out, Mapping) else None
    if hasattr(value, "execution_allowed"):
        return {
            "execution_allowed": bool(getattr(value, "execution_allowed")),
            "reason_code": getattr(value, "reason_code", None),
            "reasons": list(getattr(value, "reasons", ())),
            "context": dict(getattr(value, "context", {}) or {}),
        }
    return None


def _indicator_decision_summary(decision: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": decision.get("symbol"),
        "decision_gate_reason": decision.get("decision_gate_reason"),
        "blockers": list(_list(decision.get("blockers"))),
        "ohlc_bars_count": decision.get("ohlc_bars_count"),
        "warmup_min_bars": decision.get("warmup_min_bars"),
        "indicator_missing_inputs": list(_list(decision.get("indicator_missing_inputs"))),
    }


def _execution_allowed(payload: Mapping[str, Any]) -> bool | None:
    value = payload.get("execution_allowed")
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return None
    return str(value).strip().lower() in {"1", "true", "yes", "ok", "allowed"}


def _market_severity(state: str) -> int:
    normalized = state.strip().upper()
    if normalized == "MARKET_CLOSED":
        return 95
    if normalized == "WEBSOCKET_DISCONNECTED":
        return 92
    if normalized == "CYCLE_LATENCY_STALE":
        return 87
    if normalized in {"LTP_STALE", "OPTION_FEED_STALE", "CLOSE_WINDOW_TICK_SLOWDOWN"}:
        return 85
    return 82


def _reason(category: str, reason_code: str, severity: int, message: str, evidence: Mapping[str, Any]) -> NoTradeReason:
    return NoTradeReason(
        category=category,
        reason_code=reason_code,
        severity=int(severity),
        message=message,
        evidence=dict(evidence),
    )


def _list(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, set):
        return tuple(sorted(value))
    return (value,)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value or "").strip()}))


def _expected_sources() -> list[str]:
    return [
        "feed_health_truth",
        "feed_hold_gate",
        "market_close_feed_state",
        "live_indicator_readiness",
        "opportunity_scoring",
        "candidate_ranking",
        "executable_truth",
    ]


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "CATEGORY_CANDIDATE",
    "CATEGORY_EVIDENCE",
    "CATEGORY_EXECUTABLE",
    "CATEGORY_FEED",
    "CATEGORY_INDICATOR",
    "CATEGORY_MARKET",
    "EXECUTABLE_TRUTH_BLOCKED_REASON",
    "FEED_HEALTH_BLOCKED_REASON",
    "FEED_HOLD_ACTIVE_REASON",
    "INDICATOR_READINESS_BLOCKED_REASON",
    "MARKET_FEED_STATE_BLOCKED_REASON",
    "MISSING_EVIDENCE_REASON",
    "NO_EXECUTABLE_RANKS_REASON",
    "NO_RANKED_CANDIDATES_REASON",
    "NO_SCORED_CANDIDATES_REASON",
    "NO_SCORE_ELIGIBLE_CANDIDATES_REASON",
    "NO_TRADE_ORACLE_SCHEMA_VERSION",
    "NO_TRADE_ORACLE_SOURCE",
    "NO_TRADE_REQUIRED",
    "TRADE_ALLOWED_BY_SUPPLIED_EVIDENCE",
    "NoTradeOracleReport",
    "NoTradeReason",
    "build_no_trade_oracle_report",
]
