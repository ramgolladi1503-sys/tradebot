import pandas as pd
from typing import Dict, Any, Union
from .models import Candle, Signal, Rejection

class TrendContinuation:
    def __init__(self, variant: str):
        self.variant = variant
        self.name = f"TrendContinuation_{variant}"
        self.risk_reward = 2.0
        
        self.last_date = None
        self.current_day_high = 0.0
        self.current_day_low = float('inf')
        self.prev_day_high = 0.0
        self.prev_day_low = float('inf')

    def evaluate(self, df: pd.DataFrame, current_candle: Candle, regime: str) -> Union[Signal, Rejection, None]:
        if self.last_date != current_candle.timestamp.date():
            self.prev_day_high = self.current_day_high
            self.prev_day_low = self.current_day_low
            self.current_day_high = current_candle.high
            self.current_day_low = current_candle.low
            self.last_date = current_candle.timestamp.date()
        else:
            self.current_day_high = max(self.current_day_high, current_candle.high)
            self.current_day_low = min(self.current_day_low, current_candle.low)
            
        time_str = current_candle.timestamp.strftime("%H:%M")
        
        if time_str < "09:30":
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_SESSION_TOO_EARLY")
        if time_str > "14:30":
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_LATE_SESSION")

        if regime not in ["TREND_UP", "TREND_DOWN"]:
            return Rejection(current_candle.symbol, self.name, current_candle.timestamp, "REJECT_REGIME_MISMATCH")
            
        direction = 1 if regime == "TREND_UP" else -1
        structure_matched = False
        
        if self.variant == "EMA_PULLBACK":
            if len(df) >= 9:
                sma9 = df['close'].rolling(9).mean().iloc[-1]
                if direction == 1 and current_candle.low <= sma9 and current_candle.close > sma9:
                    structure_matched = True
                elif direction == -1 and current_candle.high >= sma9 and current_candle.close < sma9:
                    structure_matched = True
                    
        elif self.variant == "OPENING_DRIVE":
            if "09:30" <= time_str <= "10:15":
                od_high = df[df['timestamp'].dt.strftime("%H:%M") < "09:30"]['high'].max()
                od_low = df[df['timestamp'].dt.strftime("%H:%M") < "09:30"]['low'].min()
                if direction == 1 and current_candle.close > od_high:
                    structure_matched = True
                elif direction == -1 and current_candle.close < od_low:
                    structure_matched = True

        elif self.variant == "VWAP_RECLAIM":
            if direction == 1 and current_candle.close > current_candle.vwap and df.iloc[-2]['close'] < df.iloc[-2]['vwap']:
                structure_matched = True
            elif direction == -1 and current_candle.close < current_candle.vwap and df.iloc[-2]['close'] > df.iloc[-2]['vwap']:
                structure_matched = True

        elif self.variant == "PDH_PDL":
            if self.prev_day_high > 0:
                if direction == 1 and current_candle.close > self.prev_day_high:
                    structure_matched = True
                elif direction == -1 and current_candle.close < self.prev_day_low:
                    structure_matched = True

        elif self.variant == "BREAK_AND_RETEST":
            if len(df) >= 20:
                recent_high = df['high'].iloc[-20:-5].max()
                recent_low = df['low'].iloc[-20:-5].min()
                if direction == 1 and recent_low < current_candle.low <= recent_high and current_candle.close > recent_high:
                    structure_matched = True
                elif direction == -1 and recent_high > current_candle.high >= recent_low and current_candle.close < recent_low:
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
