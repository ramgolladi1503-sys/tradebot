from __future__ import annotations

import math

from .contracts import CalculationStatus, GreeksResult, ModelInputs, OptionType, PricingModel
from .conventions import is_finite_number, year_fraction
from .normal_distribution import normal_cdf, normal_pdf
from .pricing import price_option


def calculate_greeks(inputs: ModelInputs) -> GreeksResult:
    if not isinstance(inputs.model, PricingModel):
        return _empty(inputs, CalculationStatus.INVALID_INPUT, "unsupported pricing model")
    if not isinstance(inputs.option_type, OptionType):
        return _empty(inputs, CalculationStatus.INVALID_INPUT, "unsupported option type")
    numeric = [inputs.strike, inputs.risk_free_rate, inputs.volatility, inputs.dividend_yield]
    if inputs.spot is not None:
        numeric.append(inputs.spot)
    if inputs.forward is not None:
        numeric.append(inputs.forward)
    if not all(is_finite_number(x) for x in numeric):
        return _empty(inputs, CalculationStatus.NON_FINITE_INPUT, "all numeric inputs must be finite")
    if inputs.strike <= 0 or inputs.volatility <= 0:
        return _empty(inputs, CalculationStatus.INVALID_INPUT, "positive strike and volatility are required for analytic Greeks")
    status, seconds, t = year_fraction(inputs.valuation_timestamp, inputs.expiry_timestamp, inputs.day_count)
    if status is CalculationStatus.INVALID_INPUT:
        return _empty(inputs, status, "timestamps must be timezone-aware and ordered")
    if status is CalculationStatus.EXPIRED or t is None or t <= 0:
        return _empty(inputs, CalculationStatus.EXPIRED, "analytic Greeks are undefined at expiry")
    sqrt_t = math.sqrt(t)

    if inputs.model is PricingModel.BLACK_SCHOLES_MERTON:
        if inputs.spot is None or inputs.spot <= 0:
            return _empty(inputs, CalculationStatus.INVALID_INPUT, "positive spot is required")
        s = inputs.spot
        k = inputs.strike
        r = inputs.risk_free_rate
        q = inputs.dividend_yield
        sigma = inputs.volatility
        df_r = math.exp(-r * t)
        df_q = math.exp(-q * t)
        d1 = (math.log(s / k) + (r - q + 0.5 * sigma**2) * t) / (sigma * sqrt_t)
        d2 = d1 - sigma * sqrt_t
        pdf = normal_pdf(d1)
        if inputs.option_type is OptionType.CALL:
            delta = df_q * normal_cdf(d1)
            theta = -s * df_q * pdf * sigma / (2.0 * sqrt_t) - r * k * df_r * normal_cdf(d2) + q * s * df_q * normal_cdf(d1)
            rho = k * t * df_r * normal_cdf(d2)
        else:
            delta = df_q * (normal_cdf(d1) - 1.0)
            theta = -s * df_q * pdf * sigma / (2.0 * sqrt_t) + r * k * df_r * normal_cdf(-d2) - q * s * df_q * normal_cdf(-d1)
            rho = -k * t * df_r * normal_cdf(-d2)
        gamma = df_q * pdf / (s * sigma * sqrt_t)
        vega = s * df_q * pdf * sqrt_t
        convention = "spot delta with continuous dividend yield"
    elif inputs.model is PricingModel.BLACK_76:
        if inputs.forward is None or inputs.forward <= 0:
            return _empty(inputs, CalculationStatus.INVALID_INPUT, "positive forward is required")
        f = inputs.forward
        k = inputs.strike
        r = inputs.risk_free_rate
        sigma = inputs.volatility
        df = math.exp(-r * t)
        d1 = (math.log(f / k) + 0.5 * sigma**2 * t) / (sigma * sqrt_t)
        d2 = d1 - sigma * sqrt_t
        pdf = normal_pdf(d1)
        if inputs.option_type is OptionType.CALL:
            delta = df * normal_cdf(d1)
        else:
            delta = -df * normal_cdf(-d1)
        gamma = df * pdf / (f * sigma * sqrt_t)
        vega = df * f * pdf * sqrt_t
        price = price_option(inputs)
        if price.price is None:
            return _empty(inputs, CalculationStatus.NUMERICAL_FAILURE, "price required for Black-76 theta/rho")
        theta = inputs.risk_free_rate * price.price - df * f * pdf * sigma / (2.0 * sqrt_t)
        rho = -t * price.price
        convention = "discounted forward delta; forward held constant"
    else:
        return _empty(inputs, CalculationStatus.INVALID_INPUT, "unsupported pricing model")

    values = [delta, gamma, theta, vega, rho]
    if not all(math.isfinite(v) for v in values):
        return _empty(inputs, CalculationStatus.NUMERICAL_FAILURE, "Greek calculation produced non-finite output")
    return GreeksResult(
        status=CalculationStatus.OK,
        model=inputs.model,
        option_type=inputs.option_type,
        delta=delta,
        gamma=gamma,
        theta_per_year=theta,
        theta_per_calendar_day=theta / 365.0,
        vega_per_unit_volatility=vega,
        vega_per_volatility_point=vega * 0.01,
        rho_per_unit_rate=rho,
        rho_per_rate_point=rho * 0.01,
        time_to_expiry_seconds=seconds,
        time_to_expiry_years=t,
        delta_convention=convention,
        warnings=(),
    )


def _empty(inputs: ModelInputs, status: CalculationStatus, warning: str) -> GreeksResult:
    return GreeksResult(
        status=status,
        model=inputs.model,
        option_type=inputs.option_type,
        delta=None,
        gamma=None,
        theta_per_year=None,
        theta_per_calendar_day=None,
        vega_per_unit_volatility=None,
        vega_per_volatility_point=None,
        rho_per_unit_rate=None,
        rho_per_rate_point=None,
        time_to_expiry_seconds=None,
        time_to_expiry_years=None,
        delta_convention="unavailable",
        warnings=(warning,),
    )
