from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PositionState:
    trade_id: str
    symbol: str
    side: str
    playbook: str
    entry_price: float
    fill_price: float
    qty: int
    initial_stop: float
    current_stop: float
    target: float
    opened_ts: float
    updated_ts: float
    status: str = "OPEN"  # OPEN, PARTIAL, BREAKEVEN, TRAILING, CLOSED
    tp1_done: bool = False
    breakeven_done: bool = False
    trailing_active: bool = False
    exit_reason: str | None = None
    realized_qty: int = 0
    remaining_qty: int = 0
    mfe_price: float | None = None
    mae_price: float | None = None
    mfe_r: float = 0.0
    mae_r: float = 0.0
    high_watermark: float | None = None
    low_watermark: float | None = None
    telemetry: dict[str, Any] = field(default_factory=dict)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "None"):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "", "None"):
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _normalize_side(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"SELL", "SHORT", "BUY_PUT", "PUT", "PE"}:
        return "SELL"
    return "BUY"


def _signed_pnl_r(side: str, entry: float, stop: float, current: float) -> float:
    risk = abs(float(entry) - float(stop))
    if risk <= 0.0:
        return 0.0
    if _normalize_side(side) == "BUY":
        return (float(current) - float(entry)) / risk
    return (float(entry) - float(current)) / risk


def initialize_position_state(fill: dict[str, Any], candidate: dict[str, Any], now_ts: float) -> PositionState:
    fill_data = dict(fill or {})
    candidate_data = dict(candidate or {})

    qty = _safe_int(fill_data.get("qty"), 0)
    if qty <= 0:
        qty = _safe_int(candidate_data.get("qty"), 0)
    if qty <= 0:
        qty = _safe_int(candidate_data.get("qty_units"), 0)
    if qty <= 0:
        qty = 1

    fill_price = _safe_float(
        fill_data.get("fill_price"),
        _safe_float(
            candidate_data.get("execution_entry"),
            _safe_float(candidate_data.get("entry"), 0.0),
        ),
    )
    fill_price = float(fill_price or 0.0)

    initial_stop = _safe_float(candidate_data.get("stop_loss"), 0.0)
    target = _safe_float(candidate_data.get("target"), 0.0)

    entry_price = _safe_float(candidate_data.get("entry"), fill_price)
    entry_price = float(entry_price or fill_price)
    initial_stop = float(initial_stop or 0.0)
    target = float(target or 0.0)

    side = _normalize_side(candidate_data.get("side"))
    if initial_stop <= 0.0:
        if side == "BUY":
            initial_stop = round(fill_price * 0.75, 3)
        else:
            initial_stop = round(fill_price * 1.25, 3)
    if target <= 0.0:
        if side == "BUY":
            target = round(fill_price * 1.35, 3)
        else:
            target = round(fill_price * 0.65, 3)

    return PositionState(
        trade_id=str(candidate_data.get("trade_id") or fill_data.get("trade_id") or ""),
        symbol=str(candidate_data.get("symbol") or ""),
        side=side,
        playbook=str(
            candidate_data.get("selected_playbook")
            or candidate_data.get("decision_playbook")
            or "none"
        ),
        entry_price=float(entry_price),
        fill_price=float(fill_price),
        qty=int(qty),
        initial_stop=float(initial_stop),
        current_stop=float(initial_stop),
        target=float(target),
        opened_ts=float(now_ts),
        updated_ts=float(now_ts),
        remaining_qty=int(qty),
        mfe_price=float(fill_price),
        mae_price=float(fill_price),
        high_watermark=float(fill_price),
        low_watermark=float(fill_price),
        telemetry={
            "setup_score": candidate_data.get("setup_score"),
            "trigger_score": candidate_data.get("trigger_score"),
            "entry_quality_score": candidate_data.get("entry_quality_score"),
            "execution_quality_score": candidate_data.get("execution_quality_score"),
        },
    )


def update_position_state(state: PositionState, market: dict[str, Any], now_ts: float) -> PositionState:
    last_price = _safe_float((market or {}).get("last_price"), state.fill_price)
    last_price = float(last_price or state.fill_price)

    state.updated_ts = float(now_ts)
    state.high_watermark = max(float(state.high_watermark or last_price), last_price)
    state.low_watermark = min(float(state.low_watermark or last_price), last_price)

    if _normalize_side(state.side) == "BUY":
        state.mfe_price = float(state.high_watermark)
        state.mae_price = float(state.low_watermark)
    else:
        state.mfe_price = float(state.low_watermark)
        state.mae_price = float(state.high_watermark)

    state.mfe_r = max(
        float(state.mfe_r),
        _signed_pnl_r(state.side, state.fill_price, state.initial_stop, float(state.mfe_price)),
    )
    state.mae_r = min(
        float(state.mae_r),
        _signed_pnl_r(state.side, state.fill_price, state.initial_stop, float(state.mae_price)),
    )

    state.telemetry["last_price"] = float(last_price)
    return state


def apply_exit_action(state: PositionState, action: dict[str, Any], now_ts: float) -> PositionState:
    action_data = dict(action or {})
    action_name = str(action_data.get("action") or "HOLD").strip().upper()
    reason = str(action_data.get("reason") or "").strip()

    state.updated_ts = float(now_ts)

    if action_name == "PARTIAL_EXIT":
        if state.tp1_done and reason == "tp1_hit":
            return state
        if state.remaining_qty <= 0:
            return state
        fraction = _safe_float(action_data.get("exit_fraction"), 0.0) or 0.0
        fraction = max(0.0, min(1.0, float(fraction)))
        exit_qty = max(0, min(state.remaining_qty, int(round(state.qty * fraction))))
        if exit_qty <= 0 and state.remaining_qty > 1:
            exit_qty = 1
        if exit_qty <= 0:
            return state
        state.realized_qty = int(state.realized_qty) + int(exit_qty)
        state.remaining_qty = max(0, int(state.remaining_qty) - int(exit_qty))
        if reason == "tp1_hit":
            state.tp1_done = True
        state.status = "PARTIAL" if state.remaining_qty > 0 else "CLOSED"

    elif action_name == "MOVE_STOP":
        new_stop = _safe_float(action_data.get("new_stop"))
        if new_stop is None:
            return state
        if state.breakeven_done and abs(float(state.current_stop) - float(new_stop)) <= 1e-9:
            return state
        state.current_stop = float(new_stop)
        state.breakeven_done = True
        state.status = "BREAKEVEN" if not state.trailing_active else "TRAILING"

    elif action_name == "FULL_EXIT":
        state.realized_qty = int(state.qty)
        state.remaining_qty = 0
        state.status = "CLOSED"

    if reason:
        state.exit_reason = reason

    return state


def position_state_to_dict(state: PositionState) -> dict[str, Any]:
    return asdict(state)


def position_state_from_dict(payload: dict[str, Any]) -> PositionState:
    data = dict(payload or {})
    return PositionState(
        trade_id=str(data.get("trade_id") or ""),
        symbol=str(data.get("symbol") or ""),
        side=str(data.get("side") or "BUY"),
        playbook=str(data.get("playbook") or "none"),
        entry_price=float(_safe_float(data.get("entry_price"), 0.0) or 0.0),
        fill_price=float(_safe_float(data.get("fill_price"), 0.0) or 0.0),
        qty=int(_safe_int(data.get("qty"), 0)),
        initial_stop=float(_safe_float(data.get("initial_stop"), 0.0) or 0.0),
        current_stop=float(_safe_float(data.get("current_stop"), 0.0) or 0.0),
        target=float(_safe_float(data.get("target"), 0.0) or 0.0),
        opened_ts=float(_safe_float(data.get("opened_ts"), 0.0) or 0.0),
        updated_ts=float(_safe_float(data.get("updated_ts"), 0.0) or 0.0),
        status=str(data.get("status") or "OPEN"),
        tp1_done=bool(data.get("tp1_done")),
        breakeven_done=bool(data.get("breakeven_done")),
        trailing_active=bool(data.get("trailing_active")),
        exit_reason=(str(data.get("exit_reason")) if data.get("exit_reason") is not None else None),
        realized_qty=int(_safe_int(data.get("realized_qty"), 0)),
        remaining_qty=int(_safe_int(data.get("remaining_qty"), 0)),
        mfe_price=_safe_float(data.get("mfe_price")),
        mae_price=_safe_float(data.get("mae_price")),
        mfe_r=float(_safe_float(data.get("mfe_r"), 0.0) or 0.0),
        mae_r=float(_safe_float(data.get("mae_r"), 0.0) or 0.0),
        high_watermark=_safe_float(data.get("high_watermark")),
        low_watermark=_safe_float(data.get("low_watermark")),
        telemetry=dict(data.get("telemetry") or {}),
    )
