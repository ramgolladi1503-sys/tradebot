from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ExecutionPlan:
    should_execute: bool
    order_style: str
    entry_limit: float | None
    max_chase_pct: float
    timeout_sec: float
    replace_limit: int
    expected_slippage_bps: float
    effective_rr: float
    reason: str
    telemetry: dict[str, Any]


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def build_execution_plan(candidate: dict[str, Any], market_snapshot: dict[str, Any] | None = None) -> ExecutionPlan:
    snapshot = dict(market_snapshot or {})
    playbook = str(candidate.get("selected_playbook") or candidate.get("decision_playbook") or "none").strip().lower()
    spread_pct = _safe_float(candidate.get("spread_pct"))
    liquidity_score = _safe_float(candidate.get("liquidity_score"))
    execution_quality_score = _safe_float(candidate.get("execution_quality_score"))
    entry = _safe_float(candidate.get("execution_entry") or candidate.get("display_entry") or candidate.get("entry"))
    stop_loss = _safe_float(candidate.get("stop_loss"))
    target = _safe_float(candidate.get("target"))
    urgency = _safe_float(snapshot.get("urgency")) or 0.5

    if entry is None or stop_loss is None or target is None:
        return ExecutionPlan(False, "none", None, 0.0, 0.0, 0, 0.0, 0.0, "missing_trade_levels", {})

    base_risk = abs(entry - stop_loss)
    base_reward = abs(target - entry)
    base_rr = base_reward / max(base_risk, 1e-6)

    expected_slippage_bps = 6.0
    if spread_pct is not None:
        expected_slippage_bps += min(40.0, spread_pct * 10000.0 * 0.35)
    if liquidity_score is not None:
        expected_slippage_bps += max(0.0, (1.0 - liquidity_score) * 10.0)
    if execution_quality_score is not None:
        expected_slippage_bps += max(0.0, (1.0 - execution_quality_score) * 8.0)

    slippage_price = entry * (expected_slippage_bps / 10000.0)
    effective_reward = max(0.0, base_reward - slippage_price)
    effective_rr = effective_reward / max(base_risk + slippage_price, 1e-6)

    if playbook == "breakout_continuation":
        order_style = "aggressive_limit"
        max_chase_pct = 0.0025 + urgency * 0.001
        timeout_sec = 8.0
        replace_limit = 2
    elif playbook == "profile_rejection":
        order_style = "passive_limit"
        max_chase_pct = 0.0010
        timeout_sec = 4.0
        replace_limit = 1
    else:
        order_style = "passive_limit"
        max_chase_pct = 0.0015
        timeout_sec = 5.0
        replace_limit = 1

    if spread_pct is not None and spread_pct > 0.03:
        return ExecutionPlan(False, order_style, entry, max_chase_pct, timeout_sec, replace_limit, expected_slippage_bps, effective_rr, "spread_too_wide", {"spread_pct": spread_pct})

    if effective_rr < 1.2:
        return ExecutionPlan(False, order_style, entry, max_chase_pct, timeout_sec, replace_limit, expected_slippage_bps, effective_rr, "effective_rr_too_low", {"base_rr": base_rr})

    entry_limit = entry
    if order_style == "passive_limit":
        entry_limit = entry - slippage_price * 0.25
    elif order_style == "aggressive_limit":
        entry_limit = entry + slippage_price * 0.25

    return ExecutionPlan(
        True,
        order_style,
        entry_limit,
        max_chase_pct,
        timeout_sec,
        replace_limit,
        expected_slippage_bps,
        effective_rr,
        "ok",
        {
            "playbook": playbook,
            "spread_pct": spread_pct,
            "liquidity_score": liquidity_score,
            "execution_quality_score": execution_quality_score,
            "base_rr": base_rr,
        },
    )
