"""Read-only risk decision for paper intent contracts.

This module sizes or blocks a paper intent before paper-decision orchestration.
It does not create paper orders, reserve capital, update ledgers, call brokers,
mutate intents, or touch runtime/dashboard wiring.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping

from core.paper_intent_contract import PAPER_INTENT_READY

RISK_DECISION_SCHEMA_VERSION = 1
RISK_APPROVED = "RISK_APPROVED"
RISK_BLOCKED = "RISK_BLOCKED"


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


def _as_float(value: Any, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        out = float(value)
    except Exception:
        return default
    return out if out == out else default


def _as_int(value: Any, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


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


def _contains(values: Any, needle: Any) -> bool:
    if needle in (None, "", "None"):
        return False
    return str(needle) in {str(item) for item in _list_of_strings(values)}


@dataclass(frozen=True)
class RiskDecision:
    schema_version: int
    state: str
    read_only: bool
    is_order_action: bool
    append: bool
    allowed_for_paper_order: bool
    allowed_for_live_execution: bool
    paper_intent_id: str | None
    symbol: str | None
    direction: str | None
    instrument_token: int | None
    tradingsymbol: str | None
    quantity: int
    entry_price: float | None
    estimated_notional: float
    max_loss_amount: float | None
    risk_per_unit: float | None
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


def build_risk_decision(
    paper_intent: Any,
    *,
    risk_limits: Mapping[str, Any] | None = None,
    ledger_snapshot: Mapping[str, Any] | None = None,
) -> RiskDecision:
    """Return a fail-closed risk decision for a paper intent contract."""

    intent = _to_mapping(paper_intent)
    limits = dict(risk_limits or {})
    ledger = dict(ledger_snapshot or {})

    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    if intent is None:
        blockers.append("PAPER_INTENT_MISSING")
        reasons.append("paper_intent_required_for_risk_decision")
    else:
        blockers.extend(_list_of_strings(intent.get("blockers")))
        warnings.extend(_list_of_strings(intent.get("warnings")))
        if str(intent.get("state") or "") != PAPER_INTENT_READY:
            blockers.append("PAPER_INTENT_NOT_READY")
        if not _bool(intent.get("ready_for_risk_review"), default=False):
            blockers.append("PAPER_INTENT_NOT_READY_FOR_RISK_REVIEW")
        if _bool(intent.get("is_order_action"), default=False):
            blockers.append("PAPER_INTENT_CONTAINS_ORDER_ACTION")
        if _bool(intent.get("append"), default=False):
            blockers.append("PAPER_INTENT_APPEND_TRUE")
        if _bool(intent.get("allowed_for_live_execution"), default=False):
            blockers.append("PAPER_INTENT_LIVE_EXECUTION_UNEXPECTED")

    ask = _as_float(intent.get("ask") if intent else None)
    instrument_token = _as_int(intent.get("instrument_token") if intent else None)
    tradingsymbol = str(intent.get("tradingsymbol") or "") if intent else ""

    if ask is None or ask <= 0.0:
        blockers.append("ENTRY_PRICE_MISSING")

    max_trade_notional = _as_float(limits.get("max_trade_notional"), default=0.0) or 0.0
    max_total_exposure = _as_float(limits.get("max_total_exposure"), default=0.0) or 0.0
    max_daily_loss = _as_float(limits.get("max_daily_loss"), default=0.0) or 0.0
    max_daily_trades = _as_int(limits.get("max_daily_trades"), default=0) or 0
    max_open_positions = _as_int(limits.get("max_open_positions"), default=0) or 0
    max_contracts_per_trade = _as_int(limits.get("max_contracts_per_trade"), default=0) or 0
    min_contracts_per_trade = _as_int(limits.get("min_contracts_per_trade"), default=1) or 1
    risk_per_trade_pct = _as_float(limits.get("risk_per_trade_pct"), default=1.0) or 1.0
    available_cash = _as_float(limits.get("available_cash"), default=max_total_exposure) or 0.0

    if max_trade_notional <= 0.0:
        blockers.append("MAX_TRADE_NOTIONAL_MISSING")
    if max_total_exposure <= 0.0:
        blockers.append("MAX_TOTAL_EXPOSURE_MISSING")
    if max_daily_loss <= 0.0:
        blockers.append("MAX_DAILY_LOSS_MISSING")
    if max_daily_trades <= 0:
        blockers.append("MAX_DAILY_TRADES_MISSING")
    if max_open_positions <= 0:
        blockers.append("MAX_OPEN_POSITIONS_MISSING")
    if max_contracts_per_trade <= 0:
        blockers.append("MAX_CONTRACTS_PER_TRADE_MISSING")
    if min_contracts_per_trade <= 0:
        blockers.append("MIN_CONTRACTS_PER_TRADE_INVALID")
    if available_cash <= 0.0:
        blockers.append("AVAILABLE_CASH_MISSING")

    if _bool(ledger.get("risk_halt_active"), default=False):
        blockers.append("RISK_HALT_ACTIVE")

    daily_realized_pnl = _as_float(ledger.get("daily_realized_pnl"), default=0.0) or 0.0
    daily_trade_count = _as_int(ledger.get("daily_trade_count"), default=0) or 0
    open_position_count = _as_int(ledger.get("open_position_count"), default=0) or 0
    current_exposure = _as_float(ledger.get("current_exposure"), default=0.0) or 0.0

    if daily_realized_pnl <= -abs(max_daily_loss) and max_daily_loss > 0.0:
        blockers.append("DAILY_LOSS_LIMIT_REACHED")
    if daily_trade_count >= max_daily_trades and max_daily_trades > 0:
        blockers.append("DAILY_TRADE_LIMIT_REACHED")
    if open_position_count >= max_open_positions and max_open_positions > 0:
        blockers.append("MAX_OPEN_POSITIONS_REACHED")
    if _contains(ledger.get("open_instrument_tokens"), instrument_token) or _contains(ledger.get("open_tradingsymbols"), tradingsymbol):
        blockers.append("DUPLICATE_OPEN_CONTRACT")

    quantity = 0
    estimated_notional = 0.0
    risk_per_unit: float | None = None
    max_loss_amount: float | None = None

    if ask is not None and ask > 0.0 and max_trade_notional > 0.0 and max_contracts_per_trade > 0:
        by_notional = int(math.floor(max_trade_notional / ask))
        quantity = max(0, min(max_contracts_per_trade, by_notional))
        if quantity < min_contracts_per_trade:
            quantity = 0
            blockers.append("RISK_SIZE_BELOW_MIN_CONTRACTS")
        estimated_notional = round(float(quantity) * float(ask), 6)
        risk_per_unit = round(float(ask) * max(0.0, risk_per_trade_pct) / 100.0, 6)
        max_loss_amount = round(float(quantity) * float(risk_per_unit), 6)
    else:
        blockers.append("RISK_SIZE_UNAVAILABLE")

    if quantity <= 0:
        blockers.append("RISK_SIZE_ZERO")
    if estimated_notional > available_cash and available_cash > 0.0:
        blockers.append("INSUFFICIENT_AVAILABLE_CASH")
    if current_exposure + estimated_notional > max_total_exposure and max_total_exposure > 0.0:
        blockers.append("MAX_TOTAL_EXPOSURE_EXCEEDED")
    if max_loss_amount is not None and max_loss_amount > max_daily_loss and max_daily_loss > 0.0:
        blockers.append("TRADE_RISK_EXCEEDS_DAILY_LOSS_LIMIT")

    normalized_blockers = _dedupe(blockers)
    normalized_warnings = _dedupe(warnings)
    approved = not normalized_blockers

    if approved:
        state = RISK_APPROVED
        reasons.append("paper_intent_passed_risk_decision")
    else:
        state = RISK_BLOCKED
        reasons.append("paper_intent_failed_risk_decision")

    return RiskDecision(
        schema_version=RISK_DECISION_SCHEMA_VERSION,
        state=state,
        read_only=True,
        is_order_action=False,
        append=False,
        allowed_for_paper_order=approved,
        allowed_for_live_execution=False,
        paper_intent_id=str(intent.get("paper_intent_id")) if intent and intent.get("paper_intent_id") else None,
        symbol=str(intent.get("symbol")) if intent and intent.get("symbol") else None,
        direction=str(intent.get("direction")) if intent and intent.get("direction") else None,
        instrument_token=instrument_token,
        tradingsymbol=tradingsymbol or None,
        quantity=int(quantity),
        entry_price=round(float(ask), 6) if ask is not None else None,
        estimated_notional=round(float(estimated_notional), 6),
        max_loss_amount=max_loss_amount,
        risk_per_unit=risk_per_unit,
        blockers=normalized_blockers,
        warnings=normalized_warnings,
        reasons=tuple(sorted({reason for reason in reasons if reason})),
        metadata={
            "risk_decision": "risk_decision_v1",
            "scope": "read_only_no_order_creation_no_ledger_mutation",
            "sizing_model": "max_trade_notional_capped_by_contract_limit",
            "requires_paper_intent_ready": True,
        },
    )


__all__ = [
    "RISK_APPROVED",
    "RISK_BLOCKED",
    "RISK_DECISION_SCHEMA_VERSION",
    "RiskDecision",
    "build_risk_decision",
]
