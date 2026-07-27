from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PremiumGeometry:
    geometry_id: str
    entry_fill: float
    stop_distance: float
    target_distance: float
    reward_risk: float
    max_hold_minutes: int
    tick_size: float
    warmup_observations: int
    source_cutoff_ts: str

    def validate(self) -> None:
        if self.entry_fill <= 0:
            raise ValueError("invalid_entry_fill")
        if self.stop_distance <= 0 or self.target_distance <= 0:
            raise ValueError("invalid_risk_distance")
        if self.tick_size <= 0 or self.max_hold_minutes <= 0:
            raise ValueError("invalid_geometry_terms")
        if self.warmup_observations <= 0:
            raise ValueError("insufficient_option_warmup")
        if self.stop_distance < self.tick_size or self.target_distance < self.tick_size:
            raise ValueError("risk_distance_below_tick")

    @property
    def stop_price(self) -> float:
        return max(0.0, self.entry_fill - self.stop_distance)

    @property
    def target_price(self) -> float:
        return self.entry_fill + self.target_distance
