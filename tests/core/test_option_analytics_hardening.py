from __future__ import annotations

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
    calculate_greeks,
    diagnose_surface,
    enrich_candidate,
    price_option,
    resolve_quote,
    solve_implied_volatility,
)

IST = ZoneInfo("Asia/Kolkata")
VAL = datetime(2026, 7, 27, 10, 0, tzinfo=IST)
EXP = datetime(2026, 7, 28, 15, 30, tzinfo=IST)


def bsm(**overrides):
    values = dict(
        model=PricingModel.BLACK_SCHOLES_MERTON,
        option_type=OptionType.CALL,
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


def quote(**overrides):
    values = dict(
        valuation_timestamp=VAL,
        quote_timestamp=VAL - timedelta(seconds=2),
        best_bid=100.0,
        best_ask=102.0,
        last_price=101.5,
        explicit_price=101.25,
        source="fixture",
    )
    values.update(overrides)
    return QuoteInput(**values)


def surface_obs(obs_id, strike, iv):
    return SurfaceObservation(
        observation_id=obs_id,
        underlying_symbol="NIFTY",
        valuation_timestamp=VAL,
        expiry_timestamp=EXP,
        option_type=OptionType.CALL,
        model=PricingModel.BLACK_76,
        strike=float(strike),
        forward=25000.0,
        implied_volatility=iv,
        solver_status=CalculationStatus.OK,
        quote_status=CalculationStatus.OK,
    )


def test_invalid_option_type_is_not_treated_as_put():
    inputs = replace(bsm(), option_type="CALL")
    assert price_option(inputs).status is CalculationStatus.INVALID_INPUT
    assert calculate_greeks(inputs).status is CalculationStatus.INVALID_INPUT


def test_invalid_model_is_typed():
    inputs = replace(bsm(), model="BLACK_SCHOLES_MERTON")
    assert price_option(inputs).status is CalculationStatus.INVALID_INPUT
    assert calculate_greeks(inputs).status is CalculationStatus.INVALID_INPUT


def test_european_carry_time_value_is_not_dishonestly_clamped():
    inputs = bsm(
        expiry_timestamp=VAL + timedelta(days=365),
        strike=80.0,
        risk_free_rate=0.0,
        volatility=0.01,
        spot=100.0,
        dividend_yield=0.50,
    )
    result = price_option(inputs)
    assert result.status is CalculationStatus.OK
    assert result.time_value == pytest.approx(result.price - result.intrinsic_value)
    assert result.time_value < 0


def test_nonfinite_iv_market_price_does_not_leak_nan():
    result = solve_implied_volatility(bsm(), float("nan"))
    assert result.status is CalculationStatus.NON_FINITE_INPUT
    assert result.market_price is None
    assert result.implied_volatility is None


def test_nonfinite_freshness_does_not_leak_nan():
    result = resolve_quote(quote(), basis=PriceBasis.MID, freshness_limit_seconds=float("nan"))
    assert result.status is CalculationStatus.INVALID_INPUT
    assert result.freshness_limit_seconds is None


def test_missing_iv_with_nominal_ok_status_is_invalid_not_ok():
    result = diagnose_surface([
        surface_obs("a", 24950, 0.20),
        surface_obs("missing", 25000, None),
        surface_obs("c", 25050, 0.21),
    ])
    by_id = {item.observation_id: item for item in result}
    assert by_id["missing"].status is CalculationStatus.INVALID_INPUT


def test_duplicate_observation_ids_are_rejected():
    result = diagnose_surface([
        surface_obs("same", 24950, 0.20),
        surface_obs("same", 25050, 0.21),
    ])
    assert all(item.status is CalculationStatus.DUPLICATE_OBSERVATION_ID for item in result)


def test_candidate_nonfinite_payload_fails_with_typed_status():
    result = enrich_candidate({"score": float("nan")}, quote=quote(), model_inputs=bsm())
    assert result.status is CalculationStatus.NON_FINITE_INPUT
    assert result.original_candidate_hash == "unavailable"
    assert result.analytics["diagnostic_flags"] == ["NON_FINITE_INPUT"]


def test_nonfinite_attribution_inputs_fail_closed():
    inputs = bsm()
    start_price = price_option(inputs).price
    start = AttributionSnapshot(
        timestamp=VAL,
        option_price=start_price,
        underlying_value=inputs.spot,
        volatility=float("nan"),
        risk_free_rate=inputs.risk_free_rate,
        greeks=calculate_greeks(inputs),
    )
    end = replace(start, timestamp=VAL + timedelta(seconds=60), option_price=start_price + 1.0)
    result = attribute_interval(start, end)
    assert result.status is CalculationStatus.NON_FINITE_INPUT
    assert math.isfinite(result.residual)
