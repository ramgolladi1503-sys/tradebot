from config import config as cfg

class ExecutionGuard:
    def __init__(self, risk_state=None):
        self.risk_state = risk_state
    def _min_conf(self, regime):
        min_conf = getattr(cfg, "ML_MIN_PROBA", 0.6)
        mult = getattr(cfg, "REGIME_PROBA_MULT", {}).get(regime or "NEUTRAL", 1.0)
        return min_conf * mult

    def validate(self, trade, portfolio, regime):
        if self.risk_state:
            ok, reason = self.risk_state.approve(trade)
            if not ok:
                return False, f"RiskState: {reason}"
        min_conf = self._min_conf(regime)
        if trade.confidence < min_conf:
            return False, "Low confidence"

        if trade.capital_at_risk > portfolio.get("capital", 0):
            return False, "Insufficient capital"

        if regime == "RANGE" and trade.strategy == "TREND":
            return False, "Regime mismatch"

        return True, "Approved"
