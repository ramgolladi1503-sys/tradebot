from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any


class RepricingLagError(ValueError):
    """Raised when the DORL-V3 contract or evidence is invalid."""


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _validate_black_inputs(
    futures_price: float,
    strike: float,
    years_to_expiry: float,
    volatility: float,
) -> None:
    values = (futures_price, strike, years_to_expiry, volatility)
    if not all(math.isfinite(float(value)) for value in values):
        raise RepricingLagError("Black-76 inputs must be finite")
    if futures_price <= 0 or strike <= 0:
        raise RepricingLagError("futures price and strike must be positive")
    if years_to_expiry <= 0:
        raise RepricingLagError("years_to_expiry must be positive")
    if volatility <= 0:
        raise RepricingLagError("volatility must be positive")


def black76_price(
    option_type: str,
    futures_price: float,
    strike: float,
    years_to_expiry: float,
    volatility: float,
    risk_free_rate: float,
) -> float:
    _validate_black_inputs(
        futures_price, strike, years_to_expiry, volatility
    )
    normalized = str(option_type).upper().strip()
    if normalized not in {"CE", "PE"}:
        raise RepricingLagError("option_type must be CE or PE")
    sqrt_t = math.sqrt(years_to_expiry)
    sigma_t = volatility * sqrt_t
    d1 = (
        math.log(futures_price / strike)
        + 0.5 * volatility * volatility * years_to_expiry
    ) / sigma_t
    d2 = d1 - sigma_t
    discount = math.exp(-risk_free_rate * years_to_expiry)
    if normalized == "CE":
        return discount * (
            futures_price * _normal_cdf(d1)
            - strike * _normal_cdf(d2)
        )
    return discount * (
        strike * _normal_cdf(-d2)
        - futures_price * _normal_cdf(-d1)
    )


@dataclass(frozen=True)
class Black76Greeks:
    delta: float
    gamma: float
    vega: float
    theta_per_year: float


def black76_greeks(
    option_type: str,
    futures_price: float,
    strike: float,
    years_to_expiry: float,
    volatility: float,
    risk_free_rate: float,
) -> Black76Greeks:
    _validate_black_inputs(
        futures_price, strike, years_to_expiry, volatility
    )
    normalized = str(option_type).upper().strip()
    if normalized not in {"CE", "PE"}:
        raise RepricingLagError("option_type must be CE or PE")
    sqrt_t = math.sqrt(years_to_expiry)
    d1 = (
        math.log(futures_price / strike)
        + 0.5 * volatility * volatility * years_to_expiry
    ) / (volatility * sqrt_t)
    discount = math.exp(-risk_free_rate * years_to_expiry)
    delta = (
        discount * _normal_cdf(d1)
        if normalized == "CE"
        else -discount * _normal_cdf(-d1)
    )
    gamma = (
        discount
        * _normal_pdf(d1)
        / (futures_price * volatility * sqrt_t)
    )
    vega = discount * futures_price * _normal_pdf(d1) * sqrt_t
    price_now = black76_price(
        normalized,
        futures_price,
        strike,
        years_to_expiry,
        volatility,
        risk_free_rate,
    )
    one_day = 1.0 / 365.0
    reduced_t = max(years_to_expiry - one_day, 1e-9)
    price_after_day = black76_price(
        normalized,
        futures_price,
        strike,
        reduced_t,
        volatility,
        risk_free_rate,
    )
    theta_per_year = (price_after_day - price_now) / one_day
    return Black76Greeks(
        delta=float(delta),
        gamma=float(gamma),
        vega=float(vega),
        theta_per_year=float(theta_per_year),
    )


def implied_volatility_black76(
    option_type: str,
    option_price: float,
    futures_price: float,
    strike: float,
    years_to_expiry: float,
    risk_free_rate: float,
    *,
    lower: float = 1e-4,
    upper: float = 5.0,
    iterations: int = 100,
) -> float:
    if option_price <= 0 or not math.isfinite(float(option_price)):
        raise RepricingLagError("option price must be positive and finite")
    low_price = black76_price(
        option_type,
        futures_price,
        strike,
        years_to_expiry,
        lower,
        risk_free_rate,
    )
    high_price = black76_price(
        option_type,
        futures_price,
        strike,
        years_to_expiry,
        upper,
        risk_free_rate,
    )
    if option_price < low_price - 1e-9 or option_price > high_price + 1e-9:
        raise RepricingLagError(
            "option price is outside the Black-76 volatility bracket"
        )
    lo = lower
    hi = upper
    for _ in range(iterations):
        mid = (lo + hi) / 2.0
        price = black76_price(
            option_type,
            futures_price,
            strike,
            years_to_expiry,
            mid,
            risk_free_rate,
        )
        if price < option_price:
            lo = mid
        else:
            hi = mid
    return float((lo + hi) / 2.0)


__all__ = [
    "Black76Greeks",
    "RepricingLagError",
    "black76_greeks",
    "black76_price",
    "canonical_hash",
    "implied_volatility_black76",
]
