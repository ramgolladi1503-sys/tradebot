from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal


Direction = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class MarketObservation:
    instrument_key: str
    observed_time: datetime
    available_time: datetime
    bid: float | None = None
    ask: float | None = None
    last: float | None = None

    def __post_init__(self) -> None:
        observed = self.observed_time.astimezone(timezone.utc)
        available = self.available_time.astimezone(timezone.utc)
        if available < observed:
            raise ValueError("observation_available_before_observed")
        if not self.instrument_key.strip():
            raise ValueError("missing_instrument_key")
        for name, value in (("bid", self.bid), ("ask", self.ask), ("last", self.last)):
            if value is not None and value <= 0:
                raise ValueError(f"non_positive_{name}")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("crossed_quote")
        object.__setattr__(self, "observed_time", observed)
        object.__setattr__(self, "available_time", available)


@dataclass(frozen=True)
class OutcomeContract:
    candidate_id: str
    instrument_key: str
    decision_time: datetime
    direction: Direction
    horizons: tuple[timedelta, ...]
    quantity: int = 1

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("missing_candidate_id")
        if not self.instrument_key.strip():
            raise ValueError("missing_instrument_key")
        if self.quantity <= 0:
            raise ValueError("non_positive_quantity")
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("unsupported_direction")
        decision = self.decision_time.astimezone(timezone.utc)
        if not self.horizons:
            raise ValueError("empty_horizons")
        if any(horizon <= timedelta(0) for horizon in self.horizons):
            raise ValueError("non_positive_horizon")
        if tuple(sorted(set(self.horizons))) != self.horizons:
            raise ValueError("horizons_must_be_unique_and_sorted")
        object.__setattr__(self, "decision_time", decision)


def _entry_price(observation: MarketObservation, direction: Direction) -> tuple[float, str]:
    if direction == "LONG":
        if observation.ask is None:
            raise ValueError("missing_causal_ask_entry")
        return observation.ask, "ASK"
    if observation.bid is None:
        raise ValueError("missing_causal_bid_entry")
    return observation.bid, "BID"


def _exit_price(observation: MarketObservation, direction: Direction) -> tuple[float, str]:
    if direction == "LONG":
        if observation.bid is None:
            raise ValueError("missing_causal_bid_exit")
        return observation.bid, "BID"
    if observation.ask is None:
        raise ValueError("missing_causal_ask_exit")
    return observation.ask, "ASK"


def _directional_return(entry: float, exit_price: float, direction: Direction) -> float:
    raw = exit_price / entry - 1.0
    return raw if direction == "LONG" else -raw


def build_causal_outcomes(
    contract: OutcomeContract,
    observations: Iterable[MarketObservation],
) -> list[dict[str, object]]:
    path = sorted(
        (
            observation
            for observation in observations
            if observation.instrument_key == contract.instrument_key
            and observation.available_time >= contract.decision_time
        ),
        key=lambda observation: (observation.available_time, observation.observed_time),
    )
    if not path:
        raise ValueError("no_post_decision_observations")
    entry = next(
        (
            observation
            for observation in path
            if observation.available_time > contract.decision_time
        ),
        None,
    )
    if entry is None:
        raise ValueError("no_causal_next_observation")
    entry_price, entry_side = _entry_price(entry, contract.direction)
    results: list[dict[str, object]] = []
    for horizon in contract.horizons:
        target_time = contract.decision_time + horizon
        eligible = [
            observation
            for observation in path
            if observation.available_time <= target_time
            and observation.available_time >= entry.available_time
        ]
        if not eligible:
            results.append(
                {
                    "candidate_id": contract.candidate_id,
                    "instrument_key": contract.instrument_key,
                    "horizon_seconds": int(horizon.total_seconds()),
                    "status": "HORIZON_NOT_OBSERVED",
                }
            )
            continue
        exit_observation = eligible[-1]
        try:
            exit_price, exit_side = _exit_price(exit_observation, contract.direction)
        except ValueError as exc:
            results.append(
                {
                    "candidate_id": contract.candidate_id,
                    "instrument_key": contract.instrument_key,
                    "horizon_seconds": int(horizon.total_seconds()),
                    "status": str(exc).upper(),
                }
            )
            continue
        path_prices: list[float] = []
        for observation in eligible:
            value = observation.bid if contract.direction == "LONG" else observation.ask
            if value is not None:
                path_prices.append(value)
        signed_returns = [
            _directional_return(entry_price, value, contract.direction)
            for value in path_prices
        ]
        mfe = max(signed_returns) if signed_returns else None
        mae = min(signed_returns) if signed_returns else None
        net_return = _directional_return(entry_price, exit_price, contract.direction)
        spread = (
            entry.ask - entry.bid
            if entry.ask is not None and entry.bid is not None
            else None
        )
        results.append(
            {
                "candidate_id": contract.candidate_id,
                "instrument_key": contract.instrument_key,
                "direction": contract.direction,
                "quantity": contract.quantity,
                "horizon_seconds": int(horizon.total_seconds()),
                "status": "RESOLVED",
                "decision_time": contract.decision_time.isoformat(),
                "entry_observed_time": entry.observed_time.isoformat(),
                "entry_available_time": entry.available_time.isoformat(),
                "entry_price": entry_price,
                "entry_side": entry_side,
                "entry_spread": spread,
                "exit_observed_time": exit_observation.observed_time.isoformat(),
                "exit_available_time": exit_observation.available_time.isoformat(),
                "exit_price": exit_price,
                "exit_side": exit_side,
                "return": net_return,
                "pnl": (exit_price - entry_price) * contract.quantity
                if contract.direction == "LONG"
                else (entry_price - exit_price) * contract.quantity,
                "mfe_return": mfe,
                "mae_return": mae,
                "observation_count": len(eligible),
                "cost_model": "OBSERVED_BID_ASK_ONLY",
            }
        )
    return results
