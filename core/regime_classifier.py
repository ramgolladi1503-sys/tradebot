from typing import Dict, Any

class RegimeClassifier:
    """
    Elite Regime Classifier.
    Calculates current market environment based on quantitative indicators.
    Now supports probabilistic Gaussian HMM classification.
    """
    def __init__(self):
        try:
            from core.math.hmm_regime import GaussianHMM
            self.hmm_model = GaussianHMM(n_components=3, n_iter=50)
        except ImportError:
            self.hmm_model = None
        self.is_hmm_fitted = False

    def fit_hmm(self, historical_data):
        """
        Fits the HMM model using historical market data.
        historical_data should be a list of [rv, vrp, ib_vol_ratio] observations.
        """
        if not historical_data or self.hmm_model is None:
            return
        import numpy as np
        X = np.array(historical_data)
        if len(X) > 10:  # Need enough samples
            self.hmm_model.fit(X)
            self.is_hmm_fitted = True

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
        # Allow explicit override from market_data
        manual_regime = market_data.get("regime")
        if manual_regime:
            return manual_regime
            
        is_event = market_data.get("is_event_day", False)
        if is_event:
            return "EVENT_SHOCK"
            
        iv = market_data.get("iv", 0.0)
        rv = market_data.get("rv", 0.0)
        ib_vol_ratio = market_data.get("ib_volume_ratio", 1.0)
        
        vrp = self.calculate_volatility_risk_premium(iv, rv)
        
        # Probabilistic HMM Classification
        if self.is_hmm_fitted and self.hmm_model is not None:
            import numpy as np
            X_new = np.array([[rv, vrp, ib_vol_ratio]])
            state = self.hmm_model.predict(X_new)[0]
            
            # Map HMM states dynamically based on their learned means
            # Feature 0: RV, Feature 1: VRP
            state_means = self.hmm_model.means_
            high_vol_state = np.argmax(state_means[:, 0])
            skew_state = np.argmax(state_means[:, 1])
            
            # If the high vol state is the same as the skew state, differentiate
            if high_vol_state == skew_state:
                # The one with the highest VRP relative to its RV is skew
                skew_state = np.argmax(state_means[:, 1] / (state_means[:, 0] + 1e-5))
                if skew_state == high_vol_state:
                    # Fallback to secondary high vol
                    high_vol_state = np.argsort(state_means[:, 0])[-2]
            
            if state == high_vol_state:
                return "HIGH_VOL_TREND"
            elif state == skew_state:
                return "MEAN_REVERT_SKEW"
            else:
                return "LOW_VOL_CHOP"
        
        # Fallback to static heuristics if HMM is not fitted
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
