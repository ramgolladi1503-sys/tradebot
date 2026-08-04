from __future__ import annotations

import math
from dataclasses import dataclass


def _finite(value: float, *, name: str) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name}_not_finite")
    return out


@dataclass(frozen=True)
class GreekSnapshot:
    option_price: float
    underlying_price: float
    implied_volatility_points: float
    delta: float
    gamma: float
    theta_per_day: float
    vega_per_vol_point: float

    def __post_init__(self) -> None:
        for name in ("option_price", "underlying_price", "implied_volatility_points", "delta", "gamma", "theta_per_day", "vega_per_vol_point"):
            object.__setattr__(self, name, _finite(getattr(self, name), name=name))
        if self.option_price <= 0 or self.underlying_price <= 0:
            raise ValueError("greek_snapshot_prices_must_be_positive")


@dataclass(frozen=True)
class GreekAttribution:
    observed_pnl: float
    delta_contribution: float
    gamma_contribution: float
    theta_contribution: float
    vega_contribution: float
    explicit_other_contribution: float
    residual_contribution: float
    quantity: float
    elapsed_days: float
    underlying_change: float
    iv_change_points: float

    def to_record(self) -> dict[str, float]:
        return self.__dict__.copy()


def attribute_option_pnl(
    *, start: GreekSnapshot, end_option_price: float, end_underlying_price: float,
    end_implied_volatility_points: float, elapsed_days: float, quantity: float,
    explicit_other_per_option: float = 0.0,
) -> GreekAttribution:
    end_option = _finite(end_option_price, name="end_option_price")
    end_underlying = _finite(end_underlying_price, name="end_underlying_price")
    end_iv = _finite(end_implied_volatility_points, name="end_implied_volatility_points")
    elapsed = _finite(elapsed_days, name="elapsed_days")
    qty = _finite(quantity, name="quantity")
    other = _finite(explicit_other_per_option, name="explicit_other_per_option")
    if end_option <= 0 or end_underlying <= 0:
        raise ValueError("end_prices_must_be_positive")
    if elapsed < 0:
        raise ValueError("elapsed_days_negative")
    if qty <= 0:
        raise ValueError("quantity_nonpositive")
    d_underlying = end_underlying - start.underlying_price
    d_iv = end_iv - start.implied_volatility_points
    observed = (end_option - start.option_price) * qty
    delta_component = start.delta * d_underlying * qty
    gamma_component = 0.5 * start.gamma * d_underlying * d_underlying * qty
    theta_component = start.theta_per_day * elapsed * qty
    vega_component = start.vega_per_vol_point * d_iv * qty
    other_component = other * qty
    residual = observed - (delta_component + gamma_component + theta_component + vega_component + other_component)
    return GreekAttribution(observed, delta_component, gamma_component, theta_component, vega_component, other_component, residual, qty, elapsed, d_underlying, d_iv)
