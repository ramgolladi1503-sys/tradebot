"""Read-only paper decision orchestrator.

This module composes selection, paper-intent, and risk-decision outputs into one
paper decision report. It does not create paper orders, mutate ledgers, reserve
risk, call brokers, submit payloads, or wire runtime/dashboard behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.paper_intent_contract import PAPER_INTENT_READY
from core.risk_decision import RISK_APPROVED
from core.selection_policy import SELECTED_FOR_PAPER

PAPER_DECISION_SCHEMA_VERSION = 1
PAPER_DECISION_APPROVED = "PAPER_DECISION_APPROVED"
PAPER_DECISION_BLOCKED = "PAPER_DECISION_BLOCKED"


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


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if out == out else None


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


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


@dataclass(frozen=True)
class PaperDecisionReport:
    schema_version: int
    state: str
    read_only: bool
    is_order_action: bool
    append: bool
    allowed_for_paper_order: bool
    allowed_for_live_execution: bool
    paper_intent_id: str | None
    selected_strategy_id: str | None
    symbol: str | None
    direction: str | None
    instrument_token: int | None
    tradingsymbol: str | None
    quantity: int
    entry_price: float | None
    estimated_notional: float
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        payload["metadata"] = dict(self.metadata)
        return payload


def build_paper_decision_report(
    selection_report: Any,
    paper_intent: Any,
    risk_decision: Any,
) -> PaperDecisionReport:
    """Compose final read-only paper decision from prior decision layers."""

    selection = _to_mapping(selection_report)
    intent = _to_mapping(paper_intent)
    risk = _to_mapping(risk_decision)

    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    if selection is None:
        blockers.append("SELECTION_REPORT_MISSING")
    else:
        blockers.extend(_list_of_strings(selection.get("blockers")))
        warnings.extend(_list_of_strings(selection.get("warnings")))
        if not _bool(selection.get("read_only"), default=False):
            blockers.append("SELECTION_REPORT_NOT_READ_ONLY")
        if _bool(selection.get("is_order_action"), default=False):
            blockers.append("SELECTION_REPORT_CONTAINS_ORDER_ACTION")
        if _bool(selection.get("append"), default=False):
            blockers.append("SELECTION_REPORT_APPEND_TRUE")
        if str(selection.get("state") or "") != SELECTED_FOR_PAPER:
            blockers.append("SELECTION_NOT_SELECTED_FOR_PAPER")
        if _as_int(selection.get("selected_count"), default=0) != 1:
            blockers.append("SELECTION_SELECTED_COUNT_NOT_ONE")

    if intent is None:
        blockers.append("PAPER_INTENT_MISSING")
    else:
        blockers.extend(_list_of_strings(intent.get("blockers")))
        warnings.extend(_list_of_strings(intent.get("warnings")))
        if not _bool(intent.get("read_only"), default=False):
            blockers.append("PAPER_INTENT_NOT_READ_ONLY")
        if _bool(intent.get("is_order_action"), default=False):
            blockers.append("PAPER_INTENT_CONTAINS_ORDER_ACTION")
        if _bool(intent.get("append"), default=False):
            blockers.append("PAPER_INTENT_APPEND_TRUE")
        if str(intent.get("state") or "") != PAPER_INTENT_READY:
            blockers.append("PAPER_INTENT_NOT_READY")
        if not _bool(intent.get("ready_for_risk_review"), default=False):
            blockers.append("PAPER_INTENT_NOT_READY_FOR_RISK_REVIEW")
        if _bool(intent.get("allowed_for_paper_order"), default=False):
            blockers.append("PAPER_INTENT_ORDER_PERMISSION_UNEXPECTED")
        if _bool(intent.get("allowed_for_live_execution"), default=False):
            blockers.append("PAPER_INTENT_LIVE_EXECUTION_UNEXPECTED")

    if risk is None:
        blockers.append("RISK_DECISION_MISSING")
    else:
        blockers.extend(_list_of_strings(risk.get("blockers")))
        warnings.extend(_list_of_strings(risk.get("warnings")))
        if not _bool(risk.get("read_only"), default=False):
            blockers.append("RISK_DECISION_NOT_READ_ONLY")
        if _bool(risk.get("is_order_action"), default=False):
            blockers.append("RISK_DECISION_CONTAINS_ORDER_ACTION")
        if _bool(risk.get("append"), default=False):
            blockers.append("RISK_DECISION_APPEND_TRUE")
        if str(risk.get("state") or "") != RISK_APPROVED:
            blockers.append("RISK_DECISION_NOT_APPROVED")
        if not _bool(risk.get("allowed_for_paper_order"), default=False):
            blockers.append("RISK_NOT_ALLOWED_FOR_PAPER_ORDER")
        if _bool(risk.get("allowed_for_live_execution"), default=False):
            blockers.append("RISK_LIVE_EXECUTION_UNEXPECTED")
        if _as_int(risk.get("quantity"), default=0) <= 0:
            blockers.append("RISK_QUANTITY_ZERO")

    normalized_blockers = _dedupe(blockers)
    normalized_warnings = _dedupe(warnings)
    approved = not normalized_blockers

    if approved:
        state = PAPER_DECISION_APPROVED
        reasons.append("selection_intent_and_risk_approved_for_paper_order_creation")
    else:
        state = PAPER_DECISION_BLOCKED
        reasons.append("paper_decision_preconditions_failed")

    paper_intent_id = _first_text(
        intent.get("paper_intent_id") if intent else None,
        risk.get("paper_intent_id") if risk else None,
    )
    selected_strategy_id = _first_text(
        intent.get("selected_strategy_id") if intent else None,
        risk.get("selected_strategy_id") if risk else None,
    )
    symbol = _first_text(risk.get("symbol") if risk else None, intent.get("symbol") if intent else None)
    direction = _first_text(risk.get("direction") if risk else None, intent.get("direction") if intent else None)
    instrument_token = _as_int(risk.get("instrument_token"), default=0) if risk is not None else 0
    if not instrument_token and intent is not None:
        instrument_token = _as_int(intent.get("instrument_token"), default=0)
    tradingsymbol = _first_text(risk.get("tradingsymbol") if risk else None, intent.get("tradingsymbol") if intent else None)
    quantity = _as_int(risk.get("quantity"), default=0) if risk is not None else 0
    entry_price = _as_float(risk.get("entry_price") if risk is not None else None)
    estimated_notional = _as_float(risk.get("estimated_notional") if risk is not None else None) or 0.0

    return PaperDecisionReport(
        schema_version=PAPER_DECISION_SCHEMA_VERSION,
        state=state,
        read_only=True,
        is_order_action=False,
        append=False,
        allowed_for_paper_order=approved,
        allowed_for_live_execution=False,
        paper_intent_id=paper_intent_id,
        selected_strategy_id=selected_strategy_id,
        symbol=symbol,
        direction=direction,
        instrument_token=instrument_token or None,
        tradingsymbol=tradingsymbol,
        quantity=int(quantity),
        entry_price=round(float(entry_price), 6) if entry_price is not None else None,
        estimated_notional=round(float(estimated_notional), 6),
        blockers=normalized_blockers,
        warnings=normalized_warnings,
        reasons=tuple(sorted({reason for reason in reasons if reason})),
        metadata={
            "orchestrator": "paper_decision_orchestrator_v1",
            "scope": "read_only_no_order_creation_no_broker_calls_no_ledger_mutation",
            "requires_selection_policy": True,
            "requires_paper_intent_contract": True,
            "requires_risk_decision": True,
        },
    )


__all__ = [
    "PAPER_DECISION_APPROVED",
    "PAPER_DECISION_BLOCKED",
    "PAPER_DECISION_SCHEMA_VERSION",
    "PaperDecisionReport",
    "build_paper_decision_report",
]
