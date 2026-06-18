import pandas as pd
from typing import Union
from .models import Candle, Signal, Rejection

class RangeReversal:
    def __init__(self, variant: str):
        self.variant = variant
        self.name = f"RangeReversal_{variant}"
        self.risk_reward = 2.0
        self.last_date = None
        self.range_high = 0.0
        self.range_low = float('inf')
        self.range_established = False

    def evaluate(self, df: pd.DataFrame, current_candle: Candle, regime: str) -> Union[Signal, Rejection, None]:
        if self.last_date != current_candle.timestamp.date():
            self.last_date = current_candle.timestamp.date()
            self.range_high = 0.0
            self.range_low = float('inf')
            self.range_established = False

        time_str = current_candle.timestamp.strftime("%H:%M")
        
        if time_str < "10:30":
            self.range_high = max(self.range_high, current_candle.high)
            self.range_low = min(self.range_low, current_candle.low)
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_SESSION_TOO_EARLY")
            
        if time_str == "10:30":
            self.range_established = True
            
        if not self.range_established:
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_SESSION_TOO_EARLY")
            
        if time_str > "14:30":
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_LATE_SESSION")

        if regime not in ["CHOP", "VOL_CONTRACTION"]:
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_REGIME_MISMATCH")
            
        structure_matched = False
        direction = 0
        
        if self.variant == "SUPPORT":
            # Buy at range low
            direction = 1
            if current_candle.low <= self.range_low * 1.001 and current_candle.close > self.range_low:
                structure_matched = True
        elif self.variant == "RESISTANCE":
            # Sell at range high
            direction = -1
            if current_candle.high >= self.range_high * 0.999 and current_candle.close < self.range_high:
                structure_matched = True
                
        if not structure_matched:
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_STRUCTURE_FAIL")

        entry_price = current_candle.high if direction == 1 else current_candle.low
        stop_loss = self.range_low * 0.998 if direction == 1 else self.range_high * 1.002
        
        risk_points = abs(entry_price - stop_loss)
        if risk_points < 2.0:
            risk_points = 2.0
            stop_loss = entry_price - risk_points if direction == 1 else entry_price + risk_points
            
        if risk_points / entry_price > 0.005:
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_RISK_TOO_LARGE")

        target_points = risk_points * self.risk_reward
        target_1 = entry_price + target_points if direction == 1 else entry_price - target_points

        return Signal(
            symbol=current_candle.symbol,
            setup_name=self.name,
            regime=regime,
            signal_time=current_candle.timestamp,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target_1,
            risk_points=risk_points
        )
