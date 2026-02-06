from typing import Dict

class RegimeDetector:
    """
    Simple multi-factor regime detection.
    """

    def __init__(self, vwap_period=20, atr_period=14):
        self.vwap_period = vwap_period
        self.atr_period = atr_period

    def detect(self, symbol_data: Dict) -> str:
        """
        Returns one of:
        'TRENDING_BULL', 'TRENDING_BEAR', 'CHOPPY', 'VOLATILE'
        """
        # crude placeholder logic — replace with real indicators
        close = symbol_data['close']
        atr = symbol_data['atr']

        if close[-1] > sum(close[-self.vwap_period:])/self.vwap_period:
            trend = 'BULL'
        else:
            trend = 'BEAR'

        if atr[-1] > max(atr[-self.atr_period:]):
            return 'VOLATILE'

        if max(close[-5:]) - min(close[-5:]) < atr[-1]:
            return 'CHOPPY'

        return f"TRENDING_{trend}"

