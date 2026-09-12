from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Direction = Literal["BULLISH", "BEARISH", "NO_TRADE"]
RankingMetric = Literal["expected_net_premium_points", "expected_return_pct"]


@dataclass(frozen=True)
class ForwardMoveLabelConfig:
    horizons_minutes: tuple[int, ...] = (15, 20, 30)
    move_thresholds_points: tuple[float, ...] = (15.0, 25.0, 40.0, 60.0)
    bar_interval_minutes: int = 1

    def __post_init__(self) -> None:
        if self.bar_interval_minutes < 1:
            raise ValueError("bar_interval_minutes must be positive")
        if not self.horizons_minutes:
            raise ValueError("at least one horizon is required")
        if any(h <= 0 for h in self.horizons_minutes):
            raise ValueError("horizons_minutes must be positive")
        if any(h % self.bar_interval_minutes for h in self.horizons_minutes):
            raise ValueError("every horizon must be divisible by bar_interval_minutes")
        if any(t <= 0 for t in self.move_thresholds_points):
            raise ValueError("move thresholds must be positive")


@dataclass(frozen=True)
class ForecastSignal:
    decision_timestamp: object
    direction: Direction
    horizon_minutes: int
    probability_direction: float
    expected_spot_move_points: float

    def __post_init__(self) -> None:
        if self.direction not in {"BULLISH", "BEARISH", "NO_TRADE"}:
            raise ValueError("unsupported direction")
        if self.horizon_minutes <= 0:
            raise ValueError("horizon_minutes must be positive")
        if not 0.0 <= float(self.probability_direction) <= 1.0:
            raise ValueError("probability_direction must be in [0, 1]")
        if self.direction == "BULLISH" and self.expected_spot_move_points < 0:
            raise ValueError("bullish forecast requires non-negative expected move")
        if self.direction == "BEARISH" and self.expected_spot_move_points > 0:
            raise ValueError("bearish forecast requires non-positive expected move")


@dataclass(frozen=True)
class StrikeRankingConfig:
    strike_step: float = 50.0
    max_moneyness_steps: int = 2
    min_probability_direction: float = 0.55
    min_abs_expected_spot_move_points: float = 10.0
    max_spread_pct: float = 8.0
    min_abs_delta: float = 0.20
    max_abs_delta: float = 0.85
    min_volume: float = 0.0
    min_open_interest: float = 0.0
    slippage_points_round_trip: float = 0.0
    fees_points_round_trip: float = 0.0
    ranking_metric: RankingMetric = "expected_net_premium_points"
    lot_size: int | None = None

    def __post_init__(self) -> None:
        if self.strike_step <= 0:
            raise ValueError("strike_step must be positive")
        if self.max_moneyness_steps < 0:
            raise ValueError("max_moneyness_steps cannot be negative")
        if not 0.0 <= self.min_probability_direction <= 1.0:
            raise ValueError("min_probability_direction must be in [0, 1]")
        if self.min_abs_expected_spot_move_points < 0:
            raise ValueError("min_abs_expected_spot_move_points cannot be negative")
        if self.max_spread_pct < 0:
            raise ValueError("max_spread_pct cannot be negative")
        if not 0.0 <= self.min_abs_delta <= self.max_abs_delta <= 1.0:
            raise ValueError("invalid delta bounds")
        if self.slippage_points_round_trip < 0 or self.fees_points_round_trip < 0:
            raise ValueError("cost assumptions cannot be negative")
        if self.ranking_metric not in {
            "expected_net_premium_points",
            "expected_return_pct",
        }:
            raise ValueError("unsupported ranking metric")
        if self.lot_size is not None and self.lot_size <= 0:
            raise ValueError("lot_size must be positive when supplied")


CLAIM_BOUNDARY_UNDERLYING = "UNDERLYING_DIRECTION_AND_MAGNITUDE_ONLY"
CLAIM_BOUNDARY_OPTION_APPROX = "OPTION_TRANSLATION_APPROXIMATION_NOT_REALIZED_PNL"
CLAIM_BOUNDARY_OPTION_REALIZED = "REAL_OPTION_QUOTES_ASK_TO_BID_REALIZED_PNL"
