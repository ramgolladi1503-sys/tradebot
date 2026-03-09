"""Strategy-safe quote resolver adapter.

This module exists to keep strategy-layer code decoupled from ``core.market_data``
while preserving existing behavior through a thin, explicit bridge.
"""

from __future__ import annotations

from typing import Any

from core.market_data import get_index_quote_snapshot as _get_index_quote_snapshot
from core.market_data import resolve_index_quote as _resolve_index_quote


def get_index_quote_snapshot(symbol: str) -> dict[str, Any]:
    return _get_index_quote_snapshot(symbol)


def resolve_index_quote(
    *,
    symbol: str,
    mode: str | None,
    ltp: float | None,
    depth: dict[str, Any] | None,
    market_open: bool,
    ltp_age_sec: float | None,
    market_context: dict[str, Any] | None,
) -> dict[str, Any]:
    return _resolve_index_quote(
        symbol=symbol,
        mode=mode,
        ltp=ltp,
        depth=depth,
        market_open=market_open,
        ltp_age_sec=ltp_age_sec,
        market_context=market_context,
    )
