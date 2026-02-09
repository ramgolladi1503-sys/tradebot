from __future__ import annotations

import math
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from config import config as cfg


def calculate_qty(capital, risk_pct, entry, stop):
    risk_amount = capital * risk_pct
    per_unit_risk = abs(entry - stop)

    if per_unit_risk == 0:
        return 0

    return int(risk_amount / per_unit_risk)


@dataclass
class DeskBudget:
    desk_id: str
    budget_pct: float
    budget_amount: float
    reason: str | None
    metrics: Dict[str, float]
    limits: Dict[str, float]


def _utc_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _discover_desk_dbs() -> Dict[str, Path]:
    desks: Dict[str, Path] = {}
    base = Path("data/desks")
    if base.exists():
        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            db = entry / "trades.db"
            if db.exists():
                desks[entry.name] = db
    # Always include current desk config path
    current_id = getattr(cfg, "DESK_ID", "DEFAULT")
    current_db = Path(getattr(cfg, "TRADE_DB_PATH", "data/trades.db"))
    desks.setdefault(current_id, current_db)
    return desks


def _load_outcomes(db_path: Path, start_epoch: float) -> List[Tuple[float, float]]:
    if not db_path.exists():
        return []
    rows: List[Tuple[float, float]] = []
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT timestamp_epoch, r_multiple FROM outcomes WHERE timestamp_epoch IS NOT NULL AND timestamp_epoch >= ?",
                (start_epoch,),
            )
            for ts, r in cur.fetchall():
                if ts is None or r is None:
                    continue
                rows.append((float(ts), float(r)))
    except Exception:
        return []
    return rows


def _daily_series(rows: List[Tuple[float, float]]) -> Dict[str, float]:
    daily: Dict[str, float] = {}
    for ts, r in rows:
        day = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        daily[day] = daily.get(day, 0.0) + float(r)
    return daily


def _drawdown(daily: Dict[str, float]) -> float:
    if not daily:
        return 0.0
    cum = 0.0
    peak = 0.0
    dd = 0.0
    for day in sorted(daily.keys()):
        cum += daily[day]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return dd


def _corr(series_a: Dict[str, float], series_b: Dict[str, float]) -> float | None:
    overlap = sorted(set(series_a.keys()) & set(series_b.keys()))
    if len(overlap) < int(getattr(cfg, "DESK_MIN_CORR_DAYS", 5)):
        return None
    a_vals = [series_a[d] for d in overlap]
    b_vals = [series_b[d] for d in overlap]
    mean_a = sum(a_vals) / len(a_vals)
    mean_b = sum(b_vals) / len(b_vals)
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a_vals, b_vals))
    den_a = math.sqrt(sum((x - mean_a) ** 2 for x in a_vals))
    den_b = math.sqrt(sum((y - mean_b) ** 2 for y in b_vals))
    if den_a == 0 or den_b == 0:
        return None
    return num / (den_a * den_b)


def compute_desk_budgets(
    days: int = 60,
    global_capital: float | None = None,
    desk_db_paths: Dict[str, Path] | None = None,
) -> Dict[str, object]:
    now = time.time()
    start_epoch = now - (days * 86400)
    global_capital = float(global_capital or getattr(cfg, "GLOBAL_CAPITAL", getattr(cfg, "CAPITAL", 0.0)))
    desk_db_paths = desk_db_paths or _discover_desk_dbs()

    min_trades = int(getattr(cfg, "DESK_MIN_TRADES", 10))
    min_days = int(getattr(cfg, "DESK_MIN_DAYS", 5))
    max_corr = float(getattr(cfg, "DESK_MAX_CORR", 0.8))
    corr_penalty = float(getattr(cfg, "DESK_CORR_PENALTY", 0.3))
    max_budget_pct = float(getattr(cfg, "DESK_MAX_BUDGET_PCT", 0.6))
    min_budget_pct = float(getattr(cfg, "DESK_MIN_BUDGET_PCT", 0.0))
    max_gross_pct = float(getattr(cfg, "DESK_MAX_GROSS_PCT", 0.6))
    max_symbol_pct = float(getattr(cfg, "DESK_MAX_SYMBOL_PCT", 0.3))

    desk_series: Dict[str, Dict[str, float]] = {}
    desk_metrics: Dict[str, Dict[str, float]] = {}
    desk_reasons: Dict[str, str | None] = {}

    for desk_id, db_path in desk_db_paths.items():
        rows = _load_outcomes(db_path, start_epoch)
        if not rows:
            desk_reasons[desk_id] = "no_outcomes"
            continue
        daily = _daily_series(rows)
        if len(rows) < min_trades:
            desk_reasons[desk_id] = "insufficient_trades"
        elif len(daily) < min_days:
            desk_reasons[desk_id] = "insufficient_days"
        else:
            desk_reasons[desk_id] = None

        r_vals = [r for _, r in rows]
        mean_r = sum(r_vals) / len(r_vals)
        std_r = math.sqrt(sum((r - mean_r) ** 2 for r in r_vals) / max(1, len(r_vals) - 1))
        win_rate = sum(1 for r in r_vals if r > 0) / len(r_vals)
        dd = _drawdown(daily)
        peak = max(1.0, max(0.0, sum(daily.values())))
        dd_pct = dd / peak if peak != 0 else 0.0
        vol = std_r

        desk_series[desk_id] = daily
        desk_metrics[desk_id] = {
            "trades": float(len(r_vals)),
            "days": float(len(daily)),
            "mean_r": float(mean_r),
            "std_r": float(std_r),
            "win_rate": float(win_rate),
            "drawdown": float(dd),
            "drawdown_pct": float(dd_pct),
            "vol": float(vol),
        }

    valid_desks = [d for d, reason in desk_reasons.items() if reason is None]
    weights: Dict[str, float] = {d: 0.0 for d in desk_db_paths.keys()}
    if valid_desks:
        base = 1.0 / len(valid_desks)
        for desk_id in valid_desks:
            m = desk_metrics.get(desk_id, {})
            dd_pct = float(m.get("drawdown_pct", 0.0))
            vol = float(m.get("vol", 0.0))
            dd_pen = max(0.1, 1.0 + dd_pct)
            vol_pen = 1.0 / (1.0 + vol)
            weights[desk_id] = base * dd_pen * vol_pen

        # Correlation penalties
        for desk_id in valid_desks:
            max_seen = 0.0
            for other in valid_desks:
                if other == desk_id:
                    continue
                corr = _corr(desk_series.get(desk_id, {}), desk_series.get(other, {}))
                if corr is None:
                    continue
                max_seen = max(max_seen, corr)
            if max_seen > max_corr:
                weights[desk_id] *= max(0.0, 1.0 - corr_penalty * max_seen)

        total = sum(weights[d] for d in valid_desks)
        if total > 0:
            for desk_id in valid_desks:
                weights[desk_id] = weights[desk_id] / total

    budgets: List[DeskBudget] = []
    for desk_id in desk_db_paths.keys():
        reason = desk_reasons.get(desk_id)
        raw_pct = float(weights.get(desk_id, 0.0))
        if reason is not None:
            budget_pct = 0.0
        else:
            budget_pct = min(raw_pct, max_budget_pct)
            if budget_pct < min_budget_pct:
                budget_pct = min_budget_pct
        budget_amount = global_capital * budget_pct
        metrics = desk_metrics.get(desk_id, {}).copy()
        metrics.update({"raw_weight": raw_pct})
        limits = {"max_gross_pct": max_gross_pct, "max_symbol_pct": max_symbol_pct}
        budgets.append(DeskBudget(desk_id, budget_pct, budget_amount, reason, metrics, limits))

    report = {
        "as_of_epoch": now,
        "as_of_iso": _utc_iso(now),
        "global_capital": global_capital,
        "budgets": [b.__dict__ for b in budgets],
    }
    return report
