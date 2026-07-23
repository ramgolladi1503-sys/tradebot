from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpiryChoice:
    signal_id: str
    selected_expiry: str
    min_time_to_expiry_minutes: int
    available_expiries: tuple[str, ...]
    rejection_reasons: dict[str, str]
    resolver_hash: str

    def validate(self, signal_ts: str) -> None:
        if not self.selected_expiry or self.selected_expiry not in self.available_expiries:
            raise ValueError("expiry_unresolved")
        if self.min_time_to_expiry_minutes <= 0:
            raise ValueError("invalid_min_time_to_expiry")
        if self.selected_expiry <= signal_ts[:10]:
            raise ValueError("expiry_not_strictly_after_signal_date")
