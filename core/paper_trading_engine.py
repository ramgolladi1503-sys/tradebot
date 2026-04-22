from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.execution_model import simulate_fill


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


@dataclass
class PaperPosition:
    trade_id: str
    symbol: str
    option_type: str
    strategy_family: str
    qty: int
    entry_price: float
    entry_time: float
    stop_loss: float | None = None
    target: float | None = None
    mark_price: float | None = None
    exit_price: float | None = None
    exit_time: float | None = None
    status: str = "OPEN"
    fill_probability: float = 0.0
    expected_slippage_pct: float = 0.0
    realized_pnl: float = 0.0
    realized_pnl_pct: float = 0.0
    mfe: float = 0.0
    mae: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class PaperTradingSnapshot:
    open_positions: list[dict[str, Any]]
    closed_positions: list[dict[str, Any]]
    total_realized_pnl: float
    total_realized_pnl_pct: float
    win_rate: float
    total_trades: int


class PaperTradingEngine:
    def __init__(self) -> None:
        self._open: dict[str, PaperPosition] = {}
        self._closed: list[PaperPosition] = []

    def enter_position(self, candidate: dict[str, Any], now_ts: float) -> PaperPosition | None:
        simulation = simulate_fill(candidate)
        trade_id = str(candidate.get("trade_id") or candidate.get("tradingsymbol") or candidate.get("symbol") or f"paper-{int(now_ts)}")
        if not simulation.get("executable"):
            return None
        qty = int(candidate.get("qty") or candidate.get("qty_units") or 1)
        entry_price = float(simulation.get("simulated_fill_price") or candidate.get("entry_price") or 0.0)
        stop_loss = _safe_float(candidate.get("stop_loss"))
        target = _safe_float(candidate.get("target"))
        position = PaperPosition(
            trade_id=trade_id,
            symbol=str(candidate.get("symbol") or candidate.get("underlying") or "UNKNOWN"),
            option_type=str(candidate.get("option_type") or candidate.get("right") or "OPT"),
            strategy_family=str(candidate.get("strategy_family") or "unknown"),
            qty=max(1, qty),
            entry_price=entry_price,
            entry_time=float(now_ts),
            stop_loss=stop_loss,
            target=target,
            mark_price=entry_price,
            fill_probability=float(simulation.get("fill_probability") or 0.0),
            expected_slippage_pct=float(simulation.get("expected_slippage_pct") or 0.0),
            notes=["paper_entry"],
        )
        self._open[trade_id] = position
        return position

    def mark_position(self, trade_id: str, mark_price: float, now_ts: float) -> PaperPosition | None:
        position = self._open.get(str(trade_id))
        if position is None:
            return None
        price = float(mark_price)
        position.mark_price = price
        pnl = (price - position.entry_price) * position.qty
        position.mfe = max(position.mfe, pnl)
        position.mae = min(position.mae, pnl)
        if position.stop_loss is not None and price <= float(position.stop_loss):
            return self.exit_position(trade_id, float(position.stop_loss), now_ts, reason="stop_loss")
        if position.target is not None and price >= float(position.target):
            return self.exit_position(trade_id, float(position.target), now_ts, reason="target")
        return position

    def exit_position(self, trade_id: str, exit_price: float, now_ts: float, *, reason: str = "manual") -> PaperPosition | None:
        position = self._open.pop(str(trade_id), None)
        if position is None:
            return None
        position.exit_price = float(exit_price)
        position.exit_time = float(now_ts)
        position.status = "CLOSED"
        position.realized_pnl = round((position.exit_price - position.entry_price) * position.qty, 4)
        if position.entry_price > 0:
            position.realized_pnl_pct = round(((position.exit_price - position.entry_price) / position.entry_price) * 100.0, 4)
        position.notes.append(f"exit_reason:{reason}")
        self._closed.append(position)
        return position

    def snapshot(self) -> PaperTradingSnapshot:
        closed = list(self._closed)
        total_realized_pnl = round(sum(float(position.realized_pnl) for position in closed), 4)
        total_realized_pnl_pct = round(sum(float(position.realized_pnl_pct) for position in closed), 4)
        total_trades = len(closed)
        wins = sum(1 for position in closed if float(position.realized_pnl) > 0)
        win_rate = round((wins / total_trades), 4) if total_trades else 0.0
        return PaperTradingSnapshot(
            open_positions=[position.__dict__.copy() for position in self._open.values()],
            closed_positions=[position.__dict__.copy() for position in closed],
            total_realized_pnl=total_realized_pnl,
            total_realized_pnl_pct=total_realized_pnl_pct,
            win_rate=win_rate,
            total_trades=total_trades,
        )
