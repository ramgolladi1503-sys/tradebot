"""
Pro Strategy Engine (Next-level architecture)

Goal:
- Replace shallow signal logic with layered strategy system
- Separate signal generation, scoring, and routing
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ProSignal:
    name: str
    direction: str
    score: float
    confidence: float
    reason: str


class StrategyBase:
    def generate(self, market_data: dict) -> Optional[ProSignal]:
        raise NotImplementedError


# -----------------------------
# STRATEGY LAYERS
# -----------------------------

class VolatilityExpansionStrategy(StrategyBase):
    def generate(self, market_data):
        atr = market_data.get("atr", 0)
        ltp_change = market_data.get("ltp_change", 0)

        if atr > 0 and abs(ltp_change) > atr * 0.5:
            direction = "BUY_CALL" if ltp_change > 0 else "BUY_PUT"
            return ProSignal(
                name="vol_expansion",
                direction=direction,
                score=0.75,
                confidence=0.7,
                reason="ATR expansion move",
            )
        return None


class LiquidityImbalanceStrategy(StrategyBase):
    def generate(self, market_data):
        bid_qty = market_data.get("bid_qty", 0)
        ask_qty = market_data.get("ask_qty", 0)

        if bid_qty > ask_qty * 1.5:
            return ProSignal("liquidity", "BUY_CALL", 0.7, 0.65, "Bid dominance")
        if ask_qty > bid_qty * 1.5:
            return ProSignal("liquidity", "BUY_PUT", 0.7, 0.65, "Ask dominance")
        return None


class TimeBasedStrategy(StrategyBase):
    def generate(self, market_data):
        hour = market_data.get("hour", 0)

        if 9 <= hour <= 10:
            return ProSignal("time_open", "BUY_CALL", 0.6, 0.6, "Opening momentum")
        if 14 <= hour <= 15:
            return ProSignal("time_close", "BUY_CALL", 0.65, 0.6, "Closing trend")
        return None


# -----------------------------
# ENGINE
# -----------------------------

class ProStrategyEngine:
    def __init__(self):
        self.strategies: List[StrategyBase] = [
            VolatilityExpansionStrategy(),
            LiquidityImbalanceStrategy(),
            TimeBasedStrategy(),
        ]

    def run(self, market_data: dict) -> List[ProSignal]:
        signals = []

        for strat in self.strategies:
            try:
                sig = strat.generate(market_data)
                if sig:
                    signals.append(sig)
            except Exception:
                continue

        return signals
