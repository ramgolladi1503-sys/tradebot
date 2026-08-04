from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Iterable, Sequence

from .market_analytics import BookLevel


def _finite(value: float, *, name: str) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name}_not_finite")
    return out


@dataclass(frozen=True)
class FillSimulation:
    requested_quantity: float
    filled_quantity: float
    unfilled_quantity: float
    vwap: float | None
    top_price: float | None
    worst_price: float | None
    impact_bps_vs_top: float | None
    levels_consumed: int

    @property
    def fully_filled(self) -> bool:
        return self.unfilled_quantity == 0.0

    def to_record(self) -> dict[str, object]:
        return {**self.__dict__, "fully_filled": self.fully_filled}


def simulate_market_fill(levels: Sequence[BookLevel], *, quantity: float, side: str) -> FillSimulation:
    requested = _finite(quantity, name="quantity")
    if requested <= 0:
        raise ValueError("quantity_nonpositive")
    normalized_side = side.strip().upper()
    if normalized_side not in {"BUY", "SELL"}:
        raise ValueError("side_must_be_buy_or_sell")
    if not levels:
        return FillSimulation(requested, 0.0, requested, None, None, None, None, 0)
    prices = [level.price for level in levels]
    if normalized_side == "BUY" and prices != sorted(prices):
        raise ValueError("buy_levels_must_be_ascending")
    if normalized_side == "SELL" and prices != sorted(prices, reverse=True):
        raise ValueError("sell_levels_must_be_descending")
    remaining = requested
    notional = 0.0
    filled = 0.0
    worst: float | None = None
    consumed = 0
    for level in levels:
        if remaining <= 0:
            break
        take = min(remaining, level.quantity)
        if take <= 0:
            continue
        notional += take * level.price
        filled += take
        remaining -= take
        worst = level.price
        consumed += 1
    top = levels[0].price
    vwap = notional / filled if filled > 0 else None
    impact = None
    if vwap is not None:
        signed_move = (vwap - top) if normalized_side == "BUY" else (top - vwap)
        impact = signed_move / top * 10_000.0
    return FillSimulation(requested, filled, max(remaining, 0.0), vwap, top, worst, impact, consumed)


def build_capacity_curve(levels: Sequence[BookLevel], *, quantities: Iterable[float], side: str) -> list[FillSimulation]:
    values = [_finite(value, name="capacity_quantity") for value in quantities]
    if not values:
        raise ValueError("capacity_quantities_empty")
    if any(value <= 0 for value in values):
        raise ValueError("capacity_quantity_nonpositive")
    if values != sorted(values):
        raise ValueError("capacity_quantities_must_be_ascending")
    return [simulate_market_fill(levels, quantity=value, side=side) for value in values]


@dataclass(frozen=True)
class QueueObservation:
    quantity_ahead: float
    traded_at_price: float
    cancelled_ahead: float
    filled: bool

    def depletion_ratio(self) -> float:
        ahead = _finite(self.quantity_ahead, name="quantity_ahead")
        traded = _finite(self.traded_at_price, name="traded_at_price")
        cancelled = _finite(self.cancelled_ahead, name="cancelled_ahead")
        if ahead <= 0 or traded < 0 or cancelled < 0:
            raise ValueError("queue_observation_invalid")
        return (traded + cancelled) / ahead


@dataclass(frozen=True)
class QueueBucket:
    lower_inclusive: float
    upper_exclusive: float
    observations: int
    fills: int
    fill_probability: float
    wilson_low: float
    wilson_high: float


def _wilson_interval(successes: int, total: int, confidence: float) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("wilson_total_nonpositive")
    if not 0 < confidence < 1:
        raise ValueError("confidence_out_of_range")
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denominator
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def calibrate_queue_fill_probability(observations: Iterable[QueueObservation], *, bucket_edges: Sequence[float], confidence: float) -> list[QueueBucket]:
    edges = [_finite(edge, name="bucket_edge") for edge in bucket_edges]
    if len(edges) < 2 or edges != sorted(edges) or len(set(edges)) != len(edges):
        raise ValueError("bucket_edges_invalid")
    rows = list(observations)
    buckets: list[QueueBucket] = []
    for lower, upper in zip(edges, edges[1:]):
        selected = [row for row in rows if lower <= row.depletion_ratio() < upper]
        if not selected:
            continue
        fills = sum(row.filled for row in selected)
        low, high = _wilson_interval(fills, len(selected), confidence)
        buckets.append(QueueBucket(lower, upper, len(selected), fills, fills / len(selected), low, high))
    return buckets


@dataclass(frozen=True)
class MarketImpactObservation:
    participation_rate: float
    impact_bps: float

    def transformed_participation(self) -> float:
        participation = _finite(self.participation_rate, name="participation_rate")
        if participation < 0:
            raise ValueError("participation_rate_negative")
        return math.sqrt(participation)


@dataclass(frozen=True)
class SqrtImpactModel:
    coefficient: float
    observations: int
    r_squared: float | None

    def predict_bps(self, participation_rate: float) -> float:
        value = _finite(participation_rate, name="participation_rate")
        if value < 0:
            raise ValueError("participation_rate_negative")
        return self.coefficient * math.sqrt(value)


def fit_sqrt_impact_model(observations: Iterable[MarketImpactObservation]) -> SqrtImpactModel:
    rows = list(observations)
    if len(rows) < 2:
        raise ValueError("insufficient_market_impact_observations")
    xs = [row.transformed_participation() for row in rows]
    ys = [_finite(row.impact_bps, name="impact_bps") for row in rows]
    denominator = sum(value * value for value in xs)
    if denominator <= 0:
        raise ValueError("market_impact_design_singular")
    coefficient = sum(x * y for x, y in zip(xs, ys)) / denominator
    fitted = [coefficient * x for x in xs]
    mean_y = sum(ys) / len(ys)
    total = sum((y - mean_y) ** 2 for y in ys)
    residual = sum((y - y_hat) ** 2 for y, y_hat in zip(ys, fitted))
    r_squared = None if total == 0 else 1.0 - residual / total
    return SqrtImpactModel(coefficient, len(rows), r_squared)
