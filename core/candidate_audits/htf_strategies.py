import pandas as pd
from typing import Union
from .models import Candle, Signal, Rejection

class HTFStrategy:
    def __init__(self, variant: str):
        self.variant = variant
        self.name = f"HTF_{variant}"
        self.risk_reward = 2.0

        self.last_date = None
        self.pdh = 0.0
        self.pdl = float('inf')
        self.pdc = 0.0
        self.cdh = 0.0
        self.cdl = float('inf')
        self.cdc = 0.0
        self.od_high = 0.0
        self.od_low = float('inf')

    def evaluate(self, df_15m: pd.DataFrame, df_1m: pd.DataFrame, current_candle_15m: Candle, current_candle_1m: Candle, regime: str, ablation: str = "BASELINE") -> Union[Signal, Rejection, None]:
        # Safe missing data handling
        if df_15m is None or df_15m.empty or df_1m is None or df_1m.empty:
            return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_MISSING_DATA")

        if self.last_date != current_candle_15m.timestamp.date():
            if self.pdh == 0.0:
                self.pdh = self.cdh
            if self.pdl == float('inf'):
                self.pdl = self.cdl
            if self.pdc == 0.0:
                self.pdc = self.cdc
            self.cdh = current_candle_15m.high
            self.cdl = current_candle_15m.low
            self.cdc = current_candle_15m.close

            # Only reset OD if they haven't been seeded externally
            if self.od_high == 0.0:
                self.od_high = current_candle_15m.high
            if self.od_low == float('inf'):
                self.od_low = current_candle_15m.low
            self.last_date = current_candle_15m.timestamp.date()
        else:
            self.cdh = max(self.cdh, current_candle_15m.high)
            self.cdl = min(self.cdl, current_candle_15m.low)
            self.cdc = current_candle_15m.close

        time_str = current_candle_15m.timestamp.strftime("%H:%M")

        if time_str <= "10:00":
            self.od_high = max(self.od_high, current_candle_15m.high)
            self.od_low = min(self.od_low, current_candle_15m.low)

        # Session Gating
        if ablation not in ["E"]:
            if time_str < "10:15":
                return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_SESSION")
            if time_str > "14:30":
                return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_SESSION")

        direction = 0
        structure_matched = False

        # Determine effective regime based on ablation
        # The true 15m and 30m trend is available in the 1m dataframe we passed,
        # but to keep it self-contained, let's extract it from current_candle_1m.
        # Actually, df_1m has 'trend_15m' and 'trend_30m'. We should read it from df_1m.iloc[-1].

        curr_1m_row = df_1m.iloc[-1]
        t15 = curr_1m_row.get('trend_15m', 0)
        t30 = curr_1m_row.get('trend_30m', 0)

        trend_up = False
        trend_dn = False

        if ablation == "BASELINE":
            if regime == "VOL_EXPANSION":
                trend_up = True
                trend_dn = True
            elif t15 == 1 and t30 == 1:
                trend_up = True
            elif t15 == -1 and t30 == -1:
                trend_dn = True
        elif ablation == "A": # 15m only
            if t15 == 1: trend_up = True
            if t15 == -1: trend_dn = True
        elif ablation == "B": # 30m only
            if t30 == 1: trend_up = True
            if t30 == -1: trend_dn = True
        elif ablation == "C": # 15m OR 30m
            if t15 == 1 or t30 == 1: trend_up = True
            if t15 == -1 or t30 == -1: trend_dn = True
        elif ablation in ["D", "F"]: # Structure only, ignore regime
            trend_up = True
            trend_dn = True
        elif ablation == "E": # Regime only, ignore structure
            if t15 == 1 and t30 == 1: trend_up = True
            elif t15 == -1 and t30 == -1: trend_dn = True

            if trend_up:
                direction = 1
                structure_matched = True
            elif trend_dn:
                direction = -1
                structure_matched = True

        if not structure_matched and ablation != "E":
            if self.variant == "15M_TREND_CONT":
                if not (trend_up or trend_dn):
                    if t15 != t30: return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_30M_REGIME")
                    else: return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_15M_REGIME")

                if trend_up:
                    if current_candle_15m.close > current_candle_15m.open and (current_candle_15m.high - current_candle_15m.close) < (current_candle_15m.high - current_candle_15m.low) * 0.3:
                        if current_candle_15m.close > df_15m.iloc[-1]['high']:
                            direction = 1
                            structure_matched = True
                if trend_dn and not structure_matched:
                    if current_candle_15m.close < current_candle_15m.open and (current_candle_15m.close - current_candle_15m.low) < (current_candle_15m.high - current_candle_15m.low) * 0.3:
                        if current_candle_15m.close < df_15m.iloc[-1]['low']:
                            direction = -1
                            structure_matched = True

                if not structure_matched:
                    return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_STRUCTURE")

            elif self.variant == "15M_VWAP_PULLBACK":
                if not (trend_up or trend_dn):
                    if t15 != t30: return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_30M_REGIME")
                    else: return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_15M_REGIME")

                vwap = current_candle_15m.vwap
                distance = (current_candle_15m.close - vwap) / vwap

                if trend_up and distance > 0.001 and distance < 0.003:
                    if current_candle_15m.low <= vwap * 1.001 and current_candle_15m.close > vwap:
                        direction = 1
                        structure_matched = True
                if trend_dn and not structure_matched and distance < -0.001 and distance > -0.003:
                    if current_candle_15m.high >= vwap * 0.999 and current_candle_15m.close < vwap:
                        direction = -1
                        structure_matched = True

                if not structure_matched:
                    if abs(distance) > 0.003 or abs(distance) < 0.001:
                        return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_VWAP_COND")
                    else:
                        return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_STRUCTURE")

            elif self.variant == "OPENING_DRIVE_CONT":
                if not (trend_up or trend_dn):
                    if t15 != t30: return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_30M_REGIME")
                    else: return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_15M_REGIME")

                if trend_up and current_candle_15m.close > self.od_high:
                    direction = 1
                    structure_matched = True
                if trend_dn and not structure_matched and current_candle_15m.close < self.od_low:
                    direction = -1
                    structure_matched = True

                if not structure_matched:
                    return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_STRUCTURE")

            elif self.variant == "PDH_PDL_HOLD":
                if self.pdh > 0 and self.pdl < float('inf'):
                    if current_candle_15m.close > self.pdh and df_15m.iloc[-1]['close'] > self.pdh:
                        direction = 1
                        structure_matched = True
                    elif current_candle_15m.close < self.pdl and df_15m.iloc[-1]['close'] < self.pdl:
                        direction = -1
                        structure_matched = True
                if not structure_matched:
                    return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_PDH_PDL_COND")

            elif self.variant == "FAILED_BREAKOUT_REVERSAL":
                if regime not in ["RANGE", "CHOP"] and ablation not in ["D", "F"]:
                    return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_15M_REGIME")

                if df_15m.iloc[-1]['high'] > self.od_high and current_candle_15m.close < self.od_high:
                    direction = -1
                    structure_matched = True
                elif df_15m.iloc[-1]['low'] < self.od_low and current_candle_15m.close > self.od_low:
                    direction = 1
                    structure_matched = True
                if not structure_matched:
                    return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_STRUCTURE")

            elif self.variant == "RANGE_EXPANSION":
                if regime != "VOL_EXPANSION" and ablation not in ["D", "F"]:
                    return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_VOLATILITY")

                # Gap Expansion Warning
                if self.pdc > 0:
                    try:
                        today_df = df_15m[df_15m['timestamp'].dt.date == current_candle_15m.timestamp.date()]
                        if not today_df.empty:
                            current_open = today_df.iloc[0]['open']
                            if abs(current_open - self.pdc) / self.pdc > 0.005:
                                return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_GAP_EXPANSION")
                    except Exception:
                        pass

                if current_candle_15m.close > self.od_high:
                    direction = 1
                    structure_matched = True
                elif current_candle_15m.close < self.od_low:
                    direction = -1
                    structure_matched = True
                if not structure_matched:
                    return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_STRUCTURE")

        if not structure_matched:
            return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_STRUCTURE")

        # Entry on 1m resolution AFTER 15m signal (next 1m open)
        # If there's no data or the candle is corrupted
        if pd.isna(current_candle_1m.open):
            return Rejection(current_candle_15m.symbol, self.name, current_candle_1m.timestamp, "REJECT_EXECUTION_AVAILABILITY")

        entry_price = current_candle_1m.open
        stop_loss = current_candle_15m.low if direction == 1 else current_candle_15m.high

        risk_points = abs(entry_price - stop_loss)
        if risk_points < 10.0:
            risk_points = 10.0
            stop_loss = entry_price - risk_points if direction == 1 else entry_price + risk_points

        target_points = risk_points * self.risk_reward
        target_1 = entry_price + target_points if direction == 1 else entry_price - target_points

        return Signal(
            symbol=current_candle_15m.symbol,
            setup_name=self.name,
            regime=regime,
            signal_time=current_candle_1m.timestamp,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target_1,
            risk_points=risk_points
        )
