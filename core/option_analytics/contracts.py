from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class PricingModel(str, Enum):
    BLACK_SCHOLES_MERTON = "BLACK_SCHOLES_MERTON"
    BLACK_76 = "BLACK_76"


class CalculationStatus(str, Enum):
    OK = "OK"
    INVALID_INPUT = "INVALID_INPUT"
    NON_FINITE_INPUT = "NON_FINITE_INPUT"
    EXPIRED = "EXPIRED"
    OUTSIDE_NO_ARBITRAGE_BOUNDS = "OUTSIDE_NO_ARBITRAGE_BOUNDS"
    NOT_BRACKETED = "NOT_BRACKETED"
    MAX_ITERATIONS = "MAX_ITERATIONS"
    NUMERICAL_FAILURE = "NUMERICAL_FAILURE"
    QUOTE_INVALID = "QUOTE_INVALID"
    QUOTE_STALE = "QUOTE_STALE"
    QUOTE_CROSSED = "QUOTE_CROSSED"
    PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"
    INSUFFICIENT_SURFACE_NEIGHBOURS = "INSUFFICIENT_SURFACE_NEIGHBOURS"
    DUPLICATE_STRIKE = "DUPLICATE_STRIKE"
    DUPLICATE_OBSERVATION_ID = "DUPLICATE_OBSERVATION_ID"
    OUT_OF_ORDER_TIMESTAMPS = "OUT_OF_ORDER_TIMESTAMPS"


class PriceBasis(str, Enum):
    MID = "MID"
    BID = "BID"
    ASK = "ASK"
    LAST = "LAST"
    EXPLICIT = "EXPLICIT"


class DayCountConvention(str, Enum):
    ACT_365F = "ACT_365F"


@dataclass(frozen=True)
class ModelInputs:
    model: PricingModel
    option_type: OptionType
    valuation_timestamp: datetime
    expiry_timestamp: datetime
    strike: float
    risk_free_rate: float
    volatility: float
    spot: float | None = None
    forward: float | None = None
    dividend_yield: float = 0.0
    day_count: DayCountConvention = DayCountConvention.ACT_365F


@dataclass(frozen=True)
class PricingResult:
    status: CalculationStatus
    model: PricingModel
    option_type: OptionType
    price: float | None
    intrinsic_value: float | None
    discounted_strike: float | None
    time_value: float | None
    lower_price_bound: float | None
    upper_price_bound: float | None
    time_to_expiry_seconds: float | None
    time_to_expiry_years: float | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class GreeksResult:
    status: CalculationStatus
    model: PricingModel
    option_type: OptionType
    delta: float | None
    gamma: float | None
    theta_per_year: float | None
    theta_per_calendar_day: float | None
    vega_per_unit_volatility: float | None
    vega_per_volatility_point: float | None
    rho_per_unit_rate: float | None
    rho_per_rate_point: float | None
    time_to_expiry_seconds: float | None
    time_to_expiry_years: float | None
    delta_convention: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImpliedVolatilityResult:
    status: CalculationStatus
    model: PricingModel
    option_type: OptionType
    implied_volatility: float | None
    converged: bool
    iterations: int
    absolute_price_error: float | None
    lower_volatility_bound: float
    upper_volatility_bound: float
    market_price: float | None
    lower_price_bound: float | None
    upper_price_bound: float | None
    solver: str
    time_to_expiry_seconds: float | None
    time_to_expiry_years: float | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuoteInput:
    valuation_timestamp: datetime
    quote_timestamp: datetime
    best_bid: float | None = None
    best_ask: float | None = None
    last_price: float | None = None
    explicit_price: float | None = None
    source: str = "UNKNOWN"
    instrument_token: int | None = None
    tradingsymbol: str | None = None


@dataclass(frozen=True)
class QuoteResult:
    status: CalculationStatus
    price_basis: PriceBasis
    market_price: float | None
    best_bid: float | None
    best_ask: float | None
    last_price: float | None
    mid_price: float | None
    spread_absolute: float | None
    spread_fraction_of_mid: float | None
    quote_age_seconds: float | None
    freshness_limit_seconds: float | None
    locked_market: bool
    crossed_market: bool
    source: str
    quote_timestamp: datetime
    valuation_timestamp: datetime
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SurfaceObservation:
    observation_id: str
    underlying_symbol: str
    valuation_timestamp: datetime
    expiry_timestamp: datetime
    option_type: OptionType
    model: PricingModel
    strike: float
    forward: float
    implied_volatility: float | None
    solver_status: CalculationStatus
    quote_status: CalculationStatus


@dataclass(frozen=True)
class SurfaceDiagnostic:
    observation_id: str
    status: CalculationStatus
    log_moneyness: float | None
    neighbour_count: int
    local_median_iv: float | None
    absolute_iv_residual: float | None
    relative_iv_residual: float | None
    robust_scale: float | None
    robust_z_score: float | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateAnalyticsResult:
    status: CalculationStatus
    original_candidate_hash: str
    analytics_schema_version: str
    analytics: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttributionSnapshot:
    timestamp: datetime
    option_price: float
    underlying_value: float
    volatility: float | None
    risk_free_rate: float | None
    greeks: GreeksResult


@dataclass(frozen=True)
class AttributionInterval:
    status: CalculationStatus
    start_timestamp: datetime
    end_timestamp: datetime
    actual_option_price_change: float
    delta_contribution: float | None
    gamma_contribution: float | None
    theta_contribution: float | None
    vega_contribution: float | None
    rho_contribution: float | None
    explained_contribution: float
    residual: float
    unavailable_components: tuple[str, ...]
    limitations: tuple[str, ...] = (
        "APPROXIMATION_NOT_CAUSAL",
        "DISCRETE_PATH_DEPENDENT",
        "HIGHER_ORDER_AND_CROSS_GREEKS_IN_RESIDUAL",
    )


@dataclass(frozen=True)
class PathAttributionResult:
    status: CalculationStatus
    intervals: tuple[AttributionInterval, ...]
    actual_option_price_change: float
    explained_contribution: float
    residual: float
    warnings: tuple[str, ...] = ()
