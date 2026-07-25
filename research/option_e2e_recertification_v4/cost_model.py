from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndiaOptionCostSchedule:
    schedule_id: str
    effective_from: str
    effective_until: str
    brokerage_entry: float
    brokerage_exit: float
    exchange_txn_rate: float
    stt_sell_rate: float
    gst_rate: float
    sebi_rate: float
    stamp_buy_rate: float

    def validate_for(self, trade_ts: str) -> None:
        if not (self.effective_from <= trade_ts < self.effective_until):
            raise ValueError("cost_schedule_not_effective")
        values = (
            self.brokerage_entry,
            self.brokerage_exit,
            self.exchange_txn_rate,
            self.stt_sell_rate,
            self.gst_rate,
            self.sebi_rate,
            self.stamp_buy_rate,
        )
        if any(value < 0 for value in values):
            raise ValueError("negative_cost_component")
