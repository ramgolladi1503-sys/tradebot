"""Paper trading runbook command model.

This module builds a deterministic runbook report from an already-produced paper
session snapshot. It does not start runtime, read/write files, mutate paper
orders or ledgers, call brokers, or enable live behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.paper_session_gate import SESSION_GATE_PASS, build_paper_session_gate_report

PAPER_TRADING_RUNBOOK_COMMAND_SCHEMA_VERSION = 1

RUNBOOK_READY = "RUNBOOK_READY"
RUNBOOK_BLOCKED = "RUNBOOK_BLOCKED"

DEFAULT_NEXT_ACTIONS: tuple[str, ...] = (
    "Review the full-session paper gate report.",
    "Attach the runbook output to the PR or session evidence.",
    "Do not proceed to broker dry-run gates unless the runbook state is RUNBOOK_READY.",
)


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


@dataclass(frozen=True)
class PaperTradingRunbookReport:
    schema_version: int
    state: str
    read_only: bool
    is_order_action: bool
    append: bool
    broker_order_action: bool
    live_order_action: bool
    command: str
    session_id: str | None
    gate_state: str | None
    evidence_complete: bool
    paper_order_count: int | None
    paper_fill_count: int | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    next_actions: tuple[str, ...]
    gate_report: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["next_actions"] = list(self.next_actions)
        payload["gate_report"] = dict(self.gate_report)
        payload["metadata"] = dict(self.metadata)
        return payload


def build_paper_trading_runbook_report(
    session_snapshot: Any,
    *,
    command: str = "paper-trading-runbook",
    thresholds: Mapping[str, Any] | None = None,
) -> PaperTradingRunbookReport:
    """Build a runbook report from a supplied paper session snapshot."""

    blockers: list[str] = []
    warnings: list[str] = []

    snapshot = _to_mapping(session_snapshot)
    if snapshot is None:
        blockers.append("SESSION_SNAPSHOT_MISSING")
        snapshot = {}
    else:
        if _bool(snapshot.get("broker_order_action"), default=False):
            blockers.append("SESSION_SNAPSHOT_BROKER_ORDER_ACTION_REJECTED")
        if _bool(snapshot.get("live_order_action"), default=False):
            blockers.append("SESSION_SNAPSHOT_LIVE_ORDER_ACTION_REJECTED")
        if _bool(snapshot.get("is_order_action"), default=False):
            blockers.append("SESSION_SNAPSHOT_ORDER_ACTION_REJECTED")
        if _bool(snapshot.get("append"), default=False):
            blockers.append("SESSION_SNAPSHOT_APPEND_TRUE_REJECTED")

    gate = build_paper_session_gate_report(snapshot, thresholds=thresholds)
    gate_payload = gate.to_dict()
    blockers.extend(_list_of_strings(gate_payload.get("blockers")))
    warnings.extend(_list_of_strings(gate_payload.get("warnings")))

    gate_state = _text(gate_payload.get("state"))
    evidence_complete = _bool(gate_payload.get("evidence_complete"), default=False)
    if gate_state != SESSION_GATE_PASS:
        blockers.append("PAPER_SESSION_GATE_NOT_PASS")
    if not evidence_complete:
        blockers.append("PAPER_SESSION_EVIDENCE_INCOMPLETE")

    normalized_blockers = _dedupe(blockers)
    normalized_warnings = _dedupe(warnings)
    ready = not normalized_blockers

    return PaperTradingRunbookReport(
        schema_version=PAPER_TRADING_RUNBOOK_COMMAND_SCHEMA_VERSION,
        state=RUNBOOK_READY if ready else RUNBOOK_BLOCKED,
        read_only=True,
        is_order_action=False,
        append=False,
        broker_order_action=False,
        live_order_action=False,
        command=str(command or "paper-trading-runbook"),
        session_id=_text(gate_payload.get("session_id")),
        gate_state=gate_state,
        evidence_complete=evidence_complete,
        paper_order_count=gate_payload.get("paper_order_count"),
        paper_fill_count=gate_payload.get("paper_fill_count"),
        blockers=normalized_blockers,
        warnings=normalized_warnings,
        next_actions=DEFAULT_NEXT_ACTIONS,
        gate_report=gate_payload,
        metadata={
            "runbook_command": "paper_trading_runbook_command_v1",
            "scope": "read_only_no_runtime_start_no_broker_calls_no_order_mutation_no_file_io",
            "schema_version": PAPER_TRADING_RUNBOOK_COMMAND_SCHEMA_VERSION,
        },
    )


__all__ = [
    "PAPER_TRADING_RUNBOOK_COMMAND_SCHEMA_VERSION",
    "RUNBOOK_BLOCKED",
    "RUNBOOK_READY",
    "PaperTradingRunbookReport",
    "build_paper_trading_runbook_report",
]
