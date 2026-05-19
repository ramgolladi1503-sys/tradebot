"""Full-session paper trading gate.

This module evaluates a completed paper-trading session snapshot and returns a
stable pass/fail report. It does not read runtime files, write evidence, create
orders, mutate paper ledgers, call brokers, or wire dashboard/runtime behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

PAPER_SESSION_GATE_SCHEMA_VERSION = 1

SESSION_GATE_PASS = "SESSION_GATE_PASS"
SESSION_GATE_FAIL = "SESSION_GATE_FAIL"


class PaperSessionGateError(ValueError):
    """Raised when the session gate receives invalid configuration."""


def _to_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    return None


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if out == out else None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _list_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


def _threshold_float(thresholds: Mapping[str, Any], key: str, default: float) -> float:
    value = _as_float(thresholds.get(key))
    return float(default if value is None else value)


def _threshold_int(thresholds: Mapping[str, Any], key: str, default: int) -> int:
    value = _as_int(thresholds.get(key))
    return int(default if value is None else value)


def _metric_float(snapshot: Mapping[str, Any], key: str, blockers: list[str]) -> float | None:
    value = _as_float(snapshot.get(key))
    if value is None:
        blockers.append(f"{key.upper()}_MISSING")
        return None
    return round(float(value), 6)


def _metric_int(snapshot: Mapping[str, Any], key: str, blockers: list[str]) -> int | None:
    value = _as_int(snapshot.get(key))
    if value is None:
        blockers.append(f"{key.upper()}_MISSING")
        return None
    return int(value)


@dataclass(frozen=True)
class PaperSessionGateReport:
    schema_version: int
    state: str
    read_only: bool
    is_order_action: bool
    append: bool
    broker_order_action: bool
    live_order_action: bool
    session_id: str | None
    feed_uptime_pct: float | None
    stale_feed_duration_sec: float | None
    ws_disconnect_count: int | None
    restart_count: int | None
    crash_loop_detected: bool
    evidence_complete: bool
    candidate_count: int | None
    paper_order_count: int | None
    paper_fill_count: int | None
    paper_rejection_count: int | None
    fallback_paper_fill_count: int | None
    stale_feed_paper_fill_count: int | None
    unresolved_contract_paper_fill_count: int | None
    missing_evidence_trade_count: int | None
    realized_pnl: float | None
    max_drawdown: float | None
    pass_criteria: dict[str, Any]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pass_criteria"] = dict(self.pass_criteria)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        payload["metadata"] = dict(self.metadata)
        return payload


def build_paper_session_gate_report(
    session_snapshot: Any,
    *,
    thresholds: Mapping[str, Any] | None = None,
) -> PaperSessionGateReport:
    """Evaluate a full paper-trading session snapshot.

    The gate is intentionally conservative. Missing critical evidence fails the
    session because a paper session without evidence is not proof of stability.
    """

    snapshot = _to_mapping(session_snapshot)
    limits = dict(thresholds or {})
    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    if snapshot is None:
        blockers.append("SESSION_SNAPSHOT_MISSING")
        snapshot = {}

    blockers.extend(_list_of_strings(snapshot.get("blockers")))
    warnings.extend(_list_of_strings(snapshot.get("warnings")))

    if _bool(snapshot.get("broker_order_action"), default=False):
        blockers.append("SESSION_SNAPSHOT_BROKER_ORDER_ACTION_REJECTED")
    if _bool(snapshot.get("live_order_action"), default=False):
        blockers.append("SESSION_SNAPSHOT_LIVE_ORDER_ACTION_REJECTED")
    if _bool(snapshot.get("is_order_action"), default=False):
        blockers.append("SESSION_SNAPSHOT_ORDER_ACTION_REJECTED")
    if _bool(snapshot.get("append"), default=False):
        blockers.append("SESSION_SNAPSHOT_APPEND_TRUE_REJECTED")

    session_id = _text(snapshot.get("session_id"))
    if session_id is None:
        blockers.append("SESSION_ID_MISSING")

    min_feed_uptime_pct = _threshold_float(limits, "min_feed_uptime_pct", 95.0)
    max_stale_feed_duration_sec = _threshold_float(limits, "max_stale_feed_duration_sec", 120.0)
    max_ws_disconnect_count = _threshold_int(limits, "max_ws_disconnect_count", 3)
    max_restart_count = _threshold_int(limits, "max_restart_count", 1)
    max_drawdown_abs = _as_float(limits.get("max_drawdown_abs"))

    if min_feed_uptime_pct < 0.0 or min_feed_uptime_pct > 100.0:
        raise PaperSessionGateError("min_feed_uptime_pct_invalid")
    if max_stale_feed_duration_sec < 0.0:
        raise PaperSessionGateError("max_stale_feed_duration_sec_invalid")
    if max_ws_disconnect_count < 0:
        raise PaperSessionGateError("max_ws_disconnect_count_invalid")
    if max_restart_count < 0:
        raise PaperSessionGateError("max_restart_count_invalid")
    if max_drawdown_abs is not None and max_drawdown_abs < 0.0:
        raise PaperSessionGateError("max_drawdown_abs_invalid")

    feed_uptime_pct = _metric_float(snapshot, "feed_uptime_pct", blockers)
    stale_feed_duration_sec = _metric_float(snapshot, "stale_feed_duration_sec", blockers)
    ws_disconnect_count = _metric_int(snapshot, "ws_disconnect_count", blockers)
    restart_count = _metric_int(snapshot, "restart_count", blockers)
    candidate_count = _metric_int(snapshot, "candidate_count", blockers)
    paper_order_count = _metric_int(snapshot, "paper_order_count", blockers)
    paper_fill_count = _metric_int(snapshot, "paper_fill_count", blockers)
    paper_rejection_count = _metric_int(snapshot, "paper_rejection_count", blockers)
    fallback_paper_fill_count = _metric_int(snapshot, "fallback_paper_fill_count", blockers)
    stale_feed_paper_fill_count = _metric_int(snapshot, "stale_feed_paper_fill_count", blockers)
    unresolved_contract_paper_fill_count = _metric_int(snapshot, "unresolved_contract_paper_fill_count", blockers)
    missing_evidence_trade_count = _metric_int(snapshot, "missing_evidence_trade_count", blockers)
    realized_pnl = _metric_float(snapshot, "realized_pnl", blockers)
    max_drawdown = _metric_float(snapshot, "max_drawdown", blockers)

    evidence_complete = _bool(snapshot.get("evidence_complete"), default=False)
    crash_loop_detected = _bool(snapshot.get("crash_loop_detected"), default=False)

    if snapshot.get("evidence_complete") is None:
        blockers.append("EVIDENCE_COMPLETE_MISSING")
    elif not evidence_complete:
        blockers.append("EVIDENCE_INCOMPLETE")
    if snapshot.get("crash_loop_detected") is None:
        blockers.append("CRASH_LOOP_SIGNAL_MISSING")
    elif crash_loop_detected:
        blockers.append("CRASH_LOOP_DETECTED")

    if feed_uptime_pct is not None and feed_uptime_pct < min_feed_uptime_pct:
        blockers.append("FEED_UPTIME_BELOW_MIN")
    if stale_feed_duration_sec is not None and stale_feed_duration_sec > max_stale_feed_duration_sec:
        blockers.append("STALE_FEED_DURATION_EXCEEDED")
    if ws_disconnect_count is not None and ws_disconnect_count > max_ws_disconnect_count:
        blockers.append("WS_DISCONNECT_LIMIT_EXCEEDED")
    if restart_count is not None and restart_count > max_restart_count:
        blockers.append("RESTART_LIMIT_EXCEEDED")

    count_fields = {
        "candidate_count": candidate_count,
        "paper_order_count": paper_order_count,
        "paper_fill_count": paper_fill_count,
        "paper_rejection_count": paper_rejection_count,
        "fallback_paper_fill_count": fallback_paper_fill_count,
        "stale_feed_paper_fill_count": stale_feed_paper_fill_count,
        "unresolved_contract_paper_fill_count": unresolved_contract_paper_fill_count,
        "missing_evidence_trade_count": missing_evidence_trade_count,
    }
    for key, value in count_fields.items():
        if value is not None and value < 0:
            blockers.append(f"{key.upper()}_NEGATIVE")

    if fallback_paper_fill_count is not None and fallback_paper_fill_count > 0:
        blockers.append("FALLBACK_PAPER_FILLS_PRESENT")
    if stale_feed_paper_fill_count is not None and stale_feed_paper_fill_count > 0:
        blockers.append("STALE_FEED_PAPER_FILLS_PRESENT")
    if unresolved_contract_paper_fill_count is not None and unresolved_contract_paper_fill_count > 0:
        blockers.append("UNRESOLVED_CONTRACT_PAPER_FILLS_PRESENT")
    if missing_evidence_trade_count is not None and missing_evidence_trade_count > 0:
        blockers.append("MISSING_EVIDENCE_TRADES_PRESENT")

    if paper_fill_count is not None and paper_order_count is not None and paper_fill_count > paper_order_count:
        blockers.append("PAPER_FILLS_EXCEED_PAPER_ORDERS")
    if paper_order_count is not None and candidate_count is not None and paper_order_count > candidate_count:
        blockers.append("PAPER_ORDERS_EXCEED_CANDIDATES")
    if paper_fill_count == 0:
        warnings.append("NO_PAPER_FILLS_OBSERVED")
    if candidate_count == 0:
        warnings.append("NO_CANDIDATES_OBSERVED")

    if max_drawdown is not None and max_drawdown_abs is not None and abs(max_drawdown) > max_drawdown_abs:
        blockers.append("MAX_DRAWDOWN_EXCEEDED")

    normalized_blockers = _dedupe(blockers)
    normalized_warnings = _dedupe(warnings)
    passed = not normalized_blockers
    if passed:
        state = SESSION_GATE_PASS
        reasons.append("paper_session_met_full_session_gate")
    else:
        state = SESSION_GATE_FAIL
        reasons.append("paper_session_failed_full_session_gate")

    pass_criteria = {
        "min_feed_uptime_pct": min_feed_uptime_pct,
        "max_stale_feed_duration_sec": max_stale_feed_duration_sec,
        "max_ws_disconnect_count": max_ws_disconnect_count,
        "max_restart_count": max_restart_count,
        "max_drawdown_abs": max_drawdown_abs,
        "requires_zero_fallback_paper_fills": True,
        "requires_zero_stale_feed_paper_fills": True,
        "requires_zero_unresolved_contract_paper_fills": True,
        "requires_zero_missing_evidence_trades": True,
        "requires_no_crash_loop": True,
        "requires_evidence_complete": True,
    }

    return PaperSessionGateReport(
        schema_version=PAPER_SESSION_GATE_SCHEMA_VERSION,
        state=state,
        read_only=True,
        is_order_action=False,
        append=False,
        broker_order_action=False,
        live_order_action=False,
        session_id=session_id,
        feed_uptime_pct=feed_uptime_pct,
        stale_feed_duration_sec=stale_feed_duration_sec,
        ws_disconnect_count=ws_disconnect_count,
        restart_count=restart_count,
        crash_loop_detected=crash_loop_detected,
        evidence_complete=evidence_complete,
        candidate_count=candidate_count,
        paper_order_count=paper_order_count,
        paper_fill_count=paper_fill_count,
        paper_rejection_count=paper_rejection_count,
        fallback_paper_fill_count=fallback_paper_fill_count,
        stale_feed_paper_fill_count=stale_feed_paper_fill_count,
        unresolved_contract_paper_fill_count=unresolved_contract_paper_fill_count,
        missing_evidence_trade_count=missing_evidence_trade_count,
        realized_pnl=realized_pnl,
        max_drawdown=max_drawdown,
        pass_criteria=pass_criteria,
        blockers=normalized_blockers,
        warnings=normalized_warnings,
        reasons=tuple(sorted({reason for reason in reasons if reason})),
        metadata={
            "gate": "paper_session_gate_v1",
            "scope": "read_only_no_runtime_wiring_no_broker_calls_no_order_mutation_no_persistence",
            "schema_version": PAPER_SESSION_GATE_SCHEMA_VERSION,
        },
    )


__all__ = [
    "PAPER_SESSION_GATE_SCHEMA_VERSION",
    "SESSION_GATE_FAIL",
    "SESSION_GATE_PASS",
    "PaperSessionGateError",
    "PaperSessionGateReport",
    "build_paper_session_gate_report",
]
