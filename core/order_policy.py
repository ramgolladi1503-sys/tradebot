from __future__ import annotations

from dataclasses import dataclass

from config import config as cfg


@dataclass(frozen=True)
class OrderPolicyDecision:
    allowed: bool
    order_policy: str
    reason_code: str
    reason: str


def choose_order_policy(
    *,
    execution_entry_present: bool,
    execution_entry_status: str,
    spread_pct: float | None,
    liquidity_quality: float | None,
    expected_slippage_bps: float | None,
    depth_ratio: float | None,
    quote_ok: bool,
) -> OrderPolicyDecision:
    status = str(execution_entry_status or "").strip().lower()
    if not execution_entry_present or status != "executable":
        return OrderPolicyDecision(False, "reject", "missing_executable_entry", "missing_executable_entry")
    if not bool(quote_ok):
        return OrderPolicyDecision(False, "reject", "invalid_quote", "invalid_quote")
    if spread_pct is None:
        return OrderPolicyDecision(False, "reject", "missing_spread", "missing_spread")

    max_spread = float(getattr(cfg, "EXECUTION_QUALITY_LIMIT_MAX_SPREAD_PCT", getattr(cfg, "MAX_SPREAD_PCT", 0.02)) or 0.02)
    market_spread = float(getattr(cfg, "EXECUTION_QUALITY_MARKET_MAX_SPREAD_PCT", 0.005) or 0.005)
    min_liquidity = float(getattr(cfg, "EXECUTION_QUALITY_MIN_LIQUIDITY_QUALITY", 0.35) or 0.35)
    market_liquidity = float(getattr(cfg, "EXECUTION_QUALITY_MARKET_MIN_LIQUIDITY_QUALITY", 0.75) or 0.75)
    max_slippage = float(getattr(cfg, "EXECUTION_QUALITY_MAX_SLIPPAGE_BPS", 25.0) or 25.0)
    max_depth_ratio = float(getattr(cfg, "EXECUTION_QUALITY_MAX_DEPTH_RATIO", 1.25) or 1.25)

    if spread_pct > max_spread:
        return OrderPolicyDecision(False, "reject", "wide_spread", "wide_spread")
    if liquidity_quality is not None and liquidity_quality < min_liquidity:
        return OrderPolicyDecision(False, "reject", "weak_liquidity", "weak_liquidity")
    if expected_slippage_bps is not None and expected_slippage_bps > max_slippage:
        return OrderPolicyDecision(False, "reject", "slippage_too_high", "slippage_too_high")
    if depth_ratio is not None and depth_ratio > max_depth_ratio:
        return OrderPolicyDecision(False, "reject", "insufficient_depth", "insufficient_depth")

    if (
        spread_pct <= market_spread
        and (liquidity_quality is None or liquidity_quality >= market_liquidity)
        and (depth_ratio is None or depth_ratio <= 1.0)
    ):
        return OrderPolicyDecision(True, "market", "ok_market", "market_ok")
    return OrderPolicyDecision(True, "limit", "ok_limit", "limit_required")
