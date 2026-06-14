from typing import Dict, Any

class RegimeClassifier:
    """
    Elite Regime Classifier.
    Calculates current market environment based on quantitative indicators.
    """

    def calculate_volatility_risk_premium(self, iv: float, rv: float) -> float:
        """
        Calculates Volatility Risk Premium (VRP).
        VRP = Implied Volatility (IV) - Realized Volatility (RV)
        """
        if iv is None or rv is None:
            return 0.0
        return iv - rv

    def classify_regime(self, market_data: Dict[str, Any]) -> str:
        """
        Classifies the market into one of four states:
        HIGH_VOL_TREND, LOW_VOL_CHOP, MEAN_REVERT_SKEW, EVENT_SHOCK.
        
        Expected keys in market_data:
        - iv (float): Implied Volatility
        - rv (float): Realized Volatility
        - ib_volume_ratio (float): First Hour Initial Balance volume ratio vs 30-day average
        - is_event_day (bool): True if macroeconomic event or shock occurred
        """
        is_event = market_data.get("is_event_day", False)
        if is_event:
            return "EVENT_SHOCK"
            
        iv = market_data.get("iv", 0.0)
        rv = market_data.get("rv", 0.0)
        ib_vol_ratio = market_data.get("ib_volume_ratio", 1.0)
        
        vrp = self.calculate_volatility_risk_premium(iv, rv)
        
        # High volatility and high volume pushing through IB usually signals a strong trend
        if rv > 20.0 and ib_vol_ratio > 1.2:
            return "HIGH_VOL_TREND"
            
        # If IV is significantly higher than RV, dealers are pricing in skew/premium,
        # often leading to mean reversion as premium decays.
        if vrp > 5.0:
            return "MEAN_REVERT_SKEW"
            
        # Low volatility, low volume means chop
        if rv <= 15.0 and ib_vol_ratio < 0.8:
            return "LOW_VOL_CHOP"
            
        # Default fallback
        return "LOW_VOL_CHOP"

def get_current_regime(market_data: Dict[str, Any]) -> str:
    """Convenience function to classify regime without instantiating the class manually."""
    classifier = RegimeClassifier()
    return classifier.classify_regime(market_data)
