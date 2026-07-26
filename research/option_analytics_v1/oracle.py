from __future__ import annotations

import math
from dataclasses import dataclass

_SQRT_TWO = math.sqrt(2.0)
_SQRT_TWO_PI = math.sqrt(2.0 * math.pi)


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT_TWO))


def _pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_TWO_PI


def bsm_price(*, spot: float, strike: float, time_years: float, rate: float, dividend_yield: float, volatility: float, is_call: bool) -> float:
    if time_years == 0:
        return max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
    discounted_spot = spot * math.exp(-dividend_yield * time_years)
    discounted_strike = strike * math.exp(-rate * time_years)
    if volatility == 0:
        return max(discounted_spot - discounted_strike, 0.0) if is_call else max(discounted_strike - discounted_spot, 0.0)
    root_t = math.sqrt(time_years)
    d1 = (math.log(spot / strike) + (rate - dividend_yield + 0.5 * volatility**2) * time_years) / (volatility * root_t)
    d2 = d1 - volatility * root_t
    if is_call:
        return discounted_spot * _cdf(d1) - discounted_strike * _cdf(d2)
    return discounted_strike * _cdf(-d2) - discounted_spot * _cdf(-d1)


def black76_price(*, forward: float, strike: float, time_years: float, rate: float, volatility: float, is_call: bool) -> float:
    discount = math.exp(-rate * time_years)
    if time_years == 0 or volatility == 0:
        payoff = max(forward - strike, 0.0) if is_call else max(strike - forward, 0.0)
        return discount * payoff
    root_t = math.sqrt(time_years)
    d1 = (math.log(forward / strike) + 0.5 * volatility**2 * time_years) / (volatility * root_t)
    d2 = d1 - volatility * root_t
    if is_call:
        return discount * (forward * _cdf(d1) - strike * _cdf(d2))
    return discount * (strike * _cdf(-d2) - forward * _cdf(-d1))


@dataclass(frozen=True)
class OracleGreeks:
    delta: float
    gamma: float
    theta_per_year: float
    vega_per_unit_volatility: float
    rho_per_unit_rate: float


def finite_difference_greeks(
    *,
    model: str,
    option_type: str,
    underlying: float,
    strike: float,
    time_years: float,
    rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> OracleGreeks:
    is_call = option_type == "CALL"

    def price(u: float, t: float, r: float, v: float) -> float:
        if model == "BLACK_SCHOLES_MERTON":
            return bsm_price(
                spot=u,
                strike=strike,
                time_years=t,
                rate=r,
                dividend_yield=dividend_yield,
                volatility=v,
                is_call=is_call,
            )
        if model == "BLACK_76":
            return black76_price(
                forward=u,
                strike=strike,
                time_years=t,
                rate=r,
                volatility=v,
                is_call=is_call,
            )
        raise ValueError(f"unsupported oracle model: {model}")

    underlying_step = max(1e-4, abs(underlying) * 2e-5)
    volatility_step = 1e-5
    rate_step = 1e-6
    time_step = min(max(1e-7, time_years * 1e-5), time_years * 0.25)
    p0 = price(underlying, time_years, rate, volatility)
    p_up = price(underlying + underlying_step, time_years, rate, volatility)
    p_down = price(underlying - underlying_step, time_years, rate, volatility)
    delta = (p_up - p_down) / (2.0 * underlying_step)
    gamma = (p_up - 2.0 * p0 + p_down) / (underlying_step**2)
    vega = (
        price(underlying, time_years, rate, volatility + volatility_step)
        - price(underlying, time_years, rate, volatility - volatility_step)
    ) / (2.0 * volatility_step)
    rho = (
        price(underlying, time_years, rate + rate_step, volatility)
        - price(underlying, time_years, rate - rate_step, volatility)
    ) / (2.0 * rate_step)
    theta = -(
        price(underlying, time_years + time_step, rate, volatility)
        - price(underlying, time_years - time_step, rate, volatility)
    ) / (2.0 * time_step)
    return OracleGreeks(delta=delta, gamma=gamma, theta_per_year=theta, vega_per_unit_volatility=vega, rho_per_unit_rate=rho)


def parity_residual(
    *,
    model: str,
    underlying: float,
    strike: float,
    time_years: float,
    rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> float:
    if model == "BLACK_SCHOLES_MERTON":
        call = bsm_price(spot=underlying, strike=strike, time_years=time_years, rate=rate, dividend_yield=dividend_yield, volatility=volatility, is_call=True)
        put = bsm_price(spot=underlying, strike=strike, time_years=time_years, rate=rate, dividend_yield=dividend_yield, volatility=volatility, is_call=False)
        expected = underlying * math.exp(-dividend_yield * time_years) - strike * math.exp(-rate * time_years)
    elif model == "BLACK_76":
        call = black76_price(forward=underlying, strike=strike, time_years=time_years, rate=rate, volatility=volatility, is_call=True)
        put = black76_price(forward=underlying, strike=strike, time_years=time_years, rate=rate, volatility=volatility, is_call=False)
        expected = math.exp(-rate * time_years) * (underlying - strike)
    else:
        raise ValueError(f"unsupported oracle model: {model}")
    return (call - put) - expected
