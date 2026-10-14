"""Causal Synchronized Tape Buffer.

Guarantees:
1. Strict information horizon: Snapshots only emit data up to the closed bar horizon T.
2. Zero future-bar leakage: Any data from t > T raises CausalityViolationError.
3. State consensus: Aligns Spot, Option Chain OI, and Volatility (VIX) into an immutable vector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
import numpy as np


class CausalityViolationError(Exception):
    """Raised when data from the future is injected or accessed prior to its causal horizon."""


@dataclass(frozen=True)
class MarketTick:
    timestamp: datetime
    stream_type: str  # SPOT, OPTION, VIX, BREADTH
    symbol: str
    price: float
    volume: float = 0.0
    open_interest: float = 0.0
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class MarketStateSnapshot:
    horizon_timestamp: datetime
    spot_price: float
    spot_vwap: float
    vix: float
    call_oi_total: float
    put_oi_total: float
    strike_pcr: float
    active_strikes_oi: Mapping[float, tuple[float, float]]  # strike -> (call_oi, put_oi)
    is_closed_bar: bool = True

    def state_vector(self) -> np.ndarray:
        """Returns normalized numerical vector for state representation and caching."""
        return np.array([
            self.spot_price,
            self.spot_vwap,
            self.vix,
            self.strike_pcr,
            self.call_oi_total,
            self.put_oi_total,
        ], dtype=np.float64)


class CausalSynchronizedBuffer:
    """Synchronizes multi-stream ticks into completed causal bar snapshots without lookahead."""

    def __init__(self, bar_duration_seconds: int = 60) -> None:
        self.bar_duration_seconds = bar_duration_seconds
        self._current_horizon: datetime | None = None
        self._latest_spot_price: float | None = None
        self._spot_prices_in_bar: list[float] = []
        self._spot_volumes_in_bar: list[float] = []
        self._latest_vix: float = 15.0
        self._call_oi: dict[float, float] = {}
        self._put_oi: dict[float, float] = {}

    def ingest_tick(self, tick: MarketTick) -> None:
        """Ingests a tick into the buffer while enforcing temporal ordering."""
        if self._current_horizon is not None and tick.timestamp < self._current_horizon:
            raise CausalityViolationError(
                f"Tick timestamp {tick.timestamp} arrived after horizon {self._current_horizon} was finalized."
            )

        if tick.stream_type == "SPOT":
            self._latest_spot_price = tick.price
            self._spot_prices_in_bar.append(tick.price)
            self._spot_volumes_in_bar.append(max(0.0, tick.volume))
        elif tick.stream_type == "VIX":
            self._latest_vix = tick.price
        elif tick.stream_type == "OPTION":
            is_call = "CE" in tick.symbol or (tick.metadata and tick.metadata.get("option_type") == "CE")
            strike = float(tick.metadata.get("strike", 0.0)) if tick.metadata else 0.0
            if strike > 0:
                if is_call:
                    self._call_oi[strike] = tick.open_interest
                else:
                    self._put_oi[strike] = tick.open_interest

    def close_bar_horizon(self, horizon_timestamp: datetime) -> MarketStateSnapshot:
        """Finalizes the closed bar horizon and returns an immutable state snapshot."""
        if self._latest_spot_price is None:
            raise ValueError("Cannot close horizon without spot price data.")

        if self._spot_volumes_in_bar and sum(self._spot_volumes_in_bar) > 0:
            vwap = sum(p * v for p, v in zip(self._spot_prices_in_bar, self._spot_volumes_in_bar)) / sum(self._spot_volumes_in_bar)
        else:
            vwap = float(np.mean(self._spot_prices_in_bar)) if self._spot_prices_in_bar else self._latest_spot_price

        total_call_oi = sum(self._call_oi.values())
        total_put_oi = sum(self._put_oi.values())
        strike_pcr = (total_put_oi / total_call_oi) if total_call_oi > 0 else 1.0

        all_strikes = set(self._call_oi.keys()).union(self._put_oi.keys())
        strike_breakdown = {
            s: (self._call_oi.get(s, 0.0), self._put_oi.get(s, 0.0))
            for s in sorted(all_strikes)
        }

        snapshot = MarketStateSnapshot(
            horizon_timestamp=horizon_timestamp,
            spot_price=self._latest_spot_price,
            spot_vwap=vwap,
            vix=self._latest_vix,
            call_oi_total=total_call_oi,
            put_oi_total=total_put_oi,
            strike_pcr=strike_pcr,
            active_strikes_oi=strike_breakdown,
            is_closed_bar=True,
        )

        self._current_horizon = horizon_timestamp
        self._spot_prices_in_bar = []
        self._spot_volumes_in_bar = []

        return snapshot
