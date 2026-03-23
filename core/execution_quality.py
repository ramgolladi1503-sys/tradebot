from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from config import config as cfg
from core.order_policy import choose_order_policy
from core.slippage_model import estimate_slippage


@dataclass(frozen=True)
class ExecutionQualityDecision:
    expected_slippage: float | None
    spread_penalty: float
    executable_price_estimate: float | None
    execution_ok: bool
    order_policy: str
    reason_code: str
    reason: str
    expected_slippage_bps: float | None = None
    spread_pct: float | None = None
    liquidity_quality: float | None = None
    depth_ratio: float | None = None
    context: dict[str, Any] = field(default_factory=dict)


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _candidate_get(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _liquidity_quality(candidate: Any) -> float:
    volume = max(
        _safe_float(_candidate_get(candidate, "volume")) or 0.0,
        _safe_float(_candidate_get(candidate, "current_volume")) or 0.0,
    )
    min_volume = max(float(getattr(cfg, "MIN_VOLUME_FILTER", 1.0) or 1.0), 1.0)
    volume_score = min(1.0, volume / min_volume) if volume > 0 else 0.35
    quote_ok = bool(_candidate_get(candidate, "quote_ok", True))
    if not quote_ok:
        volume_score *= 0.65
    return max(0.0, min(1.0, float(volume_score)))


def evaluate_pretrade_execution_quality(candidate: Any) -> ExecutionQualityDecision:
    if not bool(getattr(cfg, "EXECUTION_QUALITY_ENABLE", True)):
        return ExecutionQualityDecision(
            expected_slippage=_safe_float(_candidate_get(candidate, "expected_slippage")),
            spread_penalty=0.0,
            executable_price_estimate=_safe_float(_candidate_get(candidate, "execution_entry")),
            execution_ok=True,
            order_policy="limit",
            reason_code="execution_quality_disabled",
            reason="execution_quality_disabled",
        )

    bid = _safe_float(_candidate_get(candidate, "best_bid"))
    if bid is None:
        bid = _safe_float(_candidate_get(candidate, "opt_bid"))
    ask = _safe_float(_candidate_get(candidate, "best_ask"))
    if ask is None:
        ask = _safe_float(_candidate_get(candidate, "opt_ask"))
    execution_entry = _safe_float(_candidate_get(candidate, "execution_entry"))
    execution_entry_status = str(_candidate_get(candidate, "execution_entry_status") or "").strip().lower()
    qty = _safe_float(_candidate_get(candidate, "qty_units"))
    if qty is None or qty <= 0:
        qty = _safe_float(_candidate_get(candidate, "qty"))
    volume = max(
        _safe_float(_candidate_get(candidate, "volume")) or 0.0,
        _safe_float(_candidate_get(candidate, "current_volume")) or 0.0,
    )
    spread_pct = _safe_float(_candidate_get(candidate, "spread_pct"))
    if spread_pct is None and bid is not None and ask is not None:
        mid = (bid + ask) / 2.0
        spread_pct = (ask - bid) / max(mid, 1e-9)
    slippage = estimate_slippage(
        side=str(_candidate_get(candidate, "side") or "BUY").strip().upper(),
        bid=bid,
        ask=ask,
        execution_entry=execution_entry,
        qty=qty or 1.0,
        volume=volume or None,
        depth=_candidate_get(candidate, "depth") or _candidate_get(candidate, "market_depth"),
        vol_z=_candidate_get(candidate, "vol_z"),
    )
    liquidity_quality = _liquidity_quality(candidate)
    policy = choose_order_policy(
        execution_entry_present=execution_entry is not None,
        execution_entry_status=execution_entry_status,
        spread_pct=slippage.spread_pct if slippage.spread_pct is not None else spread_pct,
        liquidity_quality=liquidity_quality,
        expected_slippage_bps=slippage.expected_slippage_bps,
        depth_ratio=slippage.depth_ratio,
        quote_ok=bool(_candidate_get(candidate, "quote_ok", True)),
    )
    spread_penalty = float(slippage.spread_penalty)
    if policy.allowed and policy.order_policy == "limit":
        spread_penalty = min(
            float(getattr(cfg, "EXECUTION_QUALITY_MAX_SCORE_PENALTY", 0.22) or 0.22),
            spread_penalty + float(getattr(cfg, "EXECUTION_QUALITY_LIMIT_SCORE_PENALTY", 0.05) or 0.05),
        )
    context = {
        "policy_reason_code": policy.reason_code,
        "liquidity_quality": round(liquidity_quality, 6),
        "spread_pct": slippage.spread_pct if slippage.spread_pct is not None else spread_pct,
        "depth_ratio": slippage.depth_ratio,
    }
    return ExecutionQualityDecision(
        expected_slippage=slippage.expected_slippage,
        spread_penalty=round(spread_penalty, 6),
        executable_price_estimate=slippage.executable_price_estimate,
        execution_ok=bool(policy.allowed),
        order_policy=policy.order_policy,
        reason_code=policy.reason_code,
        reason=policy.reason,
        expected_slippage_bps=slippage.expected_slippage_bps,
        spread_pct=slippage.spread_pct if slippage.spread_pct is not None else spread_pct,
        liquidity_quality=round(liquidity_quality, 6),
        depth_ratio=slippage.depth_ratio,
        context=context,
    )


def estimate_queue_position(depth, side, limit_price=None, qty=1):
    if not depth:
        return {"queue_position": None, "queue_priority": None}
    try:
        book = depth.get("buy") if side == "BUY" else depth.get("sell")
        if not book:
            return {"queue_position": None, "queue_priority": None}
        top = book[0]
        top_qty = float(top.get("quantity", 0) or 0)
        top_price = float(top.get("price", 0) or 0)
        if limit_price is not None and top_price:
            if side == "BUY" and limit_price > top_price:
                return {"queue_position": 0.0, "queue_priority": 1.0}
            if side == "SELL" and limit_price < top_price:
                return {"queue_position": 0.0, "queue_priority": 1.0}
        ahead = max(top_qty, 0.0)
        denom = max(ahead + max(qty, 1), 1.0)
        queue_position = ahead / denom
        queue_priority = 1.0 - queue_position
        return {"queue_position": round(queue_position, 4), "queue_priority": round(queue_priority, 4)}
    except Exception:
        return {"queue_position": None, "queue_priority": None}


def depth_weighted_impact(depth, side, qty, spread):
    if not depth or spread is None:
        return None
    try:
        book = depth.get("sell") if side == "BUY" else depth.get("buy")
        if not book:
            return None
        total = 0.0
        for level in book[:3]:
            total += float(level.get("quantity", 0) or 0)
        total = max(total, 1.0)
        impact = (qty / total) * float(spread)
        return round(impact, 6)
    except Exception:
        return None


def classify_urgency(confidence, time_to_expiry_hrs=None, spread_pct=None):
    score = 0.0
    try:
        if confidence is not None:
            score += float(confidence)
    except Exception:
        pass
    try:
        if time_to_expiry_hrs is not None:
            if time_to_expiry_hrs <= 1:
                score += 0.4
            elif time_to_expiry_hrs <= 4:
                score += 0.2
    except Exception:
        pass
    try:
        if spread_pct is not None and spread_pct > 0.02:
            score -= 0.1
    except Exception:
        pass
    if score >= 0.8:
        return "HIGH", round(score, 3)
    if score >= 0.55:
        return "MED", round(score, 3)
    return "LOW", round(score, 3)


def implementation_shortfall(decision_mid, fill_price, side):
    if decision_mid is None or fill_price is None:
        return None
    if side == "BUY":
        return round(fill_price - decision_mid, 4)
    return round(decision_mid - fill_price, 4)


def opportunity_cost(decision_mid, mid_end, side):
    if decision_mid is None or mid_end is None:
        return None
    if side == "BUY":
        return round(mid_end - decision_mid, 4)
    return round(decision_mid - mid_end, 4)


def alpha_decay(decision_mid, mid_at_fill, side):
    if decision_mid is None or mid_at_fill is None:
        return None
    if side == "BUY":
        return round(mid_at_fill - decision_mid, 4)
    return round(decision_mid - mid_at_fill, 4)


def adverse_selection(mid_at_fill, mid_after, side):
    if mid_at_fill is None or mid_after is None:
        return None
    if side == "BUY":
        return round(mid_after - mid_at_fill, 4)
    return round(mid_at_fill - mid_after, 4)


def execution_quality_score(report):
    """
    Produces a 0-100 score based on slippage, spread, time-to-fill, and adverse selection.
    """
    if not report:
        return None
    score = 100.0
    try:
        slippage = report.get("slippage_vs_mid")
        if slippage is not None:
            score -= min(30.0, abs(float(slippage)) * 100.0)
    except Exception:
        pass
    try:
        spread = report.get("decision_spread")
        if spread is not None:
            score -= min(20.0, float(spread) * 10.0)
    except Exception:
        pass
    try:
        ttf = report.get("time_to_fill")
        if ttf is not None:
            score -= min(20.0, float(ttf) * 5.0)
    except Exception:
        pass
    try:
        adverse = report.get("adverse_selection")
        if adverse is not None:
            score -= min(20.0, abs(float(adverse)) * 50.0)
    except Exception:
        pass
    try:
        queue_pos = report.get("queue_position")
        if queue_pos is not None:
            score -= min(10.0, float(queue_pos) * 10.0)
    except Exception:
        pass
    return round(max(0.0, min(100.0, score)), 2)
