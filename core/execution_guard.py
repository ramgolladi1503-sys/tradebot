from config import config as cfg

class ExecutionGuard:
    def _min_conf(self, regime):
        min_conf = getattr(cfg, "ML_MIN_PROBA", 0.6)
        mult = getattr(cfg, "REGIME_PROBA_MULT", {}).get(regime or "NEUTRAL", 1.0)
        return min_conf * mult

    def validate(self, trade, portfolio, regime):
        min_conf = self._min_conf(regime)
        if trade.confidence < min_conf:
            return False, "Low confidence"

        if trade.capital_at_risk > portfolio.get("capital", 0):
            return False, "Insufficient capital"

        if regime == "RANGE" and trade.strategy == "TREND":
            return False, "Regime mismatch"

        return True, "Approved"
