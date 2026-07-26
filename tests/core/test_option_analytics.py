from __future__ import annotations

import copy
import math
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.option_analytics import (
    AttributionSnapshot,
    CalculationStatus,
    ModelInputs,
    OptionType,
    PriceBasis,
    PricingModel,
    QuoteInput,
    SurfaceObservation,
    attribute_interval,
    attribute_path,
    calculate_greeks,
    diagnose_surface,
    enrich_candidate,
    no_arbitrage_bounds,
    price_option,
    resolve_quote,
    solve_implied_volatility,
)

IST = ZoneInfo("Asia/Kolkata")
VAL = datetime(2026, 7, 27, 10, 0, tzinfo=IST)
EXP = datetime(2026, 7, 28, 15, 30, tzinfo=IST)


def bsm(option_type=OptionType.CALL, **overrides):
    values = dict(
        model=PricingModel.BLACK_SCHOLES_MERTON,
        option_type=option_type,
        valuation_timestamp=VAL,
        expiry_timestamp=EXP,
        strike=25000.0,
        risk_free_rate=0.06,
        volatility=0.20,
        spot=25050.0,
        dividend_yield=0.01,
    )
    values.update(overrides)
    return ModelInputs(**values)


def black76(option_type=OptionType.CALL, **overrides):
    values = dict(
        model=PricingModel.BLACK_76,
        option_type=option_type,
        valuation_timestamp=VAL,
        expiry_timestamp=EXP,
        strike=25000.0,
        risk_free_rate=0.06,
        volatility=0.20,
        forward=25070.0,
    )
    values.update(overrides)
    return ModelInputs(**values)


@pytest.mark.parametrize("factory", [bsm, black76])
@pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
def test_price_is_within_model_bounds(factory, option_type):
    inputs = factory(option_type)
    result = price_option(inputs)
    status, lower, upper, _, _ = no_arbitrage_bounds(inputs)
    assert status is CalculationStatus.OK
    assert result.status is CalculationStatus.OK
    assert lower <= result.price <= upper


@pytest.mark.parametrize("factory", [bsm, black76])
def test_put_call_parity(factory):
    call = price_option(factory(OptionType.CALL))
    put = price_option(factory(OptionType.PUT))
    t = call.time_to_expiry_years
    assert t is not None
    if factory is bsm:
        rhs = 25050.0 * math.exp(-0.01 * t) - 25000.0 * math.exp(-0.06 * t)
    else:
        rhs = math.exp(-0.06 * t) * (25070.0 - 25000.0)
    assert call.price - put.price == pytest.approx(rhs, abs=1e-9)


@pytest.mark.parametrize("factory", [bsm, black76])
@pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
def test_price_increases_with_volatility(factory, option_type):
    low = price_option(factory(option_type, volatility=0.10)).price
    high = price_option(factory(option_type, volatility=0.40)).price
    assert high >= low


def test_call_increases_and_put_decreases_with_spot():
    assert price_option(bsm(OptionType.CALL, spot=25100)).price > price_option(bsm(OptionType.CALL, spot=24900)).price
    assert price_option(bsm(OptionType.PUT, spot=25100)).price < price_option(bsm(OptionType.PUT, spot=24900)).price


def test_black76_call_increases_and_put_decreases_with_forward():
    assert price_option(black76(OptionType.CALL, forward=25100)).price > price_option(black76(OptionType.CALL, forward=24900)).price
    assert price_option(black76(OptionType.PUT, forward=25100)).price < price_option(black76(OptionType.PUT, forward=24900)).price


@pytest.mark.parametrize("factory", [bsm, black76])
@pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
def test_zero_volatility_returns_deterministic_value(factory, option_type):
    result = price_option(factory(option_type, volatility=0.0))
    assert result.status is CalculationStatus.OK
    assert result.price == pytest.approx(result.lower_price_bound)


@pytest.mark.parametrize("factory", [bsm, black76])
@pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
def test_expiry_returns_intrinsic(factory, option_type):
    inputs = factory(option_type, expiry_timestamp=VAL)
    result = price_option(inputs)
    assert result.status is CalculationStatus.EXPIRED
    assert result.price == pytest.approx(result.intrinsic_value)


@pytest.mark.parametrize(
    "inputs,status",
    [
        (bsm(spot=0), CalculationStatus.INVALID_INPUT),
        (black76(forward=0), CalculationStatus.INVALID_INPUT),
        (bsm(strike=-1), CalculationStatus.INVALID_INPUT),
        (bsm(volatility=-0.1), CalculationStatus.INVALID_INPUT),
        (bsm(spot=float("nan")), CalculationStatus.NON_FINITE_INPUT),
        (bsm(valuation_timestamp=VAL.replace(tzinfo=None)), CalculationStatus.INVALID_INPUT),
        (bsm(expiry_timestamp=VAL - timedelta(seconds=1)), CalculationStatus.INVALID_INPUT),
    ],
)
def test_invalid_pricing_inputs_are_typed(inputs, status):
    result = price_option(inputs)
    assert result.status is status
    assert result.price is None


@pytest.mark.parametrize("factory", [bsm, black76])
@pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
@pytest.mark.parametrize("vol", [0.05, 0.20, 0.80])
def test_implied_volatility_round_trip(factory, option_type, vol):
    inputs = factory(option_type, volatility=vol)
    market = price_option(inputs).price
    solved = solve_implied_volatility(replace(inputs, volatility=0.3), market)
    assert solved.status is CalculationStatus.OK
    assert solved.converged
    assert solved.implied_volatility == pytest.approx(vol, abs=2e-8)
    assert solved.absolute_price_error <= 1e-7


def test_iv_outside_bounds_fails_without_clipping():
    inputs = bsm()
    _, _, upper, _, _ = no_arbitrage_bounds(inputs)
    result = solve_implied_volatility(inputs, upper + 1.0)
    assert result.status is CalculationStatus.OUTSIDE_NO_ARBITRAGE_BOUNDS
    assert result.implied_volatility is None
    assert not result.converged


def test_iv_lower_bound_is_explicit_zero_volatility_solution():
    inputs = bsm()
    _, lower, _, _, _ = no_arbitrage_bounds(inputs)
    result = solve_implied_volatility(inputs, lower)
    assert result.status is CalculationStatus.OK
    assert result.implied_volatility == 0.0
    assert result.solver == "lower-bound-zero-volatility"


def test_iv_not_bracketed_is_typed():
    inputs = bsm(volatility=2.0)
    market = price_option(inputs).price
    result = solve_implied_volatility(inputs, market, max_volatility=0.2)
    assert result.status is CalculationStatus.NOT_BRACKETED
    assert result.implied_volatility is None


def test_iv_max_iterations_is_typed():
    inputs = bsm(volatility=0.333333)
    market = price_option(inputs).price
    result = solve_implied_volatility(inputs, market, max_iterations=1, price_tolerance=1e-30, volatility_tolerance=1e-30)
    assert result.status is CalculationStatus.MAX_ITERATIONS
    assert result.implied_volatility is None


def finite_difference(inputs: ModelInputs, field: str, h: float) -> float:
    up = price_option(replace(inputs, **{field: getattr(inputs, field) + h})).price
    down = price_option(replace(inputs, **{field: getattr(inputs, field) - h})).price
    return (up - down) / (2.0 * h)


def theta_fd(inputs: ModelInputs, seconds: float = 10.0) -> float:
    later = replace(inputs, valuation_timestamp=inputs.valuation_timestamp + timedelta(seconds=seconds))
    p0 = price_option(inputs).price
    p1 = price_option(later).price
    return (p1 - p0) / (seconds / (365.0 * 24.0 * 3600.0))


@pytest.mark.parametrize("factory,underlying_field", [(bsm, "spot"), (black76, "forward")])
@pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
def test_analytic_greeks_match_independent_finite_differences(factory, underlying_field, option_type):
    inputs = factory(option_type, volatility=0.27)
    greeks = calculate_greeks(inputs)
    assert greeks.status is CalculationStatus.OK
    delta_fd = finite_difference(inputs, underlying_field, 0.01)
    p_up = price_option(replace(inputs, **{underlying_field: getattr(inputs, underlying_field) + 0.5})).price
    p_mid = price_option(inputs).price
    p_down = price_option(replace(inputs, **{underlying_field: getattr(inputs, underlying_field) - 0.5})).price
    gamma_fd = (p_up - 2 * p_mid + p_down) / (0.5**2)
    vega_fd = finite_difference(inputs, "volatility", 1e-5)
    rho_fd = finite_difference(inputs, "risk_free_rate", 1e-6)
    assert greeks.delta == pytest.approx(delta_fd, rel=2e-5, abs=2e-6)
    assert greeks.gamma == pytest.approx(gamma_fd, rel=2e-4, abs=2e-7)
    assert greeks.vega_per_unit_volatility == pytest.approx(vega_fd, rel=2e-5, abs=2e-5)
    assert greeks.rho_per_unit_rate == pytest.approx(rho_fd, rel=3e-4, abs=2e-3)
    assert greeks.theta_per_year == pytest.approx(theta_fd(inputs), rel=5e-4, abs=0.2)


def test_greek_units_are_explicit_and_scaled():
    result = calculate_greeks(bsm())
    assert result.theta_per_calendar_day == pytest.approx(result.theta_per_year / 365.0)
    assert result.vega_per_volatility_point == pytest.approx(result.vega_per_unit_volatility * 0.01)
    assert result.rho_per_rate_point == pytest.approx(result.rho_per_unit_rate * 0.01)


def test_put_theta_interest_term_matches_finite_difference():
    inputs = bsm(OptionType.PUT, spot=24800, volatility=0.30)
    result = calculate_greeks(inputs)
    assert result.theta_per_year == pytest.approx(theta_fd(inputs), rel=5e-4, abs=0.2)


def quote(**overrides):
    values = dict(
        valuation_timestamp=VAL,
        quote_timestamp=VAL - timedelta(seconds=2),
        best_bid=100.0,
        best_ask=102.0,
        last_price=101.5,
        explicit_price=101.25,
        source="fixture",
        instrument_token=123,
        tradingsymbol="NIFTY26JUL25000CE",
    )
    values.update(overrides)
    return QuoteInput(**values)


def test_quote_midpoint_provenance():
    result = resolve_quote(quote(), basis=PriceBasis.MID, freshness_limit_seconds=8)
    assert result.status is CalculationStatus.OK
    assert result.market_price == 101.0
    assert result.spread_absolute == 2.0
    assert result.spread_fraction_of_mid == pytest.approx(2 / 101)


def test_stale_mid_does_not_fall_back_to_last():
    result = resolve_quote(quote(quote_timestamp=VAL - timedelta(seconds=9)), basis=PriceBasis.MID, freshness_limit_seconds=8)
    assert result.status is CalculationStatus.QUOTE_STALE
    assert result.market_price is None


def test_crossed_market_is_rejected():
    result = resolve_quote(quote(best_bid=103, best_ask=102), basis=PriceBasis.MID, freshness_limit_seconds=8)
    assert result.status is CalculationStatus.QUOTE_CROSSED
    assert result.market_price is None


def test_locked_market_is_valid():
    result = resolve_quote(quote(best_bid=101, best_ask=101), basis=PriceBasis.MID, freshness_limit_seconds=8)
    assert result.status is CalculationStatus.OK
    assert result.locked_market


def test_missing_requested_price_is_typed():
    result = resolve_quote(quote(best_bid=None, best_ask=None), basis=PriceBasis.MID, freshness_limit_seconds=8)
    assert result.status is CalculationStatus.PRICE_UNAVAILABLE


def surface_obs(obs_id, strike, iv, option_type=OptionType.CALL, expiry=EXP, status=CalculationStatus.OK):
    return SurfaceObservation(
        observation_id=obs_id,
        underlying_symbol="NIFTY",
        valuation_timestamp=VAL,
        expiry_timestamp=expiry,
        option_type=option_type,
        model=PricingModel.BLACK_76,
        strike=float(strike),
        forward=25000.0,
        implied_volatility=iv,
        solver_status=status,
        quote_status=CalculationStatus.OK,
    )


def test_surface_diagnostics_are_partitioned_and_deterministic():
    observations = [
        surface_obs("a", 24900, 0.20),
        surface_obs("b", 24950, 0.21),
        surface_obs("c", 25000, 0.25),
        surface_obs("d", 25050, 0.22),
        surface_obs("e", 25100, 0.21),
        surface_obs("put", 25000, 0.50, option_type=OptionType.PUT),
        surface_obs("next", 25000, 0.60, expiry=EXP + timedelta(days=7)),
    ]
    first = diagnose_surface(observations)
    second = diagnose_surface(list(observations))
    assert first == second
    by_id = {item.observation_id: item for item in first}
    assert by_id["c"].status is CalculationStatus.OK
    assert by_id["c"].local_median_iv == pytest.approx(0.21)
    assert by_id["put"].status is CalculationStatus.INSUFFICIENT_SURFACE_NEIGHBOURS
    assert by_id["next"].status is CalculationStatus.INSUFFICIENT_SURFACE_NEIGHBOURS


def test_duplicate_strike_is_rejected():
    result = diagnose_surface([surface_obs("a", 25000, 0.2), surface_obs("b", 25000, 0.21)])
    assert all(item.status is CalculationStatus.DUPLICATE_STRIKE for item in result)


def test_invalid_iv_is_preserved_as_failed_row():
    result = diagnose_surface([surface_obs("a", 24950, 0.2), surface_obs("bad", 25000, None, status=CalculationStatus.NOT_BRACKETED), surface_obs("c", 25050, 0.21)])
    by_id = {item.observation_id: item for item in result}
    assert by_id["bad"].status is CalculationStatus.NOT_BRACKETED


def test_candidate_enrichment_does_not_mutate_or_rewrite_strategy_fields():
    inputs = bsm(volatility=0.2)
    market = price_option(inputs).price
    candidate = {"strategy": "ORB", "eligible": True, "rank": 2, "signal": "LONG", "nested": {"x": 1}}
    before = copy.deepcopy(candidate)
    result = enrich_candidate(candidate, quote=quote(best_bid=market - 0.1, best_ask=market + 0.1), model_inputs=replace(inputs, volatility=0.3))
    assert candidate == before
    assert result.status is CalculationStatus.OK
    assert "eligible" not in result.analytics
    assert "rank" not in result.analytics
    assert "signal" not in result.analytics
    assert result.analytics["iv_solver_status"] == "OK"


def test_candidate_enrichment_stale_quote_fails_closed():
    result = enrich_candidate({}, quote=quote(quote_timestamp=VAL - timedelta(seconds=20)), model_inputs=bsm())
    assert result.status is CalculationStatus.QUOTE_STALE
    assert result.analytics["diagnostic_flags"] == ["QUOTE_STALE"]


def test_candidate_hash_is_deterministic_across_key_order():
    inputs = bsm()
    market = price_option(inputs).price
    q = quote(best_bid=market - 0.1, best_ask=market + 0.1)
    a = enrich_candidate({"b": 2, "a": 1}, quote=q, model_inputs=inputs)
    b = enrich_candidate({"a": 1, "b": 2}, quote=q, model_inputs=inputs)
    assert a.original_candidate_hash == b.original_candidate_hash


def snapshots_for_move(ds=10.0, dvol=0.0, dt_seconds=60.0):
    start_inputs = bsm(volatility=0.2)
    start_price = price_option(start_inputs).price
    start_greeks = calculate_greeks(start_inputs)
    end_inputs = replace(
        start_inputs,
        valuation_timestamp=start_inputs.valuation_timestamp + timedelta(seconds=dt_seconds),
        spot=start_inputs.spot + ds,
        volatility=start_inputs.volatility + dvol,
    )
    end_price = price_option(end_inputs).price
    return [
        AttributionSnapshot(VAL, start_price, start_inputs.spot, start_inputs.volatility, start_inputs.risk_free_rate, start_greeks),
        AttributionSnapshot(VAL + timedelta(seconds=dt_seconds), end_price, end_inputs.spot, end_inputs.volatility, end_inputs.risk_free_rate, calculate_greeks(end_inputs)),
    ]


@pytest.mark.parametrize("ds", [10.0, -10.0])
def test_attribution_reconciles_directional_move(ds):
    start, end = snapshots_for_move(ds=ds)
    result = attribute_interval(start, end)
    assert result.status is CalculationStatus.OK
    assert result.actual_option_price_change == pytest.approx(result.explained_contribution + result.residual)
    assert "APPROXIMATION_NOT_CAUSAL" in result.limitations


@pytest.mark.parametrize("dvol", [0.02, -0.02])
def test_attribution_reconciles_volatility_move(dvol):
    start, end = snapshots_for_move(ds=0, dvol=dvol)
    result = attribute_interval(start, end)
    assert result.status is CalculationStatus.OK
    assert result.vega_contribution is not None
    assert result.actual_option_price_change == pytest.approx(result.explained_contribution + result.residual)


def test_attribution_missing_iv_is_not_silently_zero():
    start, end = snapshots_for_move()
    start = replace(start, volatility=None)
    result = attribute_interval(start, end)
    assert result.vega_contribution is None
    assert "vega" in result.unavailable_components


def test_path_attribution_equals_sum_of_intervals():
    first, second = snapshots_for_move(ds=5, dvol=0.01, dt_seconds=60)
    mid_inputs = bsm(spot=first.underlying_value + 2, volatility=0.205, valuation_timestamp=VAL + timedelta(seconds=30))
    mid = AttributionSnapshot(
        VAL + timedelta(seconds=30),
        price_option(mid_inputs).price,
        mid_inputs.spot,
        mid_inputs.volatility,
        mid_inputs.risk_free_rate,
        calculate_greeks(mid_inputs),
    )
    result = attribute_path([first, mid, second])
    assert result.status is CalculationStatus.OK
    assert result.actual_option_price_change == pytest.approx(sum(i.actual_option_price_change for i in result.intervals))
    assert result.explained_contribution == pytest.approx(sum(i.explained_contribution for i in result.intervals))
    assert result.residual == pytest.approx(result.actual_option_price_change - result.explained_contribution)


def test_out_of_order_attribution_fails():
    start, end = snapshots_for_move()
    result = attribute_interval(end, start)
    assert result.status is CalculationStatus.OUT_OF_ORDER_TIMESTAMPS


def test_exact_intraday_time_to_expiry_not_integer_days():
    inputs = bsm(expiry_timestamp=VAL + timedelta(hours=5, minutes=30))
    result = price_option(inputs)
    assert result.time_to_expiry_seconds == 19800
    assert result.time_to_expiry_years == pytest.approx(19800 / (365 * 24 * 3600))
