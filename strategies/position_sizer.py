# strategies/position_sizer.py

class PositionSizer:
    def __init__(self, capital, risk_per_trade=0.01):
        self.capital = capital
        self.risk_per_trade = risk_per_trade

    def calculate_quantity(self, stop_loss_points, lot_value):
        max_risk_amount = self.capital * self.risk_per_trade
        qty = max_risk_amount / (stop_loss_points * lot_value)

        return max(1, int(qty))

