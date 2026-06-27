from dataclasses import dataclass
from typing import Optional
from .evidence_types import CostModelStatus
from .evidence_models import CostBreakdown, CostComponent


@dataclass(frozen=True)
class CostModelConfig:
    brokerage_per_order: float = 20.0
    stt_rate: float = 0.00125
    exchange_tx_rate: float = 0.0005
    sebi_rate: float = 0.000001
    stamp_duty_rate: float = 0.00003
    gst_rate: float = 0.18
    default_slippage_points: float = 0.5
    default_spread_points: float = 0.5


class IndianIndexOptionsCostModel:
    """Configurable cost model for Indian index options."""
    
    def __init__(self, config: Optional[CostModelConfig] = None):
        self.config = config or CostModelConfig()

    def calculate(
        self, 
        entry_price: float, 
        exit_price: float, 
        lot_size: int,
        bid_ask_spread: Optional[float] = None
    ) -> CostBreakdown:
        if entry_price <= 0 or exit_price <= 0 or lot_size <= 0:
            return CostBreakdown(
                components=[], total_cost=0.0, lot_size=lot_size, status=CostModelStatus.INCOMPLETE
            )
            
        buy_value = entry_price * lot_size
        sell_value = exit_price * lot_size
        
        # Taxes & Charges
        brokerage = self.config.brokerage_per_order * 2  # Buy and Sell
        stt = round(sell_value * self.config.stt_rate)
        exchange_tx = (buy_value + sell_value) * self.config.exchange_tx_rate
        sebi = (buy_value + sell_value) * self.config.sebi_rate
        stamp_duty = round(buy_value * self.config.stamp_duty_rate)
        
        gst = (brokerage + exchange_tx + sebi) * self.config.gst_rate
        
        # Slippage & Spread
        slippage_cost = self.config.default_slippage_points * 2 * lot_size # entry and exit
        
        if bid_ask_spread is not None:
            spread_cost = bid_ask_spread * lot_size
            status = CostModelStatus.COMPLETE
            spread_estimated = False
            spread_bid_ask_available = True
        else:
            spread_cost = self.config.default_spread_points * lot_size
            status = CostModelStatus.ESTIMATED
            spread_estimated = True
            spread_bid_ask_available = False
            
        total_cost = brokerage + stt + exchange_tx + sebi + stamp_duty + gst + slippage_cost + spread_cost
        
        components = [
            CostComponent("brokerage", brokerage, "config", False, True),
            CostComponent("stt", stt, "config", False, True),
            CostComponent("exchange_tx", exchange_tx, "config", False, True),
            CostComponent("sebi", sebi, "config", False, True),
            CostComponent("stamp_duty", stamp_duty, "config", False, True),
            CostComponent("gst", gst, "config", False, True),
            CostComponent("slippage", slippage_cost, "config", True, False),
            CostComponent("spread", spread_cost, "trace" if not spread_estimated else "config", spread_estimated, spread_bid_ask_available)
        ]
        
        return CostBreakdown(
            components=components,
            total_cost=total_cost,
            lot_size=lot_size,
            status=status
        )
