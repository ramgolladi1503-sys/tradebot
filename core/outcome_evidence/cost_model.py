from typing import Optional
from .evidence_types import CostModelStatus
from .evidence_models import CostBreakdown


class IndianIndexOptionsCostModel:
    """Configurable cost model for Indian index options."""
    
    def __init__(
        self,
        brokerage_per_order: float = 20.0,
        stt_rate: float = 0.00125, # 0.125% on sell side premium
        exchange_tx_rate: float = 0.0005, # ~0.05% on premium
        sebi_rate: float = 0.000001, # ₹10 per crore
        stamp_duty_rate: float = 0.00003, # 0.003% on buy side premium
        gst_rate: float = 0.18, # 18% on (brokerage + SEBI + exchange_tx)
        default_slippage_points: float = 0.5,
        default_spread_points: float = 0.5,
    ):
        self.brokerage_per_order = brokerage_per_order
        self.stt_rate = stt_rate
        self.exchange_tx_rate = exchange_tx_rate
        self.sebi_rate = sebi_rate
        self.stamp_duty_rate = stamp_duty_rate
        self.gst_rate = gst_rate
        self.default_slippage_points = default_slippage_points
        self.default_spread_points = default_spread_points

    def calculate(
        self, 
        entry_price: float, 
        exit_price: float, 
        lot_size: int,
        bid_ask_spread: Optional[float] = None
    ) -> CostBreakdown:
        if entry_price <= 0 or exit_price <= 0 or lot_size <= 0:
            return CostBreakdown(
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, lot_size, CostModelStatus.INCOMPLETE
            )
            
        buy_value = entry_price * lot_size
        sell_value = exit_price * lot_size
        
        # Taxes & Charges
        brokerage = self.brokerage_per_order * 2  # Buy and Sell
        stt = round(sell_value * self.stt_rate)
        exchange_tx = (buy_value + sell_value) * self.exchange_tx_rate
        sebi = (buy_value + sell_value) * self.sebi_rate
        stamp_duty = round(buy_value * self.stamp_duty_rate)
        
        gst = (brokerage + exchange_tx + sebi) * self.gst_rate
        
        # Slippage & Spread
        slippage_cost = self.default_slippage_points * 2 * lot_size # entry and exit
        
        if bid_ask_spread is not None:
            spread_cost = bid_ask_spread * lot_size
            status = CostModelStatus.COMPLETE
        else:
            spread_cost = self.default_spread_points * lot_size
            status = CostModelStatus.ESTIMATED
            
        total_cost = brokerage + stt + exchange_tx + sebi + stamp_duty + gst + slippage_cost + spread_cost
        
        return CostBreakdown(
            brokerage=brokerage,
            stt=stt,
            exchange_tx=exchange_tx,
            sebi=sebi,
            stamp_duty=stamp_duty,
            gst=gst,
            slippage=slippage_cost,
            spread_cost=spread_cost,
            total_cost=total_cost,
            lot_size=lot_size,
            status=status
        )
