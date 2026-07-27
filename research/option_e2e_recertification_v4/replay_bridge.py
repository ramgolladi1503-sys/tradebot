from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutableQuote:
    ts: str
    bid: float | None
    ask: float | None
    bid_qty: int | None
    ask_qty: int | None
    volume: int | None
    oi: int | None
    quote_age_seconds: float
    symbol: str

    def validate_for_long_entry(self, earliest_entry_ts: str, *, max_quote_age_seconds: float) -> None:
        if self.ts <= earliest_entry_ts:
            raise ValueError("entry_quote_not_after_earliest_entry_ts")
        if self.bid is None or self.ask is None or self.bid <= 0 or self.ask <= 0:
            raise ValueError("missing_bid_ask")
        if self.ask < self.bid:
            raise ValueError("crossed_quote")
        if self.quote_age_seconds < 0:
            raise ValueError("negative_quote_age")
        if self.quote_age_seconds > max_quote_age_seconds:
            raise ValueError("stale_quote_rejected")
        if (self.ask_qty or 0) <= 0:
            raise ValueError("entry_liquidity_rejected")
        if (self.bid_qty or 0) <= 0:
            raise ValueError("exit_side_liquidity_unproven")

    def long_entry_fill(self) -> float:
        if self.ask is None:
            raise ValueError("missing_entry_ask")
        return float(self.ask)

    def long_exit_fill(self) -> float:
        if self.bid is None:
            raise ValueError("missing_exit_bid")
        return float(self.bid)
