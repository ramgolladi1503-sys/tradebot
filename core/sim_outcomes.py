from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from config import config as cfg


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


@dataclass(frozen=True)
class SimOutcomeSummary:
    mfe: float | None
    mae: float | None
    exit_reason: str
    simulated_pnl: float | None
    would_have_worked: bool
    rejection_saved_loss: bool
    rejection_missed_win: bool
    exit_price: float | None = None
    realized_r_multiple: float | None = None
    stop_hit_before_target: bool = False
    risk_plan_respected: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _candidate_get(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def build_sim_outcome_record(
    candidate: Any,
    simulation_result: Any,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if isinstance(simulation_result, dict):
        result_status = simulation_result.get("status")
        fill_status = simulation_result.get("fill_status")
        mfe = simulation_result.get("mfe")
        mae = simulation_result.get("mae")
        simulated_pnl = simulation_result.get("simulated_pnl")
        exit_reason = simulation_result.get("exit_reason")
        would_have_worked = bool(simulation_result.get("would_have_worked", False))
        rejection_saved_loss = bool(simulation_result.get("rejection_saved_loss", False))
        rejection_missed_win = bool(simulation_result.get("rejection_missed_win", False))
    else:
        result_status = getattr(simulation_result, "status", None)
        fill_status = getattr(simulation_result, "fill_status", None)
        mfe = getattr(simulation_result, "mfe", None)
        mae = getattr(simulation_result, "mae", None)
        simulated_pnl = getattr(simulation_result, "simulated_pnl", None)
        exit_reason = getattr(simulation_result, "exit_reason", None)
        would_have_worked = bool(getattr(simulation_result, "would_have_worked", False))
        rejection_saved_loss = bool(getattr(simulation_result, "rejection_saved_loss", False))
        rejection_missed_win = bool(getattr(simulation_result, "rejection_missed_win", False))
    return {
        "timestamp": str(
            timestamp
            or _candidate_get(candidate, "timestamp")
            or _candidate_get(candidate, "trade_lifecycle_ts")
            or ""
        ),
        "trade_id": _candidate_get(candidate, "trade_id") or _candidate_get(candidate, "trade_key"),
        "symbol": _candidate_get(candidate, "symbol"),
        "strategy_family": _candidate_get(candidate, "strategy_family") or (_candidate_get(candidate, "source_flags", {}) or {}).get("strategy_family"),
        "direction_family": _candidate_get(candidate, "direction_family") or (_candidate_get(candidate, "source_flags", {}) or {}).get("direction_family"),
        "strategy_regime_mode": _candidate_get(candidate, "strategy_regime_mode") or (_candidate_get(candidate, "source_flags", {}) or {}).get("strategy_regime_mode"),
        "session_mode": _candidate_get(candidate, "session_mode") or (_candidate_get(candidate, "source_flags", {}) or {}).get("session_mode"),
        "candidate_class": _candidate_get(candidate, "candidate_class"),
        "selector_outcome": _candidate_get(candidate, "selector_outcome"),
        "signal_score": _safe_float(_candidate_get(candidate, "signal_score")),
        "execution_score": _safe_float(_candidate_get(candidate, "execution_score")),
        "priority_score": _safe_float(_candidate_get(candidate, "priority_score")),
        "final_score": _safe_float(_candidate_get(candidate, "final_score")),
        "selection_probability": _safe_float(_candidate_get(candidate, "selection_probability")),
        "simulation_status": str(result_status or "UNKNOWN"),
        "fill_status": str(fill_status or ""),
        "mfe": _safe_float(mfe),
        "mae": _safe_float(mae),
        "simulated_pnl": _safe_float(simulated_pnl),
        "exit_reason": str(exit_reason or "").strip().upper() or "UNKNOWN",
        "would_have_worked": would_have_worked,
        "rejection_saved_loss": rejection_saved_loss,
        "rejection_missed_win": rejection_missed_win,
        "realized_r_multiple": _safe_float(
            simulation_result.get("realized_r_multiple") if isinstance(simulation_result, dict) else getattr(simulation_result, "realized_r_multiple", None)
        ),
        "stop_hit_before_target": bool(
            simulation_result.get("stop_hit_before_target", False) if isinstance(simulation_result, dict) else getattr(simulation_result, "stop_hit_before_target", False)
        ),
        "risk_plan_respected": bool(
            simulation_result.get("risk_plan_respected", True) if isinstance(simulation_result, dict) else getattr(simulation_result, "risk_plan_respected", True)
        ),
    }


def summarize_sim_outcome(
    *,
    entry_price: float | None,
    side: str,
    future_prices: Iterable[float | int] | None,
    stop_loss: float | None = None,
    target: float | None = None,
    rejected: bool = False,
    quantity: int | float = 1,
) -> SimOutcomeSummary:
    entry = _safe_float(entry_price)
    if entry in (None, 0.0):
        return SimOutcomeSummary(
            mfe=None,
            mae=None,
            exit_reason="NO_PATH",
            simulated_pnl=None,
            would_have_worked=False,
            rejection_saved_loss=False,
            rejection_missed_win=False,
            exit_price=None,
        )
    prices = [float(price) for price in (future_prices or []) if _safe_float(price) is not None]
    if not prices:
        return SimOutcomeSummary(
            mfe=0.0,
            mae=0.0,
            exit_reason="NO_PATH",
            simulated_pnl=0.0,
            would_have_worked=False,
            rejection_saved_loss=False,
            rejection_missed_win=False,
            exit_price=entry,
        )
    normalized_side = str(side or "BUY").strip().upper()
    pnl_points: list[float] = []
    exit_reason = "PATH_END"
    exit_price = float(prices[-1])
    for price in prices:
        current = float(price)
        pnl = (current - float(entry)) if normalized_side != "SELL" else (float(entry) - current)
        pnl_points.append(float(pnl))
        if normalized_side == "SELL":
            if stop_loss is not None and current >= float(stop_loss):
                exit_reason = "STOP_HIT"
                exit_price = current
                break
            if target is not None and current <= float(target):
                exit_reason = "TARGET_HIT"
                exit_price = current
                break
        else:
            if stop_loss is not None and current <= float(stop_loss):
                exit_reason = "STOP_HIT"
                exit_price = current
                break
            if target is not None and current >= float(target):
                exit_reason = "TARGET_HIT"
                exit_price = current
                break
    mfe = max(pnl_points) if pnl_points else 0.0
    mae = min(pnl_points) if pnl_points else 0.0
    simulated_pnl = (float(exit_price) - float(entry)) if normalized_side != "SELL" else (float(entry) - float(exit_price))
    simulated_pnl *= float(quantity or 1)
    would_have_worked = bool(exit_reason == "TARGET_HIT" or simulated_pnl > 0)
    rejection_saved_loss = bool(rejected and simulated_pnl < 0)
    rejection_missed_win = bool(rejected and simulated_pnl > 0)
    stop_hit_before_target = bool(exit_reason == "STOP_HIT")
    realized_r_multiple = None
    if stop_loss is not None:
        unit_risk = abs(float(entry) - float(stop_loss))
        if unit_risk > 0:
            realized_r_multiple = float(simulated_pnl) / max(unit_risk * float(quantity or 1), 1e-6)
    risk_plan_respected = True
    if realized_r_multiple is not None:
        risk_plan_respected = bool(
            float(realized_r_multiple) >= -(1.0 + float(getattr(cfg, "OFFLINE_RISK_PLAN_MAX_OVERSHOOT_R", 0.20) or 0.20))
        )
    return SimOutcomeSummary(
        mfe=round(float(mfe), 6),
        mae=round(float(mae), 6),
        exit_reason=exit_reason,
        simulated_pnl=round(float(simulated_pnl), 6),
        would_have_worked=would_have_worked,
        rejection_saved_loss=rejection_saved_loss,
        rejection_missed_win=rejection_missed_win,
        exit_price=round(float(exit_price), 6),
        realized_r_multiple=round(float(realized_r_multiple), 6) if realized_r_multiple is not None else None,
        stop_hit_before_target=stop_hit_before_target,
        risk_plan_respected=risk_plan_respected,
    )
