"""Migration note:
Adds deterministic pre-trade slippage budget checks by regime/volatility.
LIVE-open rejects on breached budgets; planning modes remain advisory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import config as cfg
from core.market_context import derive_market_context


@dataclass(frozen=True)
class SlippageBudgetDecision:
    allowed: bool
    reason_code: str
    reason: str
    expected_slippage_bps: float | None = None
    budget_bps: float | None = None
    context: dict[str, Any] = field(default_factory=dict)


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _budget_for_regime(regime: str, vol_z: float) -> float:
    base = float(getattr(cfg, "EXEC_SLIPPAGE_BUDGET_BPS_BASE", 18.0))
    budget_map = getattr(
        cfg,
        "EXEC_SLIPPAGE_BUDGET_BPS_BY_REGIME",
        {
            "DEFAULT": 18.0,
            "TREND": 20.0,
            "RANGE": 16.0,
            "RANGE_VOLATILE": 14.0,
            "EVENT": 10.0,
            "PANIC": 8.0,
            "NEUTRAL": 14.0,
        },
    )
    budget = base
    if isinstance(budget_map, dict):
        regime_key = str(regime or "DEFAULT").upper()
        if regime_key in budget_map:
            budget = float(budget_map.get(regime_key))
        elif "DEFAULT" in budget_map:
            budget = float(budget_map.get("DEFAULT"))
    vol_mult = float(getattr(cfg, "EXEC_SLIPPAGE_BUDGET_BPS_VOL_Z_MULT", 1.5))
    floor = float(getattr(cfg, "EXEC_SLIPPAGE_BUDGET_BPS_FLOOR", 4.0))
    cap = float(getattr(cfg, "EXEC_SLIPPAGE_BUDGET_BPS_CAP", 80.0))
    budget = budget + abs(float(vol_z)) * vol_mult
    return max(floor, min(cap, budget))


def evaluate_slippage_budget(trade, market_data: dict, execution_engine) -> SlippageBudgetDecision:
    if not bool(getattr(cfg, "EXEC_SLIPPAGE_BUDGET_ENABLE", True)):
        return SlippageBudgetDecision(True, "SLIPPAGE_BUDGET_DISABLED", "slippage_budget_disabled")

    md = dict(market_data or {})
    ctx_payload = dict(md.get("market_context") or {}) if isinstance(md.get("market_context"), dict) else {}
    if "execution_mode" not in ctx_payload:
        ctx_payload["execution_mode"] = getattr(cfg, "EXECUTION_MODE", "SIM")
    if "market_open" not in ctx_payload:
        ctx_payload["market_open"] = md.get("market_open")
    if "segment" not in ctx_payload and md.get("segment") is not None:
        ctx_payload["segment"] = md.get("segment")
    market_ctx = derive_market_context(ctx_payload)
    live_open = bool(market_ctx.mode == "LIVE" and market_ctx.is_market_open)
    enforce_live_only = bool(getattr(cfg, "EXEC_SLIPPAGE_BUDGET_ENFORCE_LIVE_ONLY", True))
    if enforce_live_only and (not live_open):
        return SlippageBudgetDecision(
            True,
            "SLIPPAGE_BUDGET_SKIPPED_NON_LIVE",
            "slippage_budget_skipped_non_live",
            context={"mode": market_ctx.mode, "market_open": bool(market_ctx.is_market_open)},
        )

    bid = _to_float(getattr(trade, "opt_bid", None) if getattr(trade, "instrument", "OPT") == "OPT" else md.get("bid"))
    ask = _to_float(getattr(trade, "opt_ask", None) if getattr(trade, "instrument", "OPT") == "OPT" else md.get("ask"))
    if bid is None or ask is None or bid <= 0.0 or ask <= 0.0 or ask < bid:
        return SlippageBudgetDecision(
            False,
            "MISSING_QUOTE",
            "missing_or_invalid_quote_for_slippage_budget",
            context={"bid": bid, "ask": ask},
        )

    mid = (bid + ask) / 2.0
    spread_pct = (ask - bid) / max(mid, 1e-9)
    max_spread_pct = float(getattr(cfg, "MAX_SPREAD_PCT", 0.03))
    if spread_pct > max_spread_pct:
        return SlippageBudgetDecision(
            False,
            "WIDE_SPREAD",
            "spread_exceeds_limit",
            expected_slippage_bps=round(spread_pct * 10000.0, 4),
            budget_bps=round(max_spread_pct * 10000.0, 4),
            context={"spread_pct": spread_pct, "max_spread_pct": max_spread_pct},
        )

    qty = int(max(getattr(trade, "qty", 1) or 1, 1))
    volume = _to_float(md.get("volume"))
    if volume is None or volume <= 0.0:
        volume = float(max(qty * 50, 100))
    vol_z = _to_float(md.get("vol_z")) or 0.0
    regime = str(getattr(trade, "regime", None) or md.get("regime_day") or md.get("regime") or "DEFAULT").upper()

    expected_abs = 0.0
    try:
        expected_abs = float(
            execution_engine.estimate_slippage(
                bid,
                ask,
                volume=volume,
                qty=qty,
                vol_z=vol_z,
            )
        )
    except Exception:
        expected_abs = 0.0
    expected_bps = float((expected_abs / max(mid, 1e-9)) * 10000.0)
    budget_bps = float(_budget_for_regime(regime, vol_z))

    if expected_bps > budget_bps:
        return SlippageBudgetDecision(
            False,
            "SLIPPAGE_BUDGET_BREACH",
            "expected_slippage_exceeds_budget",
            expected_slippage_bps=round(expected_bps, 4),
            budget_bps=round(budget_bps, 4),
            context={
                "regime": regime,
                "vol_z": vol_z,
                "qty": qty,
                "volume": volume,
                "bid": bid,
                "ask": ask,
            },
        )

    return SlippageBudgetDecision(
        True,
        "OK",
        "slippage_within_budget",
        expected_slippage_bps=round(expected_bps, 4),
        budget_bps=round(budget_bps, 4),
        context={"regime": regime, "vol_z": vol_z},
    )

