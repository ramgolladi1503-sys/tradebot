from __future__ import annotations

import math

from .contracts import (
    CalculationStatus,
    ModelInputs,
    OptionType,
    PricingModel,
    PricingResult,
)
from .conventions import is_finite_number, year_fraction
from .normal_distribution import normal_cdf


def _invalid_result(inputs: ModelInputs, status: CalculationStatus, warning: str) -> PricingResult:
    return PricingResult(
        status=status,
        model=inputs.model,
        option_type=inputs.option_type,
        price=None,
        intrinsic_value=None,
        discounted_strike=None,
        time_value=None,
        lower_price_bound=None,
        upper_price_bound=None,
        time_to_expiry_seconds=None,
        time_to_expiry_years=None,
        warnings=(warning,),
    )


def _validate_inputs(inputs: ModelInputs) -> tuple[CalculationStatus, float | None, float | None, str | None]:
    if not isinstance(inputs.model, PricingModel):
        return CalculationStatus.INVALID_INPUT, None, None, "unsupported pricing model"
    if not isinstance(inputs.option_type, OptionType):
        return CalculationStatus.INVALID_INPUT, None, None, "unsupported option type"
    numeric = [inputs.strike, inputs.risk_free_rate, inputs.volatility, inputs.dividend_yield]
    if inputs.spot is not None:
        numeric.append(inputs.spot)
    if inputs.forward is not None:
        numeric.append(inputs.forward)
    if not all(is_finite_number(x) for x in numeric):
        return CalculationStatus.NON_FINITE_INPUT, None, None, "all numeric inputs must be finite"
    if inputs.strike <= 0:
        return CalculationStatus.INVALID_INPUT, None, None, "strike must be positive"
    if inputs.volatility < 0:
        return CalculationStatus.INVALID_INPUT, None, None, "volatility cannot be negative"
    if inputs.model is PricingModel.BLACK_SCHOLES_MERTON:
        if inputs.spot is None or inputs.spot <= 0:
            return CalculationStatus.INVALID_INPUT, None, None, "positive spot is required for Black-Scholes-Merton"
    elif inputs.model is PricingModel.BLACK_76:
        if inputs.forward is None or inputs.forward <= 0:
            return CalculationStatus.INVALID_INPUT, None, None, "positive forward is required for Black-76"
    else:
        return CalculationStatus.INVALID_INPUT, None, None, "unsupported pricing model"
    status, seconds, years = year_fraction(inputs.valuation_timestamp, inputs.expiry_timestamp, inputs.day_count)
    if status is CalculationStatus.INVALID_INPUT:
        return status, seconds, years, "valuation and expiry timestamps must be timezone-aware and ordered"
    return status, seconds, years, None


def no_arbitrage_bounds(inputs: ModelInputs) -> tuple[CalculationStatus, float | None, float | None, float | None, float | None]:
    status, seconds, years, warning = _validate_inputs(inputs)
    if status in {CalculationStatus.INVALID_INPUT, CalculationStatus.NON_FINITE_INPUT}:
        return status, None, None, seconds, years
    assert years is not None
    t = years
    if inputs.model is PricingModel.BLACK_SCHOLES_MERTON:
        assert inputs.spot is not None
        discounted_spot = inputs.spot * math.exp(-inputs.dividend_yield * t)
        discounted_strike = inputs.strike * math.exp(-inputs.risk_free_rate * t)
        if inputs.option_type is OptionType.CALL:
            lower = max(0.0, discounted_spot - discounted_strike)
            upper = discounted_spot
        else:
            lower = max(0.0, discounted_strike - discounted_spot)
            upper = discounted_strike
    else:
        assert inputs.forward is not None
        discount = math.exp(-inputs.risk_free_rate * t)
        if inputs.option_type is OptionType.CALL:
            lower = discount * max(inputs.forward - inputs.strike, 0.0)
            upper = discount * inputs.forward
        else:
            lower = discount * max(inputs.strike - inputs.forward, 0.0)
            upper = discount * inputs.strike
    return status, lower, upper, seconds, years


def price_option(inputs: ModelInputs) -> PricingResult:
    status, seconds, years, warning = _validate_inputs(inputs)
    if status in {CalculationStatus.INVALID_INPUT, CalculationStatus.NON_FINITE_INPUT}:
        return _invalid_result(inputs, status, warning or "invalid inputs")
    assert seconds is not None and years is not None
    t = years
    bounds_status, lower, upper, _, _ = no_arbitrage_bounds(inputs)
    if bounds_status in {CalculationStatus.INVALID_INPUT, CalculationStatus.NON_FINITE_INPUT}:
        return _invalid_result(inputs, bounds_status, "failed to calculate no-arbitrage bounds")
    assert lower is not None and upper is not None

    if inputs.model is PricingModel.BLACK_SCHOLES_MERTON:
        assert inputs.spot is not None
        discounted_spot = inputs.spot * math.exp(-inputs.dividend_yield * t)
        discounted_strike = inputs.strike * math.exp(-inputs.risk_free_rate * t)
        intrinsic = max(inputs.spot - inputs.strike, 0.0) if inputs.option_type is OptionType.CALL else max(inputs.strike - inputs.spot, 0.0)
        deterministic = max(discounted_spot - discounted_strike, 0.0) if inputs.option_type is OptionType.CALL else max(discounted_strike - discounted_spot, 0.0)
        if status is CalculationStatus.EXPIRED:
            price = intrinsic
        elif inputs.volatility == 0:
            price = deterministic
        else:
            sqrt_t = math.sqrt(t)
            d1 = (
                math.log(inputs.spot / inputs.strike)
                + (inputs.risk_free_rate - inputs.dividend_yield + 0.5 * inputs.volatility**2) * t
            ) / (inputs.volatility * sqrt_t)
            d2 = d1 - inputs.volatility * sqrt_t
            if inputs.option_type is OptionType.CALL:
                price = discounted_spot * normal_cdf(d1) - discounted_strike * normal_cdf(d2)
            else:
                price = discounted_strike * normal_cdf(-d2) - discounted_spot * normal_cdf(-d1)
    else:
        assert inputs.forward is not None
        discount = math.exp(-inputs.risk_free_rate * t)
        discounted_strike = inputs.strike * discount
        intrinsic = discount * (max(inputs.forward - inputs.strike, 0.0) if inputs.option_type is OptionType.CALL else max(inputs.strike - inputs.forward, 0.0))
        if status is CalculationStatus.EXPIRED or inputs.volatility == 0:
            price = intrinsic
        else:
            sqrt_t = math.sqrt(t)
            d1 = (math.log(inputs.forward / inputs.strike) + 0.5 * inputs.volatility**2 * t) / (inputs.volatility * sqrt_t)
            d2 = d1 - inputs.volatility * sqrt_t
            if inputs.option_type is OptionType.CALL:
                price = discount * (inputs.forward * normal_cdf(d1) - inputs.strike * normal_cdf(d2))
            else:
                price = discount * (inputs.strike * normal_cdf(-d2) - inputs.forward * normal_cdf(-d1))

    if not math.isfinite(price):
        return _invalid_result(inputs, CalculationStatus.NUMERICAL_FAILURE, "pricing produced a non-finite value")
    numerical_tolerance = 1e-10 * max(1.0, abs(lower), abs(upper))
    if price < lower - numerical_tolerance or price > upper + numerical_tolerance:
        return _invalid_result(inputs, CalculationStatus.NUMERICAL_FAILURE, "pricing materially violated model-consistent bounds")
    price = min(max(price, lower), upper)
    # For European options, carry can make model value minus spot intrinsic negative.
    # Preserve the signed value instead of silently clamping it.
    time_value = price - intrinsic
    return PricingResult(
        status=status,
        model=inputs.model,
        option_type=inputs.option_type,
        price=price,
        intrinsic_value=intrinsic,
        discounted_strike=inputs.strike * math.exp(-inputs.risk_free_rate * t),
        time_value=time_value,
        lower_price_bound=lower,
        upper_price_bound=upper,
        time_to_expiry_seconds=seconds,
        time_to_expiry_years=years,
        warnings=(),
    )
