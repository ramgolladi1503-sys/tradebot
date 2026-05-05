"""
Alpha validation gate for the pro strategy layer.

This module is intentionally strict. A strategy should not be promoted from
shadow/paper into execution unless it has enough samples and positive
execution-adjusted expectancy.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable


@dataclass(frozen=True)
class AlphaValidationReport:
    strategy: str
    sample_size: int
    win_rate: float
    avg_r: float
    expectancy_r: float
    profit_factor: float
    max_loss_r: float
    status: str
    reasons: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _strategy_name(row: dict[str, Any]) -> str:
    return str(
        row.get("strategy")
        or row.get("strategy_name")
        or row.get("name")
        or "unknown"
    ).strip() or "unknown"


def _r_multiple(row: dict[str, Any]) -> float | None:
    explicit = _safe_float(row.get("r_multiple") or row.get("pnl_r"), None)
    if explicit is not None:
        return explicit

    entry = _safe_float(row.get("entry") or row.get("entry_price") or row.get("execution_entry"), None)
    exit_price = _safe_float(row.get("exit") or row.get("exit_price") or row.get("close"), None)
    stop = _safe_float(row.get("stop_loss") or row.get("sl"), None)
    if entry is None or exit_price is None or stop is None:
        pnl = _safe_float(row.get("pnl"), None)
        risk = _safe_float(row.get("risk_amount"), None)
        if pnl is None or risk is None or risk <= 0:
            return None
        return float(pnl) / float(risk)

    risk_per_unit = abs(float(entry) - float(stop))
    if risk_per_unit <= 0:
        return None
    # These are long-option signals. PnL is option exit minus option entry.
    return (float(exit_price) - float(entry)) / risk_per_unit


def _profit_factor(r_values: list[float]) -> float:
    gross_profit = sum(v for v in r_values if v > 0)
    gross_loss = abs(sum(v for v in r_values if v < 0))
    if gross_loss <= 0:
        return 999.0 if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def validate_alpha_edge(
    rows: Iterable[dict[str, Any]],
    *,
    strategy: str | None = None,
    min_trades: int = 30,
    min_expectancy_r: float = 0.05,
    min_profit_factor: float = 1.15,
    min_win_rate: float = 0.45,
    max_allowed_loss_r: float = -2.0,
) -> AlphaValidationReport:
    selected: list[dict[str, Any]] = []
    strategy_filter = str(strategy or "").strip()
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        if strategy_filter and _strategy_name(row) != strategy_filter:
            continue
        selected.append(row)

    r_values = [r for r in (_r_multiple(row) for row in selected) if r is not None]
    sample_size = len(r_values)
    wins = [r for r in r_values if r > 0]
    losses = [r for r in r_values if r <= 0]
    win_rate = (len(wins) / sample_size) if sample_size else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (abs(sum(losses) / len(losses))) if losses else 0.0
    expectancy = (win_rate * avg_win) - ((1.0 - win_rate) * avg_loss)
    avg_r = (sum(r_values) / sample_size) if sample_size else 0.0
    profit_factor = _profit_factor(r_values)
    max_loss_r = min(r_values) if r_values else 0.0

    reasons: list[str] = []
    if sample_size < int(min_trades):
        reasons.append("insufficient_sample_size")
    if expectancy < float(min_expectancy_r):
        reasons.append("expectancy_below_threshold")
    if profit_factor < float(min_profit_factor):
        reasons.append("profit_factor_below_threshold")
    if win_rate < float(min_win_rate):
        reasons.append("win_rate_below_threshold")
    if max_loss_r < float(max_allowed_loss_r):
        reasons.append("tail_loss_too_large")

    status = "PROMOTE" if not reasons else ("PAPER_ONLY" if sample_size >= int(min_trades) else "INSUFFICIENT_DATA")
    return AlphaValidationReport(
        strategy=strategy_filter or "ALL",
        sample_size=sample_size,
        win_rate=round(float(win_rate), 6),
        avg_r=round(float(avg_r), 6),
        expectancy_r=round(float(expectancy), 6),
        profit_factor=round(float(profit_factor), 6),
        max_loss_r=round(float(max_loss_r), 6),
        status=status,
        reasons=reasons,
    )


def require_promotable_alpha(rows: Iterable[dict[str, Any]], **kwargs: Any) -> AlphaValidationReport:
    report = validate_alpha_edge(rows, **kwargs)
    if report.status != "PROMOTE":
        raise RuntimeError(f"ALPHA_NOT_PROMOTABLE:{report.status}:{','.join(report.reasons)}")
    return report
