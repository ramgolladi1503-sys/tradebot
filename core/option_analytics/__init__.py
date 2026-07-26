"""Production-grade European option analytics primitives.

This package is calculation-only. It does not place orders, select contracts,
change strategy signals, or claim that model residuals are executable edge.
"""

from .attribution import attribute_interval, attribute_path
from .contracts import (
    AttributionInterval,
    AttributionSnapshot,
    CalculationStatus,
    CandidateAnalyticsResult,
    DayCountConvention,
    GreeksResult,
    ImpliedVolatilityResult,
    ModelInputs,
    OptionType,
    PathAttributionResult,
    PriceBasis,
    PricingModel,
    PricingResult,
    QuoteInput,
    QuoteResult,
    SurfaceDiagnostic,
    SurfaceObservation,
)
from .diagnostics import ANALYTICS_SCHEMA_VERSION, enrich_candidate
from .greeks import calculate_greeks
from .implied_volatility import solve_implied_volatility
from .pricing import no_arbitrage_bounds, price_option
from .quotes import resolve_quote
from .surface import diagnose_surface

__all__ = [
    "ANALYTICS_SCHEMA_VERSION",
    "AttributionInterval",
    "AttributionSnapshot",
    "CalculationStatus",
    "CandidateAnalyticsResult",
    "DayCountConvention",
    "GreeksResult",
    "ImpliedVolatilityResult",
    "ModelInputs",
    "OptionType",
    "PathAttributionResult",
    "PriceBasis",
    "PricingModel",
    "PricingResult",
    "QuoteInput",
    "QuoteResult",
    "SurfaceDiagnostic",
    "SurfaceObservation",
    "attribute_interval",
    "attribute_path",
    "calculate_greeks",
    "diagnose_surface",
    "enrich_candidate",
    "no_arbitrage_bounds",
    "price_option",
    "resolve_quote",
    "solve_implied_volatility",
]
