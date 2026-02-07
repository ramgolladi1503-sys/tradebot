from typing import Dict
from core.market_data import get_current_regime


class RegimeDetector:
    """
    LEGACY WRAPPER; DO NOT ADD LOGIC.
    """

    def __init__(self, vwap_period=20, atr_period=14):
        self.vwap_period = vwap_period
        self.atr_period = atr_period

    def detect(self, symbol_data: Dict) -> Dict:
        """
        Returns canonical regime snapshot dict.
        """
        symbol = symbol_data.get("symbol") if isinstance(symbol_data, dict) else None
        snap = get_current_regime(symbol)
        return {
            "regime": snap.get("primary_regime", "NEUTRAL"),
            **snap,
        }
