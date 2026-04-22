from __future__ import annotations

from typing import Any

from config.stock_option_market_context import STOCK_OPTION_CONTEXT_MAP


def _safe_float(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def _trend_score(ltp: float | None, vwap: float | None) -> float:
    if ltp is None or vwap is None or vwap == 0:
        return 0.5
    return 0.75 if ltp >= vwap else 0.25


def cross_asset_adjustment(symbol: str, market_data_by_symbol: dict[str, Any]) -> float:
    ctx = STOCK_OPTION_CONTEXT_MAP.get(symbol)
    if not ctx:
        return 0.0

    index_data = market_data_by_symbol.get(ctx.get("index_symbol"), {})
    sector_data = market_data_by_symbol.get(ctx.get("sector_symbol"), {})
    stock_data = market_data_by_symbol.get(symbol, {})

    stock_trend = _trend_score(_safe_float(stock_data.get("ltp")), _safe_float(stock_data.get("vwap")))
    index_trend = _trend_score(_safe_float(index_data.get("ltp")), _safe_float(index_data.get("vwap")))
    sector_trend = _trend_score(_safe_float(sector_data.get("ltp")), _safe_float(sector_data.get("vwap")))

    alignment = (stock_trend + index_trend + sector_trend) / 3.0

    if alignment > 0.7:
        return 0.10
    if alignment < 0.4:
        return -0.10
    return 0.0
