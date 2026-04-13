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


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "None"):
            return default
        return float(value)
    except Exception:
        return default


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


def _playbook_thresholds(playbook: str) -> dict[str, float]:
    value = str(playbook or "").strip().lower()
    if value == "breakout_continuation":
        return {
            "tp1_r": 1.10,
            "be_r": 1.30,
            "trail_start_r": 1.60,
            "stall_r": 0.95,
            "stall_vol_max": 0.18,
            "trail_pullback_r": 0.55,
        }
    if value == "profile_rejection":
        return {
            "tp1_r": 0.80,
            "be_r": 1.00,
            "trail_start_r": 1.20,
            "stall_r": 0.60,
            "stall_vol_max": 0.24,
            "trail_pullback_r": 0.35,
        }
    return {
        "tp1_r": 1.00,
        "be_r": 1.20,
        "trail_start_r": 1.40,
        "stall_r": 0.70,
        "stall_vol_max": 0.20,
        "trail_pullback_r": 0.45,
    }


def evaluate_exit_action(position: dict[str, Any], market: dict[str, Any]) -> ExitAction:
    pos = dict(position or {})
    mkt = dict(market or {})

    entry = float(_safe_float(pos.get("fill_price"), _safe_float(pos.get("entry_price"), 0.0)) or 0.0)
    initial_stop = float(_safe_float(pos.get("initial_stop"), _safe_float(pos.get("stop_loss"), 0.0)) or 0.0)
    current_stop = float(_safe_float(pos.get("current_stop"), _safe_float(pos.get("stop_loss"), initial_stop)) or initial_stop)
    current_price = float(
        _safe_float(mkt.get("last_price"), _safe_float(mkt.get("ltp"), entry))
        or entry
    )

    side = _normalize_side(pos.get("side"))
    playbook = str(pos.get("playbook") or "none").strip().lower()
    status = str(pos.get("status") or "OPEN").strip().upper()
    tp1_done = bool(pos.get("tp1_done"))
    breakeven_done = bool(pos.get("breakeven_done"))
    trailing_active = bool(pos.get("trailing_active"))
    remaining_qty = int(_safe_float(pos.get("remaining_qty"), _safe_float(pos.get("qty"), 0.0)) or 0)
    qty = max(1, int(_safe_float(pos.get("qty"), remaining_qty) or remaining_qty or 1))
    if remaining_qty <= 0 and status != "CLOSED":
        remaining_qty = qty

    thresholds = _playbook_thresholds(playbook)
    pnl_r = _signed_pnl_r(side, entry, initial_stop, current_price)
    mfe_r = float(_safe_float(pos.get("mfe_r"), pnl_r) or pnl_r)
    recent_volatility = float(_safe_float(mkt.get("volatility"), 0.0) or 0.0)

    telemetry = {
        "playbook": playbook,
        "status": status,
        "tp1_done": tp1_done,
        "breakeven_done": breakeven_done,
        "trailing_active": trailing_active,
        "mfe_r": mfe_r,
        "pnl_r": pnl_r,
        "mae_r": float(_safe_float(pos.get("mae_r"), 0.0) or 0.0),
        "current_stop": current_stop,
        "remaining_qty": remaining_qty,
        "volatility": recent_volatility,
    }

    risk = abs(entry - initial_stop)
    if risk <= 0.0:
        return ExitAction("HOLD", None, 0.0, "invalid_risk", telemetry)

    # Hard stop / invalid continuation.
    if pnl_r <= -1.0:
        return ExitAction("FULL_EXIT", None, 1.0, "stop_hit", telemetry)

    # TP1 is one-shot.
    if (not tp1_done) and pnl_r >= thresholds["tp1_r"] and remaining_qty > 1:
        return ExitAction("PARTIAL_EXIT", None, 0.5, "tp1_hit", telemetry)

    # Break-even shift is one-shot.
    if (not breakeven_done) and pnl_r >= thresholds["be_r"]:
        return ExitAction("MOVE_STOP", entry, 0.0, "move_to_be", telemetry)

    # Trail when move is established and pullback from MFE is meaningful.
    if trailing_active or pnl_r >= thresholds["trail_start_r"]:
        drawdown_from_mfe = max(0.0, mfe_r - pnl_r)
        if drawdown_from_mfe >= thresholds["trail_pullback_r"]:
            trail_r = max(0.2, pnl_r - thresholds["trail_pullback_r"] * 0.5)
            if side == "BUY":
                new_stop = entry + trail_r * risk
            else:
                new_stop = entry - trail_r * risk
            # Never loosen stop.
            if side == "BUY":
                new_stop = max(current_stop, new_stop)
            else:
                new_stop = min(current_stop, new_stop)
            return ExitAction("MOVE_STOP", float(new_stop), 0.0, "trail_pullback", telemetry)

    # Stall exit: playbook-dependent.
    if (not tp1_done) and pnl_r >= thresholds["stall_r"] and recent_volatility <= thresholds["stall_vol_max"] and remaining_qty > 1:
        return ExitAction("PARTIAL_EXIT", None, 0.5, "stall_exit", telemetry)

    return ExitAction("HOLD", None, 0.0, "hold", telemetry)
