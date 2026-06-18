import pandas as pd
from typing import Union
from .models import Candle, Signal, Rejection

class ORBVariants:
    def __init__(self, variant: str):
        self.variant = variant
        self.name = f"ORB_{variant}"
        self.risk_reward = 2.0
        self.last_date = None
        self.orb_high = 0.0
        self.orb_low = float('inf')
        self.orb_complete = False

    def evaluate(self, df: pd.DataFrame, current_candle: Candle, regime: str) -> Union[Signal, Rejection, None]:
        if self.last_date != current_candle.timestamp.date():
            self.last_date = current_candle.timestamp.date()
            self.orb_high = 0.0
            self.orb_low = float('inf')
            self.orb_complete = False

        time_str = current_candle.timestamp.strftime("%H:%M")
        
        if time_str < "09:30":
            self.orb_high = max(self.orb_high, current_candle.high)
            self.orb_low = min(self.orb_low, current_candle.low)
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_SESSION_TOO_EARLY")
            
        if time_str == "09:30":
            self.orb_complete = True
            
        if not self.orb_complete:
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_SESSION_TOO_EARLY")
            
        if time_str > "14:30":
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_LATE_SESSION")

        if regime not in ["TREND_UP", "TREND_DOWN", "VOL_EXPANSION"]:
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_REGIME_MISMATCH")
            
        direction = 1 if regime in ["TREND_UP", "VOL_EXPANSION"] else -1
        structure_matched = False
        
        if self.variant == "BREAKOUT":
            if direction == 1 and current_candle.close > self.orb_high and df.iloc[-2]['close'] <= self.orb_high:
                structure_matched = True
            elif direction == -1 and current_candle.close < self.orb_low and df.iloc[-2]['close'] >= self.orb_low:
                structure_matched = True
                
        if not structure_matched:
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_STRUCTURE_FAIL")

        entry_price = current_candle.high if direction == 1 else current_candle.low
        stop_loss = self.orb_low if direction == 1 else self.orb_high
        
        # Cap max stop loss to avoid massive range blowouts
        if abs(entry_price - stop_loss) / entry_price > 0.005:
            stop_loss = entry_price * 0.995 if direction == 1 else entry_price * 1.005
            
        risk_points = abs(entry_price - stop_loss)
        if risk_points < 2.0:
            risk_points = 2.0
            stop_loss = entry_price - risk_points if direction == 1 else entry_price + risk_points

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
