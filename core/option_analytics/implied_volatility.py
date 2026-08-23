from __future__ import annotations

import math
from dataclasses import replace

from .contracts import CalculationStatus, ImpliedVolatilityResult, ModelInputs
from .conventions import is_finite_number
from .pricing import no_arbitrage_bounds, price_option


def solve_implied_volatility(
    base_inputs: ModelInputs,
    market_price: float,
    *,
    min_volatility: float = 0.0,
    max_volatility: float = 5.0,
    price_tolerance: float = 1e-8,
    volatility_tolerance: float = 1e-10,
    bound_tolerance: float = 1e-10,
    max_iterations: int = 200,
) -> ImpliedVolatilityResult:
    if not all(
        is_finite_number(x)
        for x in (
            market_price,
            min_volatility,
            max_volatility,
            price_tolerance,
            volatility_tolerance,
            bound_tolerance,
        )
    ):
        return _result(base_inputs, market_price, CalculationStatus.NON_FINITE_INPUT, False, 0, None, min_volatility, max_volatility, None, None, "bisection", "solver inputs must be finite")
    if market_price < 0 or min_volatility < 0 or max_volatility <= min_volatility or price_tolerance <= 0 or volatility_tolerance <= 0 or bound_tolerance < 0 or max_iterations <= 0:
        return _result(base_inputs, market_price, CalculationStatus.INVALID_INPUT, False, 0, None, min_volatility, max_volatility, None, None, "bisection", "invalid solver controls")

    zero_inputs = replace(base_inputs, volatility=0.0)
    bounds_status, lower, upper, seconds, years = no_arbitrage_bounds(zero_inputs)
    if bounds_status in {CalculationStatus.INVALID_INPUT, CalculationStatus.NON_FINITE_INPUT}:
        return _result(base_inputs, market_price, bounds_status, False, 0, None, min_volatility, max_volatility, lower, upper, "bisection", "invalid model inputs", seconds, years)
    if bounds_status is CalculationStatus.EXPIRED:
        return _result(base_inputs, market_price, CalculationStatus.EXPIRED, False, 0, None, min_volatility, max_volatility, lower, upper, "bisection", "implied volatility is undefined at expiry", seconds, years)
    assert lower is not None and upper is not None
    if market_price < lower - bound_tolerance or market_price > upper + bound_tolerance:
        return _result(base_inputs, market_price, CalculationStatus.OUTSIDE_NO_ARBITRAGE_BOUNDS, False, 0, None, min_volatility, max_volatility, lower, upper, "bisection", "market price is outside model-consistent no-arbitrage bounds", seconds, years)
    if abs(market_price - lower) <= max(price_tolerance, bound_tolerance):
        return _result(base_inputs, market_price, CalculationStatus.OK, True, 0, 0.0, min_volatility, max_volatility, lower, upper, "lower-bound-zero-volatility", None, seconds, years, 0.0)

    low = max(min_volatility, 0.0)
    high = max_volatility
    low_price_result = price_option(replace(base_inputs, volatility=low))
    high_price_result = price_option(replace(base_inputs, volatility=high))
    if low_price_result.price is None or high_price_result.price is None:
        return _result(base_inputs, market_price, CalculationStatus.NUMERICAL_FAILURE, False, 0, None, low, high, lower, upper, "bisection", "failed to evaluate solver bracket", seconds, years)
    low_value = low_price_result.price - market_price
    high_value = high_price_result.price - market_price
    if low_value > price_tolerance:
        return _result(base_inputs, market_price, CalculationStatus.NOT_BRACKETED, False, 0, None, low, high, lower, upper, "bisection", "minimum volatility price exceeds market price", seconds, years, abs(low_value))
    if high_value < -price_tolerance:
        return _result(base_inputs, market_price, CalculationStatus.NOT_BRACKETED, False, 0, None, low, high, lower, upper, "bisection", "maximum volatility does not bracket the market price", seconds, years, abs(high_value))

    midpoint = None
    error = None
    for iteration in range(1, max_iterations + 1):
        midpoint = 0.5 * (low + high)
        mid_result = price_option(replace(base_inputs, volatility=midpoint))
        if mid_result.price is None or not math.isfinite(mid_result.price):
            return _result(base_inputs, market_price, CalculationStatus.NUMERICAL_FAILURE, False, iteration, None, min_volatility, max_volatility, lower, upper, "bisection", "non-finite midpoint price", seconds, years)
        difference = mid_result.price - market_price
        error = abs(difference)
        if error <= price_tolerance or (high - low) <= volatility_tolerance:
            return _result(base_inputs, market_price, CalculationStatus.OK, True, iteration, midpoint, min_volatility, max_volatility, lower, upper, "bisection", None, seconds, years, error)
        if difference > 0:
            high = midpoint
        else:
            low = midpoint

    return _result(base_inputs, market_price, CalculationStatus.MAX_ITERATIONS, False, max_iterations, None, min_volatility, max_volatility, lower, upper, "bisection", "maximum iterations reached without convergence", seconds, years, error)


def _result(
    inputs: ModelInputs,
    market_price: float,
    status: CalculationStatus,
    converged: bool,
    iterations: int,
    implied_volatility: float | None,
    lower_volatility_bound: float,
    upper_volatility_bound: float,
    lower_price_bound: float | None,
    upper_price_bound: float | None,
    solver: str,
    warning: str | None,
    seconds: float | None = None,
    years: float | None = None,
    error: float | None = None,
) -> ImpliedVolatilityResult:
    safe_market_price = float(market_price) if is_finite_number(market_price) else None
    return ImpliedVolatilityResult(
        status=status,
        model=inputs.model,
        option_type=inputs.option_type,
        implied_volatility=implied_volatility,
        converged=converged,
        iterations=iterations,
        absolute_price_error=error,
        lower_volatility_bound=lower_volatility_bound,
        upper_volatility_bound=upper_volatility_bound,
        market_price=safe_market_price,
        lower_price_bound=lower_price_bound,
        upper_price_bound=upper_price_bound,
        solver=solver,
        time_to_expiry_seconds=seconds,
        time_to_expiry_years=years,
        warnings=(warning,) if warning else (),
    )
