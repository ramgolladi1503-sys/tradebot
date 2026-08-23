from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from typing import Any, Mapping

from .contracts import (
    CalculationStatus,
    CandidateAnalyticsResult,
    ModelInputs,
    PriceBasis,
    QuoteInput,
    SurfaceDiagnostic,
)
from .greeks import calculate_greeks
from .implied_volatility import solve_implied_volatility
from .pricing import price_option
from .quotes import resolve_quote

ANALYTICS_SCHEMA_VERSION = "1.0.0"


def enrich_candidate(
    candidate: Mapping[str, Any],
    *,
    quote: QuoteInput,
    model_inputs: ModelInputs,
    price_basis: PriceBasis = PriceBasis.MID,
    freshness_limit_seconds: float = 8.0,
    surface_diagnostic: SurfaceDiagnostic | None = None,
) -> CandidateAnalyticsResult:
    try:
        candidate_hash = _stable_hash(candidate)
    except (TypeError, ValueError) as exc:
        status = CalculationStatus.NON_FINITE_INPUT if "Out of range float values" in str(exc) else CalculationStatus.INVALID_INPUT
        return CandidateAnalyticsResult(
            status=status,
            original_candidate_hash="unavailable",
            analytics_schema_version=ANALYTICS_SCHEMA_VERSION,
            analytics={"diagnostic_flags": [status.value]},
            warnings=(str(exc),),
        )
    quote_result = resolve_quote(quote, basis=price_basis, freshness_limit_seconds=freshness_limit_seconds)
    if quote_result.status is not CalculationStatus.OK or quote_result.market_price is None:
        return CandidateAnalyticsResult(
            status=quote_result.status,
            original_candidate_hash=candidate_hash,
            analytics_schema_version=ANALYTICS_SCHEMA_VERSION,
            analytics={
                "quote_status": quote_result.status.value,
                "market_price_basis": price_basis.value,
                "quote_age_seconds": quote_result.quote_age_seconds,
                "diagnostic_flags": [quote_result.status.value],
            },
            warnings=quote_result.warnings,
        )

    iv_result = solve_implied_volatility(model_inputs, quote_result.market_price)
    flags: list[str] = []
    analytics: dict[str, Any] = {
        "option_analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "analytics_status": iv_result.status.value,
        "pricing_model": model_inputs.model.value,
        "market_price": quote_result.market_price,
        "market_price_basis": quote_result.price_basis.value,
        "quote_source": quote_result.source,
        "quote_timestamp": quote_result.quote_timestamp.isoformat(),
        "valuation_timestamp": quote_result.valuation_timestamp.isoformat(),
        "quote_age_seconds": quote_result.quote_age_seconds,
        "spread_absolute": quote_result.spread_absolute,
        "spread_fraction_of_mid": quote_result.spread_fraction_of_mid,
        "iv_solver_status": iv_result.status.value,
        "implied_volatility": iv_result.implied_volatility,
        "iv_iterations": iv_result.iterations,
        "iv_absolute_price_error": iv_result.absolute_price_error,
        "time_to_expiry_seconds": iv_result.time_to_expiry_seconds,
        "time_to_expiry_years": iv_result.time_to_expiry_years,
    }
    if iv_result.status is not CalculationStatus.OK or iv_result.implied_volatility is None:
        flags.append(iv_result.status.value)
    else:
        solved_inputs = replace(model_inputs, volatility=iv_result.implied_volatility)
        pricing = price_option(solved_inputs)
        greek_values = calculate_greeks(solved_inputs)
        analytics.update(
            {
                "model_price_at_observed_iv": pricing.price,
                "intrinsic_value": pricing.intrinsic_value,
                "time_value": pricing.time_value,
                "delta": greek_values.delta,
                "gamma": greek_values.gamma,
                "theta_per_calendar_day": greek_values.theta_per_calendar_day,
                "vega_per_volatility_point": greek_values.vega_per_volatility_point,
                "rho_per_rate_point": greek_values.rho_per_rate_point,
                "delta_convention": greek_values.delta_convention,
            }
        )
        if greek_values.status is not CalculationStatus.OK:
            flags.append(greek_values.status.value)

    if surface_diagnostic is not None:
        analytics.update(
            {
                "surface_status": surface_diagnostic.status.value,
                "surface_neighbour_count": surface_diagnostic.neighbour_count,
                "surface_iv_residual": surface_diagnostic.absolute_iv_residual,
                "surface_robust_z_score": surface_diagnostic.robust_z_score,
            }
        )
        if surface_diagnostic.status is not CalculationStatus.OK:
            flags.append(surface_diagnostic.status.value)

    analytics["diagnostic_flags"] = sorted(set(flags))
    analytics["input_provenance"] = {
        "candidate_hash": candidate_hash,
        "instrument_token": quote.instrument_token,
        "tradingsymbol": quote.tradingsymbol,
        "quote_source": quote.source,
    }
    return CandidateAnalyticsResult(
        status=iv_result.status,
        original_candidate_hash=candidate_hash,
        analytics_schema_version=ANALYTICS_SCHEMA_VERSION,
        analytics=analytics,
        warnings=tuple(iv_result.warnings),
    )


def _stable_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=_json_default, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    try:
        return asdict(value)
    except TypeError as exc:
        raise TypeError(f"unsupported candidate value for deterministic hashing: {type(value).__name__}") from exc
