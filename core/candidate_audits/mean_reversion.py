import pandas as pd
from typing import Union
from .models import Candle, Signal, Rejection

class MeanReversion:
    def __init__(self, variant: str):
        self.variant = variant
        self.name = f"MeanReversion_{variant}"
        self.risk_reward = 2.0

    def evaluate(self, df: pd.DataFrame, current_candle: Candle, regime: str) -> Union[Signal, Rejection, None]:
        time_str = current_candle.timestamp.strftime("%H:%M")
        
        if time_str < "09:45":
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_SESSION_TOO_EARLY")
            
        if time_str > "14:30":
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_LATE_SESSION")

        if regime not in ["CHOP", "VOL_CONTRACTION", "VOL_EXPANSION"]:
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_REGIME_MISMATCH")
            
        structure_matched = False
        direction = 0
        
        if self.variant == "VWAP_PULLBACK":
            # If price is far from VWAP, revert to VWAP.
            # E.g. long if price is 0.5% below VWAP and shows a green reversal candle
            distance = (current_candle.close - current_candle.vwap) / current_candle.vwap
            
            if distance <= -0.003: # 0.3% below
                direction = 1
                if current_candle.close > current_candle.open and current_candle.close > df.iloc[-2]['high']:
                    structure_matched = True
            elif distance >= 0.003: # 0.3% above
                direction = -1
                if current_candle.close < current_candle.open and current_candle.close < df.iloc[-2]['low']:
                    structure_matched = True
                
        if not structure_matched:
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_STRUCTURE_FAIL")

        entry_price = current_candle.high if direction == 1 else current_candle.low
        stop_loss = current_candle.low if direction == 1 else current_candle.high
        
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
