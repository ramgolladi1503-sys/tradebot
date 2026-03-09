from __future__ import annotations

from typing import Any, Mapping

from core.decision_snapshot import DecisionSnapshot


def _get_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def build_snapshot(
    *,
    market_data: Mapping[str, Any] | None,
    trade: Any | None = None,
    now_ts: float | None = None,
) -> DecisionSnapshot:
    """
    Build one atomic decision snapshot for a candidate from current market state.
    This helper is additive and does not alter existing schemas.
    """
    data = dict(market_data or {})
    ts_sec = _get_float(now_ts)
    if ts_sec is None:
        ts_sec = _get_float(data.get("timestamp")) or _get_float(data.get("quote_ts")) or 0.0
    ts_ms = int(round(ts_sec * 1000.0))

    index_ltp = _get_float(data.get("spot"))
    if index_ltp is None:
        index_ltp = _get_float(data.get("underlying_spot"))
    if index_ltp is None:
        index_ltp = _get_float(data.get("ltp"))

    option_bid = _get_float(getattr(trade, "opt_bid", None))
    if option_bid is None:
        option_bid = _get_float(data.get("bid"))
    option_ask = _get_float(getattr(trade, "opt_ask", None))
    if option_ask is None:
        option_ask = _get_float(data.get("ask"))
    option_ltp = _get_float(getattr(trade, "opt_ltp", None))
    if option_ltp is None:
        option_ltp = _get_float(data.get("ltp"))

    spread = _get_float(getattr(trade, "spread_pct", None))
    if spread is None:
        spread = _get_float(data.get("spread_pct"))

    depth = data.get("depth") if isinstance(data.get("depth"), Mapping) else None

    index_quote_age_ms = None
    quote_age = _get_float(data.get("quote_age_sec"))
    if quote_age is not None:
        index_quote_age_ms = quote_age * 1000.0

    option_quote_age_ms = _get_float(getattr(trade, "option_age_sec", None))
    if option_quote_age_ms is None:
        option_quote_age_ms = _get_float(data.get("option_age_sec"))
    if option_quote_age_ms is not None:
        option_quote_age_ms *= 1000.0

    meta = {
        "symbol": data.get("symbol") or getattr(trade, "symbol", None),
        "strategy": getattr(trade, "strategy", None),
        "source": data.get("ltp_source") or data.get("quote_source") or "unknown",
    }

    return DecisionSnapshot.build(
        ts_ms=ts_ms,
        index_price=index_ltp,
        option_bid=option_bid,
        option_ask=option_ask,
        option_ltp=option_ltp,
        spread=spread,
        depth=depth,
        index_quote_age_ms=index_quote_age_ms,
        option_quote_age_ms=option_quote_age_ms,
        source=str(meta.get("source") or "unknown"),
        meta=meta,
    )
