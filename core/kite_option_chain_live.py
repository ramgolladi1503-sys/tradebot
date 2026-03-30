from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from core.kite_client import kite_client


@dataclass
class KiteOptionChainConfig:
    exchange: str = "NFO"
    strike_window: int = 6


class KiteLiveOptionChainBuilder:
    def __init__(self, config: KiteOptionChainConfig | None = None):
        self.cfg = config or KiteOptionChainConfig()

    def build(self, symbol: str, spot: float) -> list[dict]:
        kite = kite_client.ensure()
        instruments = kite_client.instruments_cached(self.cfg.exchange)

        expiry = self._nearest_expiry(instruments, symbol)
        if not expiry:
            return []

        options = [i for i in instruments if i.get("name") == symbol and i.get("expiry") == expiry]

        strikes = sorted({i.get("strike") for i in options if i.get("strike")})
        if not strikes:
            return []

        atm = min(strikes, key=lambda x: abs(x - spot))
        window = [s for s in strikes if abs(s - atm) <= self.cfg.strike_window * 50]

        tradingsymbols = [f"{self.cfg.exchange}:{i['tradingsymbol']}" for i in options if i.get("strike") in window]

        quotes = kite.quote(tradingsymbols)

        chain = []
        for i in options:
            key = f"{self.cfg.exchange}:{i['tradingsymbol']}"
            q = quotes.get(key)
            if not q:
                continue

            depth = q.get("depth", {})
            bid = depth.get("buy", [{}])[0].get("price")
            ask = depth.get("sell", [{}])[0].get("price")

            chain.append({
                "symbol": symbol,
                "strike": i.get("strike"),
                "type": i.get("instrument_type"),
                "ltp": q.get("last_price"),
                "bid": bid,
                "ask": ask,
                "oi": q.get("oi"),
                "volume": q.get("volume"),
                "quote_ok": True,
            })

        return chain

    def _nearest_expiry(self, instruments, symbol):
        expiries = sorted({i.get("expiry") for i in instruments if i.get("name") == symbol})
        return expiries[0] if expiries else None
