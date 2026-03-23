from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any

from config import config as cfg


@dataclass(frozen=True)
class SlippageEstimate:
    expected_slippage: float
    expected_slippage_bps: float | None
    spread_penalty: float
    executable_price_estimate: float | None
    spread: float | None = None
    spread_pct: float | None = None
    depth_ratio: float | None = None
    liquidity_ratio: float | None = None
    reason_code: str = "ok"


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _book_levels(depth: Any, side: str) -> list[dict[str, Any]]:
    if not isinstance(depth, dict):
        return []
    book = depth.get("sell") if str(side).strip().upper() == "BUY" else depth.get("buy")
    return list(book) if isinstance(book, list) else []


def _top_depth_qty(depth: Any, side: str) -> float | None:
    levels = _book_levels(depth, side)
    if not levels:
        return None
    top = levels[0] if isinstance(levels[0], dict) else {}
    qty = _safe_float(top.get("quantity"))
    return qty if qty is not None and qty > 0 else None


def estimate_slippage(
    *,
    side: str,
    bid: Any,
    ask: Any,
    execution_entry: Any,
    qty: Any = 1,
    volume: Any = None,
    depth: Any = None,
    vol_z: Any = 0.0,
) -> SlippageEstimate:
    bid_v = _safe_float(bid)
    ask_v = _safe_float(ask)
    entry_v = _safe_float(execution_entry)
    qty_v = max(_safe_float(qty) or 1.0, 1.0)
    volume_v = max(_safe_float(volume) or 0.0, qty_v)
    vol_z_v = abs(_safe_float(vol_z) or 0.0)
    side_v = str(side or "BUY").strip().upper()

    if bid_v is None or ask_v is None or bid_v <= 0.0 or ask_v <= 0.0 or ask_v < bid_v:
        return SlippageEstimate(
            expected_slippage=0.0,
            expected_slippage_bps=None,
            spread_penalty=float(getattr(cfg, "EXECUTION_QUALITY_MAX_SCORE_PENALTY", 0.22) or 0.22),
            executable_price_estimate=None,
            reason_code="missing_quote",
        )

    touch = entry_v
    if touch is None:
        touch = ask_v if side_v == "BUY" else bid_v
    mid = (bid_v + ask_v) / 2.0
    spread = max(0.0, ask_v - bid_v)
    spread_pct = spread / max(mid, 1e-9)
    size_ratio = qty_v / max(volume_v, 1.0)
    top_depth_qty = _top_depth_qty(depth, side_v)
    depth_ratio = qty_v / max(top_depth_qty, 1.0) if top_depth_qty is not None else None

    base_mult = float(getattr(cfg, "EXEC_DET_BASE_SPREAD_MULT", 0.35))
    vol_mult = float(getattr(cfg, "EXEC_DET_VOL_MULT", 0.08))
    size_mult = float(getattr(cfg, "EXEC_DET_SIZE_MULT", 0.60))
    liq_mult = float(getattr(cfg, "EXEC_DET_LIQ_MULT", 0.25))
    depth_mult = float(getattr(cfg, "EXECUTION_QUALITY_DEPTH_IMPACT_MULT", 0.35))
    penalty_cap = float(getattr(cfg, "EXECUTION_QUALITY_MAX_SCORE_PENALTY", 0.22) or 0.22)
    limit_spread = max(float(getattr(cfg, "EXECUTION_QUALITY_LIMIT_MAX_SPREAD_PCT", getattr(cfg, "MAX_SPREAD_PCT", 0.02)) or 0.02), 1e-6)

    expected_slippage = (
        spread * base_mult
        + spread * min(vol_z_v, 5.0) * vol_mult
        + spread * sqrt(max(size_ratio, 0.0)) * size_mult
        + spread * min(1.0, 5000.0 / max(volume_v, 1.0)) * liq_mult
    )
    if depth_ratio is not None:
        expected_slippage += spread * max(0.0, depth_ratio - 1.0) * depth_mult
    expected_slippage = max(0.0, float(expected_slippage))
    expected_slippage_bps = (expected_slippage / max(mid, 1e-9)) * 10000.0

    spread_component = min(1.5, spread_pct / limit_spread)
    liquidity_component = min(1.0, sqrt(max(size_ratio, 0.0)))
    depth_component = min(1.0, max(0.0, (depth_ratio or 1.0) - 1.0))
    spread_penalty = min(
        penalty_cap,
        (0.08 * spread_component) + (0.04 * liquidity_component) + (0.03 * depth_component),
    )

    executable_price_estimate = (
        touch + expected_slippage
        if side_v == "BUY"
        else max(0.01, touch - expected_slippage)
    )
    return SlippageEstimate(
        expected_slippage=round(expected_slippage, 6),
        expected_slippage_bps=round(expected_slippage_bps, 6),
        spread_penalty=round(spread_penalty, 6),
        executable_price_estimate=round(executable_price_estimate, 6),
        spread=round(spread, 6),
        spread_pct=round(spread_pct, 6),
        depth_ratio=round(depth_ratio, 6) if depth_ratio is not None else None,
        liquidity_ratio=round(size_ratio, 6),
        reason_code="ok",
    )
