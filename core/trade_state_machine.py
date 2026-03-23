from __future__ import annotations

from dataclasses import is_dataclass, replace
from datetime import datetime, timezone
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


class TradeLifecycleState(str, Enum):
    IDEA_CREATED = "idea_created"
    SCORED = "scored"
    RANKED = "ranked"
    ADVISORY = "advisory"
    EXECUTION_PENDING = "execution_pending"
    PARTIALLY_FILLED = "partially_filled"
    ACTIVE = "active"
    EXIT_PENDING = "exit_pending"
    CLOSED = "closed"
    RECONCILED = "reconciled"

    @classmethod
    def coerce(cls, value: Any) -> "TradeLifecycleState":
        if isinstance(value, cls):
            return value
        text = str(value or "").strip().lower()
        if not text:
            return cls.IDEA_CREATED
        try:
            return cls(text)
        except Exception as exc:
            raise ValueError(f"invalid_trade_lifecycle_state:{value}") from exc


TRADE_LIFECYCLE_STATES = tuple(state.value for state in TradeLifecycleState)

ALLOWED_TRANSITIONS: dict[TradeStateV1, set[TradeStateV1]] = {
    TradeStateV1.NEW: {TradeStateV1.CANDIDATE, TradeStateV1.REJECTED, TradeStateV1.CANCELLED},
    TradeStateV1.CANDIDATE: {TradeStateV1.APPROVED, TradeStateV1.REJECTED, TradeStateV1.CANCELLED},
    TradeStateV1.APPROVED: {TradeStateV1.SUBMITTED, TradeStateV1.REJECTED, TradeStateV1.CANCELLED},
    TradeStateV1.SUBMITTED: {TradeStateV1.FILLED, TradeStateV1.REJECTED, TradeStateV1.CANCELLED},
    TradeStateV1.FILLED: set(),
    TradeStateV1.REJECTED: set(),
    TradeStateV1.CANCELLED: set(),
}

ALLOWED_LIFECYCLE_TRANSITIONS: dict[TradeLifecycleState, set[TradeLifecycleState]] = {
    TradeLifecycleState.IDEA_CREATED: {TradeLifecycleState.SCORED, TradeLifecycleState.ADVISORY, TradeLifecycleState.CLOSED},
    TradeLifecycleState.SCORED: {
        TradeLifecycleState.RANKED,
        TradeLifecycleState.ADVISORY,
        TradeLifecycleState.EXECUTION_PENDING,
        TradeLifecycleState.CLOSED,
    },
    TradeLifecycleState.RANKED: {
        TradeLifecycleState.ADVISORY,
        TradeLifecycleState.EXECUTION_PENDING,
        TradeLifecycleState.CLOSED,
    },
    TradeLifecycleState.ADVISORY: {
        TradeLifecycleState.EXECUTION_PENDING,
        TradeLifecycleState.CLOSED,
    },
    TradeLifecycleState.EXECUTION_PENDING: {
        TradeLifecycleState.PARTIALLY_FILLED,
        TradeLifecycleState.ACTIVE,
        TradeLifecycleState.CLOSED,
    },
    TradeLifecycleState.PARTIALLY_FILLED: {
        TradeLifecycleState.ACTIVE,
        TradeLifecycleState.EXIT_PENDING,
        TradeLifecycleState.CLOSED,
    },
    TradeLifecycleState.ACTIVE: {
        TradeLifecycleState.EXIT_PENDING,
        TradeLifecycleState.CLOSED,
    },
    TradeLifecycleState.EXIT_PENDING: {
        TradeLifecycleState.CLOSED,
    },
    TradeLifecycleState.CLOSED: {
        TradeLifecycleState.RECONCILED,
    },
    TradeLifecycleState.RECONCILED: set(),
}

_TERMINAL_LIFECYCLE_STATES = {TradeLifecycleState.RECONCILED}
_LEGACY_TO_LIFECYCLE = {
    TradeStateV1.NEW: TradeLifecycleState.IDEA_CREATED,
    TradeStateV1.CANDIDATE: TradeLifecycleState.SCORED,
    TradeStateV1.APPROVED: TradeLifecycleState.EXECUTION_PENDING,
    TradeStateV1.SUBMITTED: TradeLifecycleState.EXECUTION_PENDING,
    TradeStateV1.FILLED: TradeLifecycleState.ACTIVE,
    TradeStateV1.REJECTED: TradeLifecycleState.CLOSED,
    TradeStateV1.CANCELLED: TradeLifecycleState.CLOSED,
}
_LIFECYCLE_TO_LEGACY = {
    TradeLifecycleState.IDEA_CREATED: TradeStateV1.NEW,
    TradeLifecycleState.SCORED: TradeStateV1.CANDIDATE,
    TradeLifecycleState.RANKED: TradeStateV1.CANDIDATE,
    TradeLifecycleState.ADVISORY: TradeStateV1.CANDIDATE,
    TradeLifecycleState.EXECUTION_PENDING: TradeStateV1.APPROVED,
    TradeLifecycleState.PARTIALLY_FILLED: TradeStateV1.SUBMITTED,
    TradeLifecycleState.ACTIVE: TradeStateV1.FILLED,
    TradeLifecycleState.EXIT_PENDING: TradeStateV1.FILLED,
    TradeLifecycleState.CLOSED: TradeStateV1.FILLED,
    TradeLifecycleState.RECONCILED: TradeStateV1.FILLED,
}


class TradeStateTransitionError(RuntimeError):
    def __init__(self, current_state: TradeStateV1, new_state: TradeStateV1):
        self.current_state = current_state
        self.new_state = new_state
        super().__init__(f"invalid_trade_transition:{current_state.value}->{new_state.value}")


class TradeLifecycleTransitionError(RuntimeError):
    def __init__(
        self,
        current_state: TradeLifecycleState,
        new_state: TradeLifecycleState,
        reason: str | None = None,
    ):
        self.current_state = current_state
        self.new_state = new_state
        self.reason = str(reason or "").strip() or None
        detail = f"invalid_trade_lifecycle_transition:{current_state.value}->{new_state.value}"
        if self.reason:
            detail = f"{detail} reason={self.reason}"
        super().__init__(detail)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _text(value: Any, *, upper: bool = False, lower: bool = False) -> str:
    raw = str(value or "").strip()
    if upper:
        return raw.upper()
    if lower:
        return raw.lower()
    return raw


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return text not in {"", "None", "null"}


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value, lower=True) in {"1", "true", "yes", "y", "on"}


def _normalize_reason(reason: Any) -> str | None:
    text = _text(reason)
    return text or None


def _coerce_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    history: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        state_text = _text(item.get("state"), lower=True)
        try:
            state = TradeLifecycleState.coerce(state_text)
        except Exception:
            continue
        history.append(
            {
                "state": state.value,
                "reason": _normalize_reason(item.get("reason")),
                "timestamp": _text(item.get("timestamp")) or None,
            }
        )
    return history


def _has_legacy_state_fields(trade: Any) -> bool:
    if isinstance(trade, dict):
        return any(key in trade for key in ("trade_state_v1", "trade_status", "status", "state"))
    return any(hasattr(trade, key) for key in ("trade_state_v1", "trade_status", "status", "state"))


def _set_fields(trade: Any, updates: dict[str, Any]) -> Any:
    if isinstance(trade, dict):
        out = dict(trade)
        out.update(updates)
        return out
    if is_dataclass(trade):
        dataclass_fields = getattr(type(trade), "__dataclass_fields__", {})
        allowed = {key: value for key, value in updates.items() if key in dataclass_fields}
        if not allowed:
            return trade
        return replace(trade, **allowed)
    for key, value in updates.items():
        try:
            setattr(trade, key, value)
        except Exception:
            continue
    return trade


def _infer_current_state(trade: Any) -> TradeStateV1:
    for key in ("trade_state_v1", "trade_status", "status", "state"):
        value = _get_value(trade, key)
        if value is not None and str(value).strip():
            return TradeStateV1.coerce(value)
    return TradeStateV1.NEW


def _validate_approved_preconditions(trade: Any) -> None:
    expected_entry = _as_float(_get_value(trade, "expected_entry"))
    snapshot_id = _text(_get_value(trade, "snapshot_id"))
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


def infer_trade_lifecycle_state(trade: Any) -> TradeLifecycleState:
    explicit = _get_value(trade, "trade_lifecycle_state")
    if _has_value(explicit):
        return TradeLifecycleState.coerce(explicit)

    if _is_truthy(_get_value(trade, "reconciled")) or _has_value(_get_value(trade, "reconciled_at")):
        return TradeLifecycleState.RECONCILED
    if _text(_get_value(trade, "reconciliation_status"), upper=True) == "RECONCILED":
        return TradeLifecycleState.RECONCILED

    if any(_has_value(_get_value(trade, key)) for key in ("exit_price", "exit_time", "actual", "outcome_label")):
        return TradeLifecycleState.CLOSED

    status_upper = _text(_get_value(trade, "status"), upper=True)
    if status_upper == "EXIT_PENDING" or _text(_get_value(trade, "exit_order_status"), upper=True) in {"PENDING", "OPEN"}:
        return TradeLifecycleState.EXIT_PENDING

    filled_qty = _as_float(_get_value(trade, "filled_qty"))
    if filled_qty is None:
        filled_qty = _as_float(_get_value(trade, "filled_quantity"))
    total_qty = _as_float(_get_value(trade, "qty"))
    if total_qty is None:
        total_qty = _as_float(_get_value(trade, "qty_units"))
    if filled_qty is not None and total_qty is not None and 0.0 < filled_qty < total_qty:
        return TradeLifecycleState.PARTIALLY_FILLED

    if status_upper in {"ACTIVE", "OPEN", "FILLED"}:
        return TradeLifecycleState.ACTIVE
    if any(_has_value(_get_value(trade, key)) for key in ("fill_price", "fill_entry", "activated_ts")):
        return TradeLifecycleState.ACTIVE

    legacy_state = None
    try:
        legacy_state = TradeStateV1.coerce(_get_value(trade, "trade_state_v1"))
    except Exception:
        legacy_state = None
    if legacy_state in {TradeStateV1.APPROVED, TradeStateV1.SUBMITTED}:
        return TradeLifecycleState.EXECUTION_PENDING
    if legacy_state == TradeStateV1.FILLED:
        return TradeLifecycleState.ACTIVE
    if legacy_state in {TradeStateV1.REJECTED, TradeStateV1.CANCELLED}:
        return TradeLifecycleState.CLOSED

    final_action = _text(_get_value(trade, "final_action"), upper=True)
    permission = _text(_get_value(trade, "permission"), upper=True)
    readiness = _text(_get_value(trade, "readiness"), upper=True)
    execution_status = _text(_get_value(trade, "execution_status"), lower=True)
    if final_action == "EXECUTE" or permission == "EXECUTE" or execution_status == "executable":
        return TradeLifecycleState.EXECUTION_PENDING
    if final_action in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCK"}:
        return TradeLifecycleState.ADVISORY
    if readiness in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCKED"} or execution_status in {"advisory_only", "queue_only", "blocked"}:
        return TradeLifecycleState.ADVISORY

    execution_entry = _as_float(_get_value(trade, "execution_entry"))
    display_entry = _as_float(_get_value(trade, "display_entry"))
    if execution_entry is None and display_entry is not None:
        return TradeLifecycleState.ADVISORY

    if _get_value(trade, "opportunity_rank") is not None:
        return TradeLifecycleState.RANKED
    if any(_get_value(trade, key) is not None for key in ("trade_score", "opportunity_score", "confidence", "builder_confidence")):
        return TradeLifecycleState.SCORED

    if legacy_state == TradeStateV1.CANDIDATE:
        return TradeLifecycleState.SCORED
    return TradeLifecycleState.IDEA_CREATED


def _legacy_alias_for_lifecycle(state: TradeLifecycleState) -> TradeStateV1:
    return _LIFECYCLE_TO_LEGACY[state]


def _history_event(
    state: TradeLifecycleState,
    *,
    reason: str | None,
    timestamp: str,
) -> dict[str, Any]:
    return {
        "state": state.value,
        "reason": reason,
        "timestamp": timestamp,
    }


def build_trade_lifecycle_snapshot(
    trade: Any,
    *,
    state: TradeLifecycleState | str | None = None,
    reason: str | None = None,
    timestamp: str | None = None,
    include_legacy_alias: bool | None = None,
    force_history: bool = False,
) -> dict[str, Any]:
    explicit_state = _text(_get_value(trade, "trade_lifecycle_state"), lower=True)
    existing_reason = _normalize_reason(_get_value(trade, "trade_lifecycle_reason"))
    existing_ts = _text(_get_value(trade, "trade_lifecycle_ts")) or None
    history = _coerce_history(_get_value(trade, "trade_lifecycle_history"))

    if state is not None:
        resolved_state = TradeLifecycleState.coerce(state)
    elif explicit_state:
        resolved_state = TradeLifecycleState.coerce(explicit_state)
    else:
        resolved_state = infer_trade_lifecycle_state(trade)

    resolved_reason = _normalize_reason(reason) or existing_reason or "lifecycle_initialized"
    resolved_ts = _text(timestamp) or existing_ts or _utc_now_iso()

    last_event = history[-1] if history else None
    event = _history_event(resolved_state, reason=resolved_reason, timestamp=resolved_ts)
    if force_history:
        if not history or last_event != event:
            history = [*history, event]
    elif not history:
        history = [*history, event]

    snapshot = {
        "trade_lifecycle_state": resolved_state.value,
        "trade_lifecycle_reason": resolved_reason,
        "trade_lifecycle_ts": resolved_ts,
        "trade_lifecycle_history": history,
    }
    if include_legacy_alias is None:
        include_legacy_alias = _has_legacy_state_fields(trade)
    if include_legacy_alias:
        snapshot["trade_state_v1"] = _legacy_alias_for_lifecycle(resolved_state).value
    return snapshot


def ensure_trade_lifecycle(
    trade: Any,
    *,
    reason: str | None = None,
    timestamp: str | None = None,
) -> Any:
    explicit_state = _has_value(_get_value(trade, "trade_lifecycle_state"))
    history = _coerce_history(_get_value(trade, "trade_lifecycle_history"))
    snapshot = build_trade_lifecycle_snapshot(
        trade,
        reason=reason,
        timestamp=timestamp,
        force_history=(not explicit_state) or (not history),
    )
    return _set_fields(trade, snapshot)


def rehydrate_trade_lifecycle(
    trade: Any,
    *,
    reason: str | None = "restart_rehydrated",
    timestamp: str | None = None,
) -> Any:
    inferred_state = infer_trade_lifecycle_state(trade)
    snapshot = build_trade_lifecycle_snapshot(
        trade,
        state=inferred_state,
        reason=reason,
        timestamp=timestamp,
        force_history=not _coerce_history(_get_value(trade, "trade_lifecycle_history")),
    )
    return _set_fields(trade, snapshot)


def record_trade_lifecycle_observation(
    trade: Any,
    observed_state: TradeLifecycleState | str,
    *,
    reason: str | None,
    timestamp: str | None = None,
) -> Any:
    snapshot = build_trade_lifecycle_snapshot(
        trade,
        state=TradeLifecycleState.coerce(observed_state),
        reason=reason,
        timestamp=timestamp,
        force_history=True,
    )
    return _set_fields(trade, snapshot)


def transition_trade_lifecycle(
    trade: Any,
    new_state: TradeLifecycleState | str,
    *,
    reason: str | None,
    timestamp: str | None = None,
) -> Any:
    ensured = ensure_trade_lifecycle(trade, reason="lifecycle_initialized", timestamp=timestamp)
    current_state = TradeLifecycleState.coerce(_get_value(ensured, "trade_lifecycle_state"))
    target_state = TradeLifecycleState.coerce(new_state)

    if current_state != target_state:
        allowed = ALLOWED_LIFECYCLE_TRANSITIONS.get(current_state, set())
        if current_state in _TERMINAL_LIFECYCLE_STATES and target_state != current_state:
            raise TradeLifecycleTransitionError(current_state, target_state, reason=reason)
        if target_state not in allowed:
            raise TradeLifecycleTransitionError(current_state, target_state, reason=reason)

    snapshot = build_trade_lifecycle_snapshot(
        ensured,
        state=target_state,
        reason=reason,
        timestamp=timestamp,
        force_history=True,
    )
    return _set_fields(ensured, snapshot)


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
        updated = _set_state(trade, target_state)
        return record_trade_lifecycle_observation(
            updated,
            _LEGACY_TO_LIFECYCLE[target_state],
            reason=f"legacy_state:{target_state.value.lower()}",
        )

    allowed = ALLOWED_TRANSITIONS.get(current_state, set())
    if target_state not in allowed:
        raise TradeStateTransitionError(current_state, target_state)

    if target_state == TradeStateV1.APPROVED:
        _validate_approved_preconditions(trade)

    updated = _set_state(trade, target_state)
    return record_trade_lifecycle_observation(
        updated,
        _LEGACY_TO_LIFECYCLE[target_state],
        reason=f"legacy_state:{target_state.value.lower()}",
    )
