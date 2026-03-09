from __future__ import annotations

from dataclasses import is_dataclass, replace
from enum import Enum
from typing import Any

from core.entry_semantics import derive_expected_entry, derive_fill_entry, resolve_entry_price


class TradeStateV1(str, Enum):
    NEW = "NEW"
    CANDIDATE = "CANDIDATE"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

    @classmethod
    def coerce(cls, value: Any) -> "TradeStateV1":
        if isinstance(value, cls):
            return value
        text = str(value or "").strip().upper()
        if not text:
            return cls.NEW
        try:
            return cls(text)
        except Exception as exc:
            raise ValueError(f"invalid_trade_state:{value}") from exc


ALLOWED_TRANSITIONS: dict[TradeStateV1, set[TradeStateV1]] = {
    TradeStateV1.NEW: {TradeStateV1.CANDIDATE, TradeStateV1.REJECTED, TradeStateV1.CANCELLED},
    TradeStateV1.CANDIDATE: {TradeStateV1.APPROVED, TradeStateV1.REJECTED, TradeStateV1.CANCELLED},
    TradeStateV1.APPROVED: {TradeStateV1.SUBMITTED, TradeStateV1.REJECTED, TradeStateV1.CANCELLED},
    TradeStateV1.SUBMITTED: {TradeStateV1.FILLED, TradeStateV1.REJECTED, TradeStateV1.CANCELLED},
    TradeStateV1.FILLED: set(),
    TradeStateV1.REJECTED: set(),
    TradeStateV1.CANCELLED: set(),
}


class TradeStateTransitionError(RuntimeError):
    def __init__(self, current_state: TradeStateV1, new_state: TradeStateV1):
        self.current_state = current_state
        self.new_state = new_state
        super().__init__(f"invalid_trade_transition:{current_state.value}->{new_state.value}")


def _get_value(trade: Any, key: str) -> Any:
    if isinstance(trade, dict):
        return trade.get(key)
    return getattr(trade, key, None)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _infer_current_state(trade: Any) -> TradeStateV1:
    # Preserve backward compatibility with existing payloads:
    # prefer explicit v1 field, then existing status-like fields.
    for key in ("trade_state_v1", "trade_status", "status", "state"):
        value = _get_value(trade, key)
        if value is not None and str(value).strip():
            return TradeStateV1.coerce(value)
    return TradeStateV1.NEW


def _validate_approved_preconditions(trade: Any) -> None:
    expected_entry = _as_float(_get_value(trade, "expected_entry"))
    snapshot_id = str(_get_value(trade, "snapshot_id") or "").strip()
    if expected_entry is None or expected_entry <= 0:
        raise ValueError("approved_requires_expected_entry")
    if not snapshot_id:
        raise ValueError("approved_requires_snapshot_id")


def _set_state(trade: Any, new_state: TradeStateV1) -> Any:
    if isinstance(trade, dict):
        out = dict(trade)
        out["trade_state_v1"] = new_state.value
        return out

    if is_dataclass(trade):
        # Keep existing state fields untouched unless trade_state_v1 is modeled.
        # If not modeled, fall back to trade_status/status when present.
        if hasattr(trade, "trade_state_v1"):
            return replace(trade, trade_state_v1=new_state.value)
        if hasattr(trade, "trade_status"):
            return replace(trade, trade_status=new_state.value)
        if hasattr(trade, "status"):
            return replace(trade, status=new_state.value)
        return trade

    try:
        setattr(trade, "trade_state_v1", new_state.value)
    except Exception:
        pass
    return trade


def transition_trade_state(trade: Any, new_state: TradeStateV1 | str) -> Any:
    """
    Transition a trade into TradeStateV1 while preserving existing trade schemas.

    Rules:
    - Transition must be in ALLOWED_TRANSITIONS.
    - APPROVED requires expected_entry and snapshot_id.
    - Same-state transitions are no-op and allowed.
    """
    if isinstance(trade, dict):
        trade = dict(trade)
        target_state_pre = TradeStateV1.coerce(new_state)
        if target_state_pre == TradeStateV1.APPROVED and _as_float(trade.get("expected_entry")) is None:
            derived_expected = derive_expected_entry(trade)
            if derived_expected is not None:
                trade["expected_entry"] = float(derived_expected)
        if target_state_pre == TradeStateV1.FILLED and _as_float(trade.get("fill_entry")) is None:
            derived_fill = derive_fill_entry(trade)
            if derived_fill is not None:
                trade["fill_entry"] = float(derived_fill)
        resolved_entry_price = resolve_entry_price(trade)
        if resolved_entry_price is not None:
            trade["entry_price"] = float(resolved_entry_price)

    current_state = _infer_current_state(trade)
    target_state = TradeStateV1.coerce(new_state)

    if current_state == target_state:
        return _set_state(trade, target_state)

    allowed = ALLOWED_TRANSITIONS.get(current_state, set())
    if target_state not in allowed:
        raise TradeStateTransitionError(current_state, target_state)

    if target_state == TradeStateV1.APPROVED:
        _validate_approved_preconditions(trade)

    return _set_state(trade, target_state)
