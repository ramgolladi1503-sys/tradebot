"""Strict paper order state machine.

This module models paper-order lifecycle transitions only. It does not call
brokers, simulate fills/slippage, mutate ledgers, write files, or wire runtime
execution. Fill pricing and realistic slippage belong to later PRs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping

PAPER_ORDER_STATE_SCHEMA_VERSION = 1

CREATED = "CREATED"
SUBMITTED = "SUBMITTED"
PARTIALLY_FILLED = "PARTIALLY_FILLED"
FILLED = "FILLED"
CANCEL_REQUESTED = "CANCEL_REQUESTED"
CANCELLED = "CANCELLED"
REJECTED = "REJECTED"
EXPIRED = "EXPIRED"

TERMINAL_STATES: frozenset[str] = frozenset({FILLED, CANCELLED, REJECTED, EXPIRED})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    CREATED: frozenset({SUBMITTED, REJECTED, EXPIRED}),
    SUBMITTED: frozenset({PARTIALLY_FILLED, FILLED, CANCEL_REQUESTED, REJECTED, EXPIRED}),
    PARTIALLY_FILLED: frozenset({FILLED, CANCEL_REQUESTED, REJECTED, EXPIRED}),
    CANCEL_REQUESTED: frozenset({CANCELLED, PARTIALLY_FILLED, FILLED, REJECTED, EXPIRED}),
    FILLED: frozenset(),
    CANCELLED: frozenset(),
    REJECTED: frozenset(),
    EXPIRED: frozenset(),
}


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


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    return out if out == out else default


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


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


def _transition_key(from_state: str, to_state: str, event_id: str | None) -> str:
    suffix = str(event_id or "").strip() or "no_event_id"
    return f"{from_state}->{to_state}:{suffix}"


class PaperOrderStateError(ValueError):
    """Raised when a paper-order lifecycle operation is invalid."""


@dataclass(frozen=True)
class PaperOrderTransition:
    from_state: str
    to_state: str
    reason: str
    event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PaperOrderRecord:
    schema_version: int
    paper_order_id: str
    paper_intent_id: str
    state: str
    symbol: str
    direction: str
    instrument_token: int
    tradingsymbol: str
    quantity: int
    entry_price: float
    estimated_notional: float
    filled_quantity: int
    remaining_quantity: int
    broker_order_action: bool
    live_order_action: bool
    transitions: tuple[PaperOrderTransition, ...]
    transition_keys: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["transitions"] = [transition.to_dict() for transition in self.transitions]
        payload["transition_keys"] = list(self.transition_keys)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["metadata"] = dict(self.metadata)
        return payload


def create_paper_order_record(paper_decision: Any, *, paper_order_id: str | None = None) -> PaperOrderRecord:
    """Create an in-memory paper order record from an approved paper decision."""

    decision = _to_mapping(paper_decision)
    if decision is None:
        raise PaperOrderStateError("paper_decision_missing")
    blockers = list(_list_of_strings(decision.get("blockers")))
    if str(decision.get("state") or "") != "PAPER_DECISION_APPROVED":
        blockers.append("PAPER_DECISION_NOT_APPROVED")
    if not _bool(decision.get("allowed_for_paper_order"), default=False):
        blockers.append("PAPER_ORDER_NOT_ALLOWED")
    if _bool(decision.get("allowed_for_live_execution"), default=False):
        blockers.append("LIVE_EXECUTION_PERMISSION_UNEXPECTED")
    if _bool(decision.get("is_order_action"), default=False):
        blockers.append("DECISION_CONTAINS_ORDER_ACTION")
    if _bool(decision.get("append"), default=False):
        blockers.append("DECISION_APPEND_TRUE")

    paper_intent_id = _first_text(decision.get("paper_intent_id"))
    symbol = _first_text(decision.get("symbol"))
    direction = _first_text(decision.get("direction"))
    tradingsymbol = _first_text(decision.get("tradingsymbol"))
    instrument_token = _as_int(decision.get("instrument_token"), default=0)
    quantity = _as_int(decision.get("quantity"), default=0)
    entry_price = _as_float(decision.get("entry_price"), default=0.0)
    estimated_notional = _as_float(decision.get("estimated_notional"), default=0.0)

    if paper_intent_id is None:
        blockers.append("PAPER_INTENT_ID_MISSING")
    if symbol is None:
        blockers.append("SYMBOL_MISSING")
    if direction is None:
        blockers.append("DIRECTION_MISSING")
    if tradingsymbol is None:
        blockers.append("TRADINGSYMBOL_MISSING")
    if instrument_token <= 0:
        blockers.append("INSTRUMENT_TOKEN_MISSING")
    if quantity <= 0:
        blockers.append("QUANTITY_MISSING")
    if entry_price <= 0.0:
        blockers.append("ENTRY_PRICE_MISSING")
    if estimated_notional <= 0.0:
        blockers.append("ESTIMATED_NOTIONAL_MISSING")

    normalized_blockers = _dedupe(blockers)
    if normalized_blockers:
        raise PaperOrderStateError("paper_order_record_preconditions_failed:" + ",".join(normalized_blockers))

    order_id = paper_order_id or f"paper-{paper_intent_id}"
    initial_transition = PaperOrderTransition(
        from_state="NONE",
        to_state=CREATED,
        reason="paper_order_record_created",
        event_id="create",
    )
    transition_key = _transition_key("NONE", CREATED, "create")
    return PaperOrderRecord(
        schema_version=PAPER_ORDER_STATE_SCHEMA_VERSION,
        paper_order_id=order_id,
        paper_intent_id=str(paper_intent_id),
        state=CREATED,
        symbol=str(symbol),
        direction=str(direction),
        instrument_token=int(instrument_token),
        tradingsymbol=str(tradingsymbol),
        quantity=int(quantity),
        entry_price=round(float(entry_price), 6),
        estimated_notional=round(float(estimated_notional), 6),
        filled_quantity=0,
        remaining_quantity=int(quantity),
        broker_order_action=False,
        live_order_action=False,
        transitions=(initial_transition,),
        transition_keys=(transition_key,),
        blockers=(),
        warnings=(),
        metadata={
            "state_machine": "paper_order_state_machine_v1",
            "scope": "in_memory_no_broker_calls_no_fill_model_no_ledger_mutation",
            "terminal_states": sorted(TERMINAL_STATES),
        },
    )


def transition_paper_order(
    order: PaperOrderRecord,
    to_state: str,
    *,
    reason: str,
    event_id: str | None = None,
    filled_quantity_delta: int = 0,
) -> PaperOrderRecord:
    """Return a new record after applying one validated state transition."""

    if not isinstance(order, PaperOrderRecord):
        raise PaperOrderStateError("paper_order_record_invalid")
    target = str(to_state or "").strip().upper()
    if target not in ALLOWED_TRANSITIONS:
        raise PaperOrderStateError(f"unknown_paper_order_state:{target}")
    if order.state in TERMINAL_STATES:
        raise PaperOrderStateError(f"terminal_state_transition_rejected:{order.state}->{target}")
    if target == order.state:
        raise PaperOrderStateError(f"duplicate_state_transition_rejected:{order.state}->{target}")
    if target not in ALLOWED_TRANSITIONS.get(order.state, frozenset()):
        raise PaperOrderStateError(f"invalid_state_transition:{order.state}->{target}")

    key = _transition_key(order.state, target, event_id)
    if key in set(order.transition_keys):
        raise PaperOrderStateError(f"duplicate_transition_event_rejected:{key}")

    delta = _as_int(filled_quantity_delta, default=0)
    if delta < 0:
        raise PaperOrderStateError("filled_quantity_delta_negative")
    if target in {PARTIALLY_FILLED, FILLED} and delta <= 0:
        raise PaperOrderStateError("fill_transition_requires_positive_delta")
    if target not in {PARTIALLY_FILLED, FILLED} and delta != 0:
        raise PaperOrderStateError("non_fill_transition_rejects_fill_delta")

    next_filled = int(order.filled_quantity) + int(delta)
    if next_filled > int(order.quantity):
        raise PaperOrderStateError("filled_quantity_exceeds_order_quantity")
    if target == PARTIALLY_FILLED and next_filled >= int(order.quantity):
        raise PaperOrderStateError("partial_fill_cannot_complete_order")
    if target == FILLED and next_filled != int(order.quantity):
        raise PaperOrderStateError("filled_state_requires_full_quantity")

    next_remaining = int(order.quantity) - int(next_filled)
    transition = PaperOrderTransition(
        from_state=order.state,
        to_state=target,
        reason=str(reason or "").strip() or "unspecified",
        event_id=str(event_id).strip() if event_id not in (None, "") else None,
    )
    return replace(
        order,
        state=target,
        filled_quantity=next_filled,
        remaining_quantity=next_remaining,
        transitions=tuple(order.transitions) + (transition,),
        transition_keys=tuple(order.transition_keys) + (key,),
    )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "CANCELLED",
    "CANCEL_REQUESTED",
    "CREATED",
    "EXPIRED",
    "FILLED",
    "PAPER_ORDER_STATE_SCHEMA_VERSION",
    "PARTIALLY_FILLED",
    "REJECTED",
    "SUBMITTED",
    "TERMINAL_STATES",
    "PaperOrderRecord",
    "PaperOrderStateError",
    "PaperOrderTransition",
    "create_paper_order_record",
    "transition_paper_order",
]
