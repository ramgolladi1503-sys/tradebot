from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StrikeWrapper(str, Enum):
    ATM_LIQUIDITY_FIRST = "ATM_LIQUIDITY_FIRST"
    ONE_STEP_ITM = "ONE_STEP_ITM"
    ONE_STEP_OTM = "ONE_STEP_OTM"
    OBSERVED_DELTA_BUCKET = "OBSERVED_DELTA_BUCKET"
    BROAD_PREMIUM_LIQUIDITY_BUCKET = "BROAD_PREMIUM_LIQUIDITY_BUCKET"


@dataclass(frozen=True)
class StrikeChoice:
    signal_id: str
    wrapper: StrikeWrapper
    selected_strike: float
    atm_reference: float
    eligible_strikes: tuple[float, ...]
    causal_liquidity_fields: tuple[str, ...]
    resolver_hash: str
    observed_greeks_verified: bool = False

    def validate(self) -> None:
        if self.selected_strike <= 0 or self.atm_reference <= 0:
            raise ValueError("strike_unresolved")
        if self.selected_strike not in self.eligible_strikes:
            raise ValueError("selected_strike_not_in_causal_set")
        if self.wrapper == StrikeWrapper.OBSERVED_DELTA_BUCKET and not self.observed_greeks_verified:
            raise ValueError("DATA_UNAVAILABLE_OBSERVED_GREEKS")
        forbidden = {"future_volume", "future_oi", "future_spread", "future_return", "outcome_pnl"}
        if forbidden.intersection(self.causal_liquidity_fields):
            raise ValueError("future_or_outcome_field_in_strike_selection")
