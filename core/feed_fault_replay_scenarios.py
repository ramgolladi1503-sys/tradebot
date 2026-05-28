from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from core.feed_health_truth import FeedHealthTruthDecision, classify_feed_health_truth
from core.feed_hold_gate import FeedHoldDecision, classify_feed_hold

FEED_FAULT_REPLAY_SCHEMA_VERSION = 1
FEED_FAULT_REPLAY_SOURCE = "feed_fault_replay_scenarios_v1"
FEED_FAULT_REPLAY_PASSED = "FEED_FAULT_REPLAY_PASSED"
FEED_FAULT_REPLAY_BLOCKED = "FEED_FAULT_REPLAY_BLOCKED"

MISSING_CANDIDATE_ID = "MISSING_CANDIDATE_ID"
INVALID_FEED_PAYLOAD = "INVALID_FEED_PAYLOAD"
OK_REASON = "OK"


@dataclass(frozen=True)
class FeedFaultReplayEvidence:
    schema_version: int
    source: str
    scenario_id: str
    candidate_id: str
    symbol: str
    fault_type: str
    valid: bool
    reason: str
    feed_ok: bool
    hold_active: bool
    replay_should_block: bool
    feed_reason_code: str
    feed_reasons: tuple[str, ...]
    hold_reason: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    feed_health_truth: Mapping[str, Any]
    feed_hold: Mapping[str, Any]
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
        payload = asdict(self)
        payload["read_only"] = True
        payload["append"] = False
        payload["is_order_action"] = False
        payload["broker_api_called"] = False
        payload["live_order_action"] = False
        payload["broker_order_action"] = False
        return payload


@dataclass(frozen=True)
class FeedFaultReplayReport:
    schema_version: int
    source: str
    status: str
    scenario_count: int
    blocked_scenario_count: int
    clear_scenario_count: int
    invalid_scenario_count: int
    reasons: tuple[str, ...]
    evidence: tuple[FeedFaultReplayEvidence, ...]
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
        payload = asdict(self)
        payload["evidence"] = [item.to_payload() for item in self.evidence]
        payload["read_only"] = True
        payload["append"] = False
        payload["is_order_action"] = False
        payload["broker_api_called"] = False
        payload["live_order_action"] = False
        payload["broker_order_action"] = False
        return payload


def build_feed_fault_replay_evidence(
    *,
    scenario_id: str | None,
    candidate_id: str | None,
    symbol: str | None,
    feed_payload: Mapping[str, Any] | None,
    expected_block: bool | None = None,
    max_option_tick_age_sec: float = 3.0,
    max_ltp_age_sec: float | None = 2.5,
    max_depth_age_sec: float | None = 6.0,
    metadata: Mapping[str, Any] | None = None,
) -> FeedFaultReplayEvidence:
    candidate = str(candidate_id or "").strip()
    normalized_symbol = str(symbol or "").strip().upper()
    if not candidate:
        return _invalid_evidence(
            scenario_id=scenario_id,
            candidate_id="",
            symbol=normalized_symbol,
            reason=MISSING_CANDIDATE_ID,
            metadata=metadata,
        )
    if not isinstance(feed_payload, Mapping):
        return _invalid_evidence(
            scenario_id=scenario_id,
            candidate_id=candidate,
            symbol=normalized_symbol,
            reason=INVALID_FEED_PAYLOAD,
            metadata=metadata,
        )

    feed_truth = classify_feed_health_truth(
        dict(feed_payload),
        symbols=(normalized_symbol,) if normalized_symbol else (),
        max_option_tick_age_sec=max_option_tick_age_sec,
        max_ltp_age_sec=max_ltp_age_sec,
        max_depth_age_sec=max_depth_age_sec,
    )
    hold = classify_feed_hold(feed_truth)
    expected = hold.hold_active if expected_block is None else bool(expected_block)
    actual_block = bool(hold.hold_active)
    reason = OK_REASON if expected == actual_block else "FEED_FAULT_EXPECTATION_MISMATCH"
    return _evidence_from_decisions(
        scenario_id=scenario_id,
        candidate_id=candidate,
        symbol=normalized_symbol,
        feed_truth=feed_truth,
        hold=hold,
        valid=reason == OK_REASON,
        reason=reason,
        replay_should_block=actual_block,
        metadata={
            "expected_block": expected,
            "actual_block": actual_block,
            "evidence_only": True,
            **dict(metadata or {}),
        },
    )


def build_feed_fault_replay_report(
    replay_scenarios: Sequence[Mapping[str, Any]] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> FeedFaultReplayReport:
    rows = tuple(replay_scenarios or ())
    evidence = tuple(
        build_feed_fault_replay_evidence(
            scenario_id=_pick_text(row, "scenario_id", "id"),
            candidate_id=_pick_text(row, "candidate_id"),
            symbol=_pick_text(row, "symbol", "instrument", "tradingsymbol"),
            feed_payload=_pick_mapping(row, "feed_payload", "feed_health", "runtime_snapshot"),
            expected_block=_pick_optional_bool(row, "expected_block", "expected_hold", "should_block"),
            metadata=_pick_metadata(row),
        )
        for row in rows
    )
    invalid_count = sum(1 for item in evidence if not item.valid)
    blocked_count = sum(1 for item in evidence if item.replay_should_block)
    reasons = tuple(sorted({item.reason for item in evidence if item.reason != OK_REASON}))
    return FeedFaultReplayReport(
        schema_version=FEED_FAULT_REPLAY_SCHEMA_VERSION,
        source=FEED_FAULT_REPLAY_SOURCE,
        status=FEED_FAULT_REPLAY_BLOCKED if blocked_count or invalid_count else FEED_FAULT_REPLAY_PASSED,
        scenario_count=len(evidence),
        blocked_scenario_count=blocked_count,
        clear_scenario_count=sum(1 for item in evidence if item.valid and not item.replay_should_block),
        invalid_scenario_count=invalid_count,
        reasons=reasons,
        evidence=evidence,
        metadata={
            "evidence_only": True,
            "does_not_rank_candidates": True,
            "does_not_change_execution": True,
            **dict(metadata or {}),
        },
    )


def _invalid_evidence(
    *,
    scenario_id: str | None,
    candidate_id: str,
    symbol: str,
    reason: str,
    metadata: Mapping[str, Any] | None,
) -> FeedFaultReplayEvidence:
    empty_feed_truth = FeedHealthTruthDecision(feed_ok=False, reason_code=reason, reasons=(reason,), context={})
    empty_hold = classify_feed_hold(empty_feed_truth)
    return _evidence_from_decisions(
        scenario_id=scenario_id,
        candidate_id=candidate_id,
        symbol=symbol,
        feed_truth=empty_feed_truth,
        hold=empty_hold,
        valid=False,
        reason=reason,
        replay_should_block=True,
        metadata=dict(metadata or {}),
    )


def _evidence_from_decisions(
    *,
    scenario_id: str | None,
    candidate_id: str,
    symbol: str,
    feed_truth: FeedHealthTruthDecision,
    hold: FeedHoldDecision,
    valid: bool,
    reason: str,
    replay_should_block: bool,
    metadata: Mapping[str, Any],
) -> FeedFaultReplayEvidence:
    feed_reasons = tuple(str(item) for item in feed_truth.reasons)
    return FeedFaultReplayEvidence(
        schema_version=FEED_FAULT_REPLAY_SCHEMA_VERSION,
        source=FEED_FAULT_REPLAY_SOURCE,
        scenario_id=str(scenario_id or candidate_id or "UNKNOWN").strip() or "UNKNOWN",
        candidate_id=candidate_id,
        symbol=symbol or "UNKNOWN",
        fault_type=_classify_fault_type(feed_reasons),
        valid=valid,
        reason=reason,
        feed_ok=bool(feed_truth.feed_ok),
        hold_active=bool(hold.hold_active),
        replay_should_block=bool(replay_should_block),
        feed_reason_code=str(feed_truth.reason_code),
        feed_reasons=feed_reasons,
        hold_reason=str(hold.reason),
        blockers=tuple(str(item) for item in hold.blockers),
        warnings=tuple(str(item) for item in hold.warnings),
        feed_health_truth=feed_truth.to_payload(),
        feed_hold=hold.to_dict(),
        metadata=dict(metadata),
    )


def _classify_fault_type(reasons: tuple[str, ...]) -> str:
    if not reasons:
        return "HEALTHY_FEED"
    joined = "|".join(reasons).lower()
    if "websocket" in joined:
        return "WEBSOCKET_DISCONNECTED"
    if "ltp_ticks_stale" in joined:
        return "LTP_TICKS_STALE"
    if "depth_ticks_stale" in joined:
        return "DEPTH_TICKS_STALE"
    if "option_ticks_stale" in joined:
        return "OPTION_TICKS_STALE"
    if "option_feed_blocked" in joined:
        return "OPTION_FEED_BLOCKED"
    if "runtime_state" in joined:
        return "RUNTIME_STATE_UNSAFE"
    if "feed_state" in joined:
        return "FEED_STATE_UNSAFE"
    if "global_feed" in joined:
        return "GLOBAL_FEED_UNHEALTHY"
    return "UNKNOWN_FEED_FAULT"


def _pick_text(row: Mapping[str, Any], *keys: str) -> str | None:
    value = _pick_value(row, *keys)
    if value is None:
        return None
    return str(value)


def _pick_mapping(row: Mapping[str, Any], *keys: str) -> Mapping[str, Any] | None:
    value = _pick_value(row, *keys)
    return value if isinstance(value, Mapping) else None


def _pick_value(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _pick_optional_bool(row: Mapping[str, Any], *keys: str) -> bool | None:
    value = _pick_value(row, *keys)
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _pick_metadata(row: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = row.get("metadata")
    base = dict(raw) if isinstance(raw, Mapping) else {}
    for key in ("strategy", "timeframe", "source"):
        if key in row:
            base[key] = row[key]
    return base
