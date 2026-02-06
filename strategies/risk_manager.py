# strategies/risk_manager.py

from datetime import datetime

class RiskManager:
    def __init__(
        self,
        capital,
        max_risk_per_trade=0.01,   # 1%
        max_daily_loss=0.03,       # 3%
        max_trades_per_day=5
    ):
        self.capital = capital
        self.max_risk_per_trade = max_risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_trades_per_day = max_trades_per_day

        self.daily_pnl = 0
        self.trades_today = 0
        self.day = datetime.now().date()

    def reset_day_if_needed(self):
        today = datetime.now().date()
        if today != self.day:
            self.day = today
            self.daily_pnl = 0
            self.trades_today = 0

    def can_take_trade(self, stop_loss_points, lot_value):
        self.reset_day_if_needed()

        if self.trades_today >= self.max_trades_per_day:
            return False, "Max trades reached"

        if abs(self.daily_pnl) >= self.capital * self.max_daily_loss:
            return False, "Daily loss limit hit"

        risk_amount = stop_loss_points * lot_value
        if risk_amount > self.capital * self.max_risk_per_trade:
            return False, "Risk per trade too high"

        return True, "Trade allowed"

    def register_trade(self):
        self.trades_today += 1

    def register_pnl(self, pnl):
        self.daily_pnl += pnl

