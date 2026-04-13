from __future__ import annotations

from dataclasses import dataclass, field
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

    status: str = "OPEN"
    tp1_done: bool = False
    breakeven_done: bool = False

    remaining_qty: int = 0
    realized_qty: int = 0

    mfe_r: float = 0.0
    mae_r: float = 0.0

    telemetry: dict[str, Any] = field(default_factory=dict)


def _pnl_r(side: str, entry: float, stop: float, price: float) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    if side.upper() == "BUY":
        return (price - entry) / risk
    return (entry - price) / risk


def initialize_position_state(fill: dict[str, Any], candidate: dict[str, Any]) -> PositionState:
    qty = int(fill.get("qty") or candidate.get("qty") or 0)
    fill_price = float(fill.get("fill_price") or candidate.get("entry"))

    state = PositionState(
        trade_id=str(candidate.get("trade_id") or ""),
        symbol=str(candidate.get("symbol") or ""),
        side=str(candidate.get("side") or "BUY"),
        playbook=str(candidate.get("selected_playbook") or "none"),
        entry_price=float(candidate.get("entry") or fill_price),
        fill_price=fill_price,
        qty=qty,
        initial_stop=float(candidate.get("stop_loss")),
        current_stop=float(candidate.get("stop_loss")),
        target=float(candidate.get("target")),
        remaining_qty=qty,
    )

    return state


def update_position_state(state: PositionState, market: dict[str, Any]) -> PositionState:
    price = float(market.get("last_price") or state.fill_price)

    pnl_r = _pnl_r(state.side, state.fill_price, state.initial_stop, price)

    state.mfe_r = max(state.mfe_r, pnl_r)
    state.mae_r = min(state.mae_r, pnl_r)

    return state


def apply_exit_action(state: PositionState, action: dict[str, Any]) -> PositionState:
    action_name = str(action.get("action") or "HOLD").upper()

    if action_name == "PARTIAL_EXIT":
        if state.tp1_done and action.get("reason") == "tp1_hit":
            return state

        fraction = float(action.get("exit_fraction") or 0.0)
        exit_qty = int(state.qty * fraction)
        exit_qty = min(exit_qty, state.remaining_qty)

        if exit_qty > 0:
            state.realized_qty += exit_qty
            state.remaining_qty -= exit_qty

        if action.get("reason") == "tp1_hit":
            state.tp1_done = True

        state.status = "PARTIAL" if state.remaining_qty > 0 else "CLOSED"

    elif action_name == "MOVE_STOP":
        new_stop = action.get("new_stop")
        if new_stop is not None:
            state.current_stop = float(new_stop)
            state.breakeven_done = True

    elif action_name == "FULL_EXIT":
        state.remaining_qty = 0
        state.realized_qty = state.qty
        state.status = "CLOSED"

    return state
