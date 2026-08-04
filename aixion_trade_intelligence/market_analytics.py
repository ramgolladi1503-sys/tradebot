from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Iterable, Mapping, Sequence


def _finite(value: float, *, name: str) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name}_not_finite")
    return out


@dataclass(frozen=True)
class BreadthAnalytics:
    constituent_count: int
    positive_count: int
    negative_count: int
    unchanged_count: int
    equal_weight_breadth: float
    weighted_breadth: float | None
    median_return: float
    absolute_contribution: float | None
    top3_concentration: float | None
    top5_concentration: float | None

    def to_record(self) -> dict[str, object]:
        return {
            "constituent_count": self.constituent_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "unchanged_count": self.unchanged_count,
            "equal_weight_breadth": self.equal_weight_breadth,
            "weighted_breadth": self.weighted_breadth,
            "median_return": self.median_return,
            "absolute_contribution": self.absolute_contribution,
            "top3_concentration": self.top3_concentration,
            "top5_concentration": self.top5_concentration,
        }


def calculate_breadth(
    returns: Mapping[str, float],
    *,
    weights: Mapping[str, float] | None = None,
) -> BreadthAnalytics:
    if not returns:
        raise ValueError("returns_empty")
    clean = {str(symbol): _finite(value, name=f"return_{symbol}") for symbol, value in returns.items()}
    positive = sum(value > 0 for value in clean.values())
    negative = sum(value < 0 for value in clean.values())
    unchanged = len(clean) - positive - negative
    equal = (positive - negative) / len(clean)
    weighted_breadth: float | None = None
    total_abs_contribution: float | None = None
    top3: float | None = None
    top5: float | None = None
    if weights is not None:
        missing = sorted(set(clean) - set(weights))
        if missing:
            raise ValueError(f"missing_weights={','.join(missing)}")
        clean_weights = {symbol: _finite(weights[symbol], name=f"weight_{symbol}") for symbol in clean}
        weight_total = sum(abs(value) for value in clean_weights.values())
        if weight_total <= 0:
            raise ValueError("weight_total_nonpositive")
        weighted_breadth = sum(
            clean_weights[symbol] * (1.0 if clean[symbol] > 0 else -1.0 if clean[symbol] < 0 else 0.0)
            for symbol in clean
        ) / weight_total
        contributions = sorted((abs(clean_weights[symbol] * clean[symbol]) for symbol in clean), reverse=True)
        total_abs_contribution = sum(contributions)
        if total_abs_contribution > 0:
            top3 = sum(contributions[:3]) / total_abs_contribution
            top5 = sum(contributions[:5]) / total_abs_contribution
        else:
            top3 = 0.0
            top5 = 0.0
    return BreadthAnalytics(
        constituent_count=len(clean),
        positive_count=positive,
        negative_count=negative,
        unchanged_count=unchanged,
        equal_weight_breadth=equal,
        weighted_breadth=weighted_breadth,
        median_return=median(clean.values()),
        absolute_contribution=total_abs_contribution,
        top3_concentration=top3,
        top5_concentration=top5,
    )


@dataclass(frozen=True)
class FuturesBasisAnalytics:
    index_price: float
    futures_price: float
    basis: float
    basis_pct: float
    basis_change: float | None
    futures_return_minus_index_return: float | None

    def to_record(self) -> dict[str, float | None]:
        return {
            "index_price": self.index_price,
            "futures_price": self.futures_price,
            "basis": self.basis,
            "basis_pct": self.basis_pct,
            "basis_change": self.basis_change,
            "futures_return_minus_index_return": self.futures_return_minus_index_return,
        }


def calculate_futures_basis(
    *,
    index_price: float,
    futures_price: float,
    previous_index_price: float | None = None,
    previous_futures_price: float | None = None,
) -> FuturesBasisAnalytics:
    index_value = _finite(index_price, name="index_price")
    futures_value = _finite(futures_price, name="futures_price")
    if index_value <= 0 or futures_value <= 0:
        raise ValueError("prices_must_be_positive")
    basis = futures_value - index_value
    basis_change: float | None = None
    relative_return: float | None = None
    if (previous_index_price is None) != (previous_futures_price is None):
        raise ValueError("previous_prices_must_be_paired")
    if previous_index_price is not None and previous_futures_price is not None:
        prior_index = _finite(previous_index_price, name="previous_index_price")
        prior_futures = _finite(previous_futures_price, name="previous_futures_price")
        if prior_index <= 0 or prior_futures <= 0:
            raise ValueError("previous_prices_must_be_positive")
        basis_change = basis - (prior_futures - prior_index)
        relative_return = (futures_value / prior_futures - 1.0) - (index_value / prior_index - 1.0)
    return FuturesBasisAnalytics(index_value, futures_value, basis, basis / index_value, basis_change, relative_return)


@dataclass(frozen=True)
class BookLevel:
    price: float
    quantity: float

    def __post_init__(self) -> None:
        price = _finite(self.price, name="level_price")
        quantity = _finite(self.quantity, name="level_quantity")
        if price <= 0:
            raise ValueError("level_price_nonpositive")
        if quantity < 0:
            raise ValueError("level_quantity_negative")
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "quantity", quantity)


@dataclass(frozen=True)
class OptionMicrostructureAnalytics:
    bid: float
    ask: float
    mid: float
    spread: float
    spread_pct_mid: float
    microprice: float | None
    top_depth_imbalance: float | None
    bid_depth_total: float
    ask_depth_total: float
    full_depth_imbalance: float | None

    def to_record(self) -> dict[str, float | None]:
        return self.__dict__.copy()


def calculate_option_microstructure(
    *,
    bid: float,
    ask: float,
    bid_levels: Sequence[BookLevel] = (),
    ask_levels: Sequence[BookLevel] = (),
) -> OptionMicrostructureAnalytics:
    bid_value = _finite(bid, name="bid")
    ask_value = _finite(ask, name="ask")
    if bid_value <= 0 or ask_value <= 0:
        raise ValueError("quote_prices_must_be_positive")
    if ask_value < bid_value:
        raise ValueError("crossed_quote")
    mid = (bid_value + ask_value) / 2.0
    spread = ask_value - bid_value
    bid_total = sum(level.quantity for level in bid_levels)
    ask_total = sum(level.quantity for level in ask_levels)
    top_imbalance: float | None = None
    microprice: float | None = None
    if bid_levels and ask_levels:
        bid_qty = bid_levels[0].quantity
        ask_qty = ask_levels[0].quantity
        denominator = bid_qty + ask_qty
        if denominator > 0:
            top_imbalance = (bid_qty - ask_qty) / denominator
            microprice = (ask_value * bid_qty + bid_value * ask_qty) / denominator
    full_imbalance = None if bid_total + ask_total == 0 else (bid_total - ask_total) / (bid_total + ask_total)
    return OptionMicrostructureAnalytics(
        bid_value, ask_value, mid, spread, spread / mid, microprice,
        top_imbalance, bid_total, ask_total, full_imbalance,
    )


def lead_lag_returns(
    leader: Sequence[tuple[float, float]],
    follower: Sequence[tuple[float, float]],
    *,
    lags_seconds: Iterable[float],
) -> dict[float, float | None]:
    leader_rows = sorted((_finite(ts, name="leader_ts"), _finite(value, name="leader_value")) for ts, value in leader)
    follower_rows = sorted((_finite(ts, name="follower_ts"), _finite(value, name="follower_value")) for ts, value in follower)
    if not leader_rows or not follower_rows:
        raise ValueError("lead_lag_inputs_empty")

    def correlation(xs: list[float], ys: list[float]) -> float | None:
        if len(xs) < 2:
            return None
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        denominator = math.sqrt(sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys))
        return None if denominator == 0 else numerator / denominator

    result: dict[float, float | None] = {}
    for raw_lag in lags_seconds:
        lag = _finite(raw_lag, name="lag")
        xs: list[float] = []
        ys: list[float] = []
        index = 0
        latest: float | None = None
        for follower_ts, follower_value in follower_rows:
            cutoff = follower_ts - lag
            while index < len(leader_rows) and leader_rows[index][0] <= cutoff:
                latest = leader_rows[index][1]
                index += 1
            if latest is not None:
                xs.append(latest)
                ys.append(follower_value)
        result[lag] = correlation(xs, ys)
    return result
