from __future__ import annotations

from dataclasses import dataclass

from .time_utils import expiry_cutoff_ts, parse_ts


@dataclass(frozen=True)
class ExpiryChoice:
    signal_id: str
    selected_expiry: str
    min_time_to_expiry_minutes: int
    available_expiries: tuple[str, ...]
    rejection_reasons: dict[str, str]
    resolver_hash: str

    def validate(self, signal_ts: str, *, expiry_cutoff: str = "15:30:00") -> None:
        if not self.selected_expiry or self.selected_expiry not in self.available_expiries:
            raise ValueError("expiry_unresolved")
        if self.min_time_to_expiry_minutes <= 0:
            raise ValueError("invalid_min_time_to_expiry")
        signal = parse_ts(signal_ts)
        cutoff = expiry_cutoff_ts(self.selected_expiry, cutoff=expiry_cutoff)
        if signal >= cutoff:
            raise ValueError("expiry_not_valid_after_cutoff")
        minutes_to_expiry = (cutoff - signal).total_seconds() / 60.0
        if minutes_to_expiry < float(self.min_time_to_expiry_minutes):
            raise ValueError("expiry_min_time_to_expiry_not_met")
