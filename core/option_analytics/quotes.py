from __future__ import annotations

import math

from .contracts import CalculationStatus, PriceBasis, QuoteInput, QuoteResult
from .conventions import is_finite_number, validate_aware_datetime


def resolve_quote(quote: QuoteInput, *, basis: PriceBasis, freshness_limit_seconds: float) -> QuoteResult:
    if not is_finite_number(freshness_limit_seconds) or freshness_limit_seconds < 0:
        return _empty(quote, basis, freshness_limit_seconds, CalculationStatus.INVALID_INPUT, "freshness limit must be finite and non-negative")
    if not validate_aware_datetime(quote.valuation_timestamp) or not validate_aware_datetime(quote.quote_timestamp):
        return _empty(quote, basis, freshness_limit_seconds, CalculationStatus.QUOTE_INVALID, "quote and valuation timestamps must be timezone-aware")
    numeric = [x for x in (quote.best_bid, quote.best_ask, quote.last_price, quote.explicit_price) if x is not None]
    if not all(is_finite_number(x) for x in numeric):
        return _empty(quote, basis, freshness_limit_seconds, CalculationStatus.QUOTE_INVALID, "quote prices must be finite")
    if any(float(x) <= 0 for x in numeric):
        return _empty(quote, basis, freshness_limit_seconds, CalculationStatus.QUOTE_INVALID, "quote prices must be positive")

    bid = float(quote.best_bid) if quote.best_bid is not None else None
    ask = float(quote.best_ask) if quote.best_ask is not None else None
    last = float(quote.last_price) if quote.last_price is not None else None
    explicit = float(quote.explicit_price) if quote.explicit_price is not None else None
    crossed = bid is not None and ask is not None and bid > ask
    locked = bid is not None and ask is not None and bid == ask
    age = (quote.valuation_timestamp - quote.quote_timestamp).total_seconds()
    if age < 0:
        return _empty(quote, basis, freshness_limit_seconds, CalculationStatus.QUOTE_INVALID, "quote timestamp cannot be in the future")
    if crossed:
        return _result(quote, basis, freshness_limit_seconds, CalculationStatus.QUOTE_CROSSED, None, age, locked, crossed, "bid exceeds ask")
    if age > freshness_limit_seconds:
        return _result(quote, basis, freshness_limit_seconds, CalculationStatus.QUOTE_STALE, None, age, locked, crossed, "quote exceeds freshness limit")

    mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
    price = {
        PriceBasis.MID: mid,
        PriceBasis.BID: bid,
        PriceBasis.ASK: ask,
        PriceBasis.LAST: last,
        PriceBasis.EXPLICIT: explicit,
    }[basis]
    if price is None:
        return _result(quote, basis, freshness_limit_seconds, CalculationStatus.PRICE_UNAVAILABLE, None, age, locked, crossed, f"{basis.value} price is unavailable")
    return _result(quote, basis, freshness_limit_seconds, CalculationStatus.OK, price, age, locked, crossed, None)


def _result(
    quote: QuoteInput,
    basis: PriceBasis,
    freshness_limit_seconds: float,
    status: CalculationStatus,
    price: float | None,
    age: float | None,
    locked: bool,
    crossed: bool,
    warning: str | None,
) -> QuoteResult:
    bid = float(quote.best_bid) if quote.best_bid is not None and is_finite_number(quote.best_bid) else None
    ask = float(quote.best_ask) if quote.best_ask is not None and is_finite_number(quote.best_ask) else None
    last = float(quote.last_price) if quote.last_price is not None and is_finite_number(quote.last_price) else None
    mid = (bid + ask) / 2.0 if bid is not None and ask is not None and bid <= ask else None
    spread = ask - bid if bid is not None and ask is not None and bid <= ask else None
    spread_fraction = spread / mid if spread is not None and mid and mid > 0 else None
    if spread_fraction is not None and not math.isfinite(spread_fraction):
        spread_fraction = None
    safe_freshness_limit = float(freshness_limit_seconds) if is_finite_number(freshness_limit_seconds) else None
    return QuoteResult(
        status=status,
        price_basis=basis,
        market_price=price,
        best_bid=bid,
        best_ask=ask,
        last_price=last,
        mid_price=mid,
        spread_absolute=spread,
        spread_fraction_of_mid=spread_fraction,
        quote_age_seconds=age,
        freshness_limit_seconds=safe_freshness_limit,
        locked_market=locked,
        crossed_market=crossed,
        source=quote.source,
        quote_timestamp=quote.quote_timestamp,
        valuation_timestamp=quote.valuation_timestamp,
        warnings=(warning,) if warning else (),
    )


def _empty(quote: QuoteInput, basis: PriceBasis, freshness_limit_seconds: float, status: CalculationStatus, warning: str) -> QuoteResult:
    return _result(quote, basis, freshness_limit_seconds, status, None, None, False, False, warning)
