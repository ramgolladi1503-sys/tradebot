from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from core.feed_fault_replay_scenarios import (
    FEED_FAULT_REPLAY_PASSED,
    FeedFaultReplayReport,
    build_feed_fault_replay_report,
)
from core.regime_replay_scenarios import (
    REGIME_REPLAY_PASSED,
    RegimeReplayReport,
    build_regime_replay_report,
)
from core.replay_session_path_report import (
    SESSION_PATH_REPLAY_PASSED,
    SessionPathReplayReport,
    build_session_path_replay_report,
)

STRATEGY_REPLAY_PROOF_PACK_SCHEMA_VERSION = 1
STRATEGY_REPLAY_PROOF_PACK_SOURCE = "strategy_replay_proof_pack_v1"

STRATEGY_REPLAY_PROOF_PASSED = "STRATEGY_REPLAY_PROOF_PASSED"
STRATEGY_REPLAY_PROOF_BLOCKED = "STRATEGY_REPLAY_PROOF_BLOCKED"

STRATEGY_PROOF_STATUS_PASSED = "PASSED"
STRATEGY_PROOF_STATUS_BLOCKED = "BLOCKED"

OK_REASON = "OK"
NO_STRATEGY_REPLAY_INPUTS = "NO_STRATEGY_REPLAY_INPUTS"
UNKNOWN_STRATEGY = "UNKNOWN_STRATEGY"


@dataclass(frozen=True)
class StrategyReplayProofSummary:
    """Deterministic strategy-level summary across replay evidence layers."""

    strategy_id: str
    status: str
    candidate_count: int
    valid_candidate_count: int
    invalid_candidate_count: int
    feed_blocked_count: int
    regime_status: str
    session_path_status: str
    feed_fault_status: str
    reasons: tuple[str, ...]
    read_only: bool = True
    append: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

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
            "strategy_id": self.strategy_id,
            "status": self.status,
            "candidate_count": self.candidate_count,
            "valid_candidate_count": self.valid_candidate_count,
            "invalid_candidate_count": self.invalid_candidate_count,
            "feed_blocked_count": self.feed_blocked_count,
            "regime_status": self.regime_status,
            "session_path_status": self.session_path_status,
            "feed_fault_status": self.feed_fault_status,
            "reasons": list(self.reasons),
            "read_only": True,
            "append": False,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class StrategyReplayProofPack:
    """Read-only proof pack combining regime, session-path, and feed-fault replay evidence."""

    schema_version: int
    source: str
    status: str
    strategy_count: int
    passed_strategy_count: int
    blocked_strategy_count: int
    candidate_count: int
    valid_candidate_count: int
    invalid_candidate_count: int
    feed_blocked_count: int
    reasons: tuple[str, ...]
    regime_replay: RegimeReplayReport
    session_path_replay: SessionPathReplayReport
    feed_fault_replay: FeedFaultReplayReport
    strategy_summaries: tuple[StrategyReplayProofSummary, ...]
    read_only: bool = True
    append: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

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
            "source": self.source,
            "status": self.status,
            "strategy_count": self.strategy_count,
            "passed_strategy_count": self.passed_strategy_count,
            "blocked_strategy_count": self.blocked_strategy_count,
            "candidate_count": self.candidate_count,
            "valid_candidate_count": self.valid_candidate_count,
            "invalid_candidate_count": self.invalid_candidate_count,
            "feed_blocked_count": self.feed_blocked_count,
            "reasons": list(self.reasons),
            "regime_replay": self.regime_replay.to_payload(),
            "session_path_replay": self.session_path_replay.to_payload(),
            "feed_fault_replay": self.feed_fault_replay.to_payload(),
            "strategy_summaries": [summary.to_payload() for summary in self.strategy_summaries],
            "read_only": True,
            "append": False,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


def build_strategy_replay_proof_pack(
    *,
    regime_scenarios: Sequence[Mapping[str, Any]] | None = None,
    session_replay_candidates: Sequence[Mapping[str, Any]] | None = None,
    feed_fault_scenarios: Sequence[Mapping[str, Any]] | None = None,
    strategy_key: str = "strategy",
    symbol: str = "MARKET",
    mode: str = "PAPER",
    default_target_pct: float = 4.0,
    metadata: Mapping[str, Any] | None = None,
) -> StrategyReplayProofPack:
    """Build a deterministic, read-only strategy replay proof pack.

    This function is the EDGE-93 aggregation point. It consumes existing replay
    evidence layers and summarizes them by strategy. It does not rank, select,
    execute, mutate runtime state, call brokers, write artifacts, or wire UI.
    """

    session_rows = tuple(session_replay_candidates or ())
    feed_rows = tuple(feed_fault_scenarios or ())

    regime_report = build_regime_replay_report(regime_scenarios, symbol=symbol, mode=mode)
    session_report = build_session_path_replay_report(
        session_rows,
        default_target_pct=default_target_pct,
        metadata={"source": STRATEGY_REPLAY_PROOF_PACK_SOURCE},
    )
    feed_report = build_feed_fault_replay_report(
        feed_rows,
        metadata={"source": STRATEGY_REPLAY_PROOF_PACK_SOURCE},
    )

    summaries = _build_strategy_summaries(
        regime_report=regime_report,
        session_report=session_report,
        feed_report=feed_report,
        strategy_key=strategy_key,
    )
    no_strategy_inputs = not summaries
    blocked_strategy_count = sum(1 for item in summaries if item.status == STRATEGY_PROOF_STATUS_BLOCKED)
    passed_strategy_count = sum(1 for item in summaries if item.status == STRATEGY_PROOF_STATUS_PASSED)

    reasons = _pack_reasons(
        regime_report=regime_report,
        session_report=session_report,
        feed_report=feed_report,
        summaries=summaries,
        no_strategy_inputs=no_strategy_inputs,
    )
    status = (
        STRATEGY_REPLAY_PROOF_PASSED
        if not reasons and summaries and blocked_strategy_count == 0
        else STRATEGY_REPLAY_PROOF_BLOCKED
    )

    return StrategyReplayProofPack(
        schema_version=STRATEGY_REPLAY_PROOF_PACK_SCHEMA_VERSION,
        source=STRATEGY_REPLAY_PROOF_PACK_SOURCE,
        status=status,
        strategy_count=len(summaries),
        passed_strategy_count=passed_strategy_count,
        blocked_strategy_count=blocked_strategy_count,
        candidate_count=sum(item.candidate_count for item in summaries),
        valid_candidate_count=sum(item.valid_candidate_count for item in summaries),
        invalid_candidate_count=sum(item.invalid_candidate_count for item in summaries),
        feed_blocked_count=sum(item.feed_blocked_count for item in summaries),
        reasons=reasons,
        regime_replay=regime_report,
        session_path_replay=session_report,
        feed_fault_replay=feed_report,
        strategy_summaries=summaries,
        metadata={
            "evidence_only": True,
            "does_not_rank_candidates": True,
            "does_not_select_strategies": True,
            "does_not_change_strategies": True,
            "does_not_change_execution": True,
            "does_not_wire_runtime": True,
            "does_not_wire_dashboard": True,
            **dict(metadata or {}),
        },
    )


def _build_strategy_summaries(
    *,
    regime_report: RegimeReplayReport,
    session_report: SessionPathReplayReport,
    feed_report: FeedFaultReplayReport,
    strategy_key: str,
) -> tuple[StrategyReplayProofSummary, ...]:
    strategy_ids = sorted(
        {
            *(_strategy_id(item.metadata, strategy_key=strategy_key) for item in session_report.evidence),
            *(_strategy_id(item.metadata, strategy_key=strategy_key) for item in feed_report.evidence),
        }
    )
    summaries: list[StrategyReplayProofSummary] = []
    for strategy_id in strategy_ids:
        session_items = tuple(
            item for item in session_report.evidence if _strategy_id(item.metadata, strategy_key=strategy_key) == strategy_id
        )
        feed_items = tuple(
            item for item in feed_report.evidence if _strategy_id(item.metadata, strategy_key=strategy_key) == strategy_id
        )
        candidate_ids = sorted(
            {
                *(item.candidate_id for item in session_items if item.candidate_id),
                *(item.candidate_id for item in feed_items if item.candidate_id),
            }
        )
        candidate_count = len(candidate_ids) if candidate_ids else len(session_items) + len(feed_items)
        session_invalid_count = sum(1 for item in session_items if not item.valid)
        feed_invalid_count = sum(1 for item in feed_items if not item.valid)
        feed_blocked_count = sum(1 for item in feed_items if item.replay_should_block)
        invalid_count = session_invalid_count + feed_invalid_count
        reasons = _strategy_reasons(
            regime_report=regime_report,
            session_report=session_report,
            feed_report=feed_report,
            session_items=session_items,
            feed_items=feed_items,
        )
        status = STRATEGY_PROOF_STATUS_BLOCKED if reasons or invalid_count or feed_blocked_count else STRATEGY_PROOF_STATUS_PASSED
        summaries.append(
            StrategyReplayProofSummary(
                strategy_id=strategy_id,
                status=status,
                candidate_count=candidate_count,
                valid_candidate_count=sum(1 for item in session_items if item.valid),
                invalid_candidate_count=invalid_count,
                feed_blocked_count=feed_blocked_count,
                regime_status=regime_report.status,
                session_path_status=session_report.status,
                feed_fault_status=feed_report.status,
                reasons=reasons,
                metadata={
                    "session_evidence_count": len(session_items),
                    "feed_fault_evidence_count": len(feed_items),
                    "candidate_ids": candidate_ids,
                    "evidence_only": True,
                },
            )
        )
    return tuple(summaries)


def _strategy_reasons(
    *,
    regime_report: RegimeReplayReport,
    session_report: SessionPathReplayReport,
    feed_report: FeedFaultReplayReport,
    session_items: Sequence[Any],
    feed_items: Sequence[Any],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if regime_report.status != REGIME_REPLAY_PASSED:
        reasons.extend(_clean_reasons(regime_report.reasons or (regime_report.reason_code,)))
    if session_report.status != SESSION_PATH_REPLAY_PASSED:
        reasons.extend(_clean_reasons(session_report.reasons))
    if feed_report.status != FEED_FAULT_REPLAY_PASSED:
        reasons.extend(_clean_reasons(feed_report.reasons))
    for item in session_items:
        if not item.valid:
            reasons.append(str(item.reason))
    for item in feed_items:
        if not item.valid:
            reasons.append(str(item.reason))
        if item.replay_should_block:
            reasons.append(f"feed_fault:{item.fault_type}")
    return _dedupe(reason for reason in reasons if _is_reason(reason))


def _pack_reasons(
    *,
    regime_report: RegimeReplayReport,
    session_report: SessionPathReplayReport,
    feed_report: FeedFaultReplayReport,
    summaries: Sequence[StrategyReplayProofSummary],
    no_strategy_inputs: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if no_strategy_inputs:
        reasons.append(NO_STRATEGY_REPLAY_INPUTS)
    if regime_report.status != REGIME_REPLAY_PASSED:
        reasons.extend(_clean_reasons(regime_report.reasons or (regime_report.reason_code,)))
    if session_report.status != SESSION_PATH_REPLAY_PASSED:
        reasons.extend(_clean_reasons(session_report.reasons))
    if feed_report.status != FEED_FAULT_REPLAY_PASSED:
        reasons.extend(_clean_reasons(feed_report.reasons))
    for summary in summaries:
        reasons.extend(summary.reasons)
    return _dedupe(reason for reason in reasons if _is_reason(reason))


def _strategy_id(metadata: Mapping[str, Any] | None, *, strategy_key: str) -> str:
    if not isinstance(metadata, Mapping):
        return UNKNOWN_STRATEGY
    value = metadata.get(strategy_key) or metadata.get("strategy") or metadata.get("strategy_id")
    text = str(value or "").strip()
    return text or UNKNOWN_STRATEGY


def _clean_reasons(reasons: Sequence[Any]) -> tuple[str, ...]:
    return tuple(str(reason) for reason in reasons if _is_reason(reason))


def _is_reason(reason: Any) -> bool:
    text = str(reason or "").strip()
    return bool(text) and text not in {OK_REASON, "ok"}


def _dedupe(reasons: Sequence[str] | Any) -> tuple[str, ...]:
    return tuple(sorted({str(reason) for reason in reasons if _is_reason(reason)}))


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload["is_order_action"] = False
    payload["broker_api_called"] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False
