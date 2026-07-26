from __future__ import annotations

from .contracts import (
    AttributionInterval,
    AttributionSnapshot,
    CalculationStatus,
    PathAttributionResult,
)
from .conventions import SECONDS_PER_ACT_365F_YEAR, is_finite_number, validate_aware_datetime


def attribute_interval(start: AttributionSnapshot, end: AttributionSnapshot) -> AttributionInterval:
    if not validate_aware_datetime(start.timestamp) or not validate_aware_datetime(end.timestamp):
        return _invalid_interval(start, end, CalculationStatus.INVALID_INPUT, "timestamps must be timezone-aware")
    if end.timestamp <= start.timestamp:
        return _invalid_interval(start, end, CalculationStatus.OUT_OF_ORDER_TIMESTAMPS, "end timestamp must be after start timestamp")
    numeric = [start.option_price, end.option_price, start.underlying_value, end.underlying_value]
    optional_numeric = [
        value
        for value in (start.volatility, end.volatility, start.risk_free_rate, end.risk_free_rate)
        if value is not None
    ]
    if not all(is_finite_number(value) for value in numeric + optional_numeric):
        return _invalid_interval(start, end, CalculationStatus.NON_FINITE_INPUT, "all provided attribution inputs must be finite")
    if start.greeks.status is not CalculationStatus.OK:
        return _invalid_interval(start, end, start.greeks.status, "start Greeks are unavailable")

    dt_years = (end.timestamp - start.timestamp).total_seconds() / SECONDS_PER_ACT_365F_YEAR
    ds = end.underlying_value - start.underlying_value
    unavailable: list[str] = []

    delta = _component(start.greeks.delta, ds)
    gamma = _quadratic_component(start.greeks.gamma, ds)
    theta = _component(start.greeks.theta_per_year, dt_years)

    if start.volatility is None or end.volatility is None or start.greeks.vega_per_unit_volatility is None:
        vega = None
        unavailable.append("vega")
    else:
        vega = start.greeks.vega_per_unit_volatility * (end.volatility - start.volatility)

    if start.risk_free_rate is None or end.risk_free_rate is None or start.greeks.rho_per_unit_rate is None:
        rho = None
        unavailable.append("rho")
    else:
        rho = start.greeks.rho_per_unit_rate * (end.risk_free_rate - start.risk_free_rate)

    for name, value in (("delta", delta), ("gamma", gamma), ("theta", theta)):
        if value is None:
            unavailable.append(name)
    available = [value for value in (delta, gamma, theta, vega, rho) if value is not None]
    explained = sum(available)
    actual = end.option_price - start.option_price
    return AttributionInterval(
        status=CalculationStatus.OK,
        start_timestamp=start.timestamp,
        end_timestamp=end.timestamp,
        actual_option_price_change=actual,
        delta_contribution=delta,
        gamma_contribution=gamma,
        theta_contribution=theta,
        vega_contribution=vega,
        rho_contribution=rho,
        explained_contribution=explained,
        residual=actual - explained,
        unavailable_components=tuple(unavailable),
    )


def attribute_path(snapshots: list[AttributionSnapshot]) -> PathAttributionResult:
    if len(snapshots) < 2:
        return PathAttributionResult(
            status=CalculationStatus.INVALID_INPUT,
            intervals=(),
            actual_option_price_change=0.0,
            explained_contribution=0.0,
            residual=0.0,
            warnings=("at least two snapshots are required",),
        )
    intervals = tuple(attribute_interval(start, end) for start, end in zip(snapshots, snapshots[1:]))
    failed = next((item for item in intervals if item.status is not CalculationStatus.OK), None)
    if failed is not None:
        return PathAttributionResult(
            status=failed.status,
            intervals=intervals,
            actual_option_price_change=snapshots[-1].option_price - snapshots[0].option_price,
            explained_contribution=sum(item.explained_contribution for item in intervals),
            residual=sum(item.residual for item in intervals),
            warnings=failed.unavailable_components,
        )
    actual = snapshots[-1].option_price - snapshots[0].option_price
    explained = sum(item.explained_contribution for item in intervals)
    return PathAttributionResult(
        status=CalculationStatus.OK,
        intervals=intervals,
        actual_option_price_change=actual,
        explained_contribution=explained,
        residual=actual - explained,
        warnings=(),
    )


def _component(greek: float | None, change: float) -> float | None:
    return None if greek is None else greek * change


def _quadratic_component(gamma: float | None, change: float) -> float | None:
    return None if gamma is None else 0.5 * gamma * change * change


def _invalid_interval(start: AttributionSnapshot, end: AttributionSnapshot, status: CalculationStatus, warning: str) -> AttributionInterval:
    return AttributionInterval(
        status=status,
        start_timestamp=start.timestamp,
        end_timestamp=end.timestamp,
        actual_option_price_change=(end.option_price - start.option_price) if is_finite_number(start.option_price) and is_finite_number(end.option_price) else 0.0,
        delta_contribution=None,
        gamma_contribution=None,
        theta_contribution=None,
        vega_contribution=None,
        rho_contribution=None,
        explained_contribution=0.0,
        residual=(end.option_price - start.option_price) if is_finite_number(start.option_price) and is_finite_number(end.option_price) else 0.0,
        unavailable_components=(warning,),
    )
