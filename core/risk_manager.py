from datetime import date

class RiskManager:
    def __init__(self, capital: float, max_loss_pct=0.02, max_trades=3):
        self.capital = capital
        self.max_loss = capital * max_loss_pct
        self.max_trades = max_trades
        self.reset()

    def reset(self):
        self.day = date.today()
        self.loss_today = 0
        self.trades_today = 0
        self.locked = False

    def check_new_day(self):
        if date.today() != self.day:
            self.reset()

    def record_trade(self, pnl: float):
        self.check_new_day()

        self.trades_today += 1
        if pnl < 0:
            self.loss_today += abs(pnl)

        if (
            self.loss_today >= self.max_loss or
            self.trades_today >= self.max_trades
        ):
            self.locked = True

    def can_trade(self) -> bool:
        self.check_new_day()
        return not self.locked

