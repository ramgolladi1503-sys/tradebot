from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ExitAction:
    action: str
    new_stop: float | None
    exit_fraction: float
    reason: str
    telemetry: dict[str, Any]


def evaluate_exit_action(position: dict[str, Any], market: dict[str, Any]) -> ExitAction:
    entry = float(position.get("entry_price") or 0.0)
    stop = float(position.get("stop_loss") or 0.0)
    current_price = float(market.get("last_price") or entry)
    playbook = str(position.get("playbook") or "").lower()
    tp1_done = bool(position.get("tp1_done"))

    risk = abs(entry - stop)
    if risk <= 0:
        return ExitAction("HOLD", None, 0.0, "invalid_risk", {})

    pnl_r = (current_price - entry) / risk if playbook != "profile_rejection" else (entry - current_price) / risk

    # TP1 logic
    if pnl_r >= 1.0 and not tp1_done:
        return ExitAction("PARTIAL_EXIT", None, 0.5, "tp1_hit", {"pnl_r": pnl_r})

    # Move to breakeven
    if pnl_r >= 1.2:
        return ExitAction("MOVE_STOP", entry, 0.0, "move_to_be", {"pnl_r": pnl_r})

    # Stall detection
    recent_volatility = float(market.get("volatility") or 0.0)
    if pnl_r > 0.5 and recent_volatility < 0.2:
        return ExitAction("PARTIAL_EXIT", None, 0.5, "stall_exit", {"pnl_r": pnl_r})

    # Hard stop
    if pnl_r < -1.0:
        return ExitAction("FULL_EXIT", None, 1.0, "stop_hit", {"pnl_r": pnl_r})

    return ExitAction("HOLD", None, 0.0, "hold", {"pnl_r": pnl_r})
