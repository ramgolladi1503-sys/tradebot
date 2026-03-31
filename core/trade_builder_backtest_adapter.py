from __future__ import annotations

from typing import Optional, Dict, Any

from strategies.trade_builder import TradeBuilder
from core.historical_option_chain import HistoricalOptionChainBuilder


class TradeBuilderBacktestAdapter:
    def __init__(self):
        self.builder = TradeBuilder()
        self.chain_builder = HistoricalOptionChainBuilder()

    def __call__(self, market: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        symbol = market.get("symbol", "NIFTY")
        market = dict(market)
        market["option_chain"] = self.chain_builder.build_for_row(market, symbol=symbol)
        trade = self.builder.build(market)
        if not trade:
            return None
        try:
            return {
                "entry": float(getattr(trade, "entry_price", 0.0)),
                "target": float(getattr(trade, "target", 0.0)),
                "stop": float(getattr(trade, "stop_loss", 0.0)),
                "qty": int(getattr(trade, "qty", 1)),
                "side": str(getattr(trade, "side", "BUY")),
            }
        except Exception:
            return None
