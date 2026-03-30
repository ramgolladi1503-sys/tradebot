from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class HistoricalOptionChainConfig:
    strike_step: int = 50
    strikes_around: int = 4
    base_premium_ratio: float = 0.004
    max_spread_pct: float = 0.01
    default_volume: int = 1000
    default_oi: int = 5000


class HistoricalOptionChainBuilder:
    """Build a deterministic synthetic option chain from underlying candles.

    This is not real options history. It is a controlled replay approximation so the
    existing TradeBuilder can run against historical candles without silently falling
    back to live broker calls.
    """

    def __init__(self, config: HistoricalOptionChainConfig | None = None):
        self.config = config or HistoricalOptionChainConfig()

    def build_for_row(self, row: dict, symbol: str = "NIFTY") -> list[dict]:
        ltp = float(row.get("close") or row.get("ltp") or 0.0)
        timestamp = pd.to_datetime(row.get("timestamp"))
        if ltp <= 0:
            return []

        step = int(self.config.strike_step)
        atm = int(round(ltp / step) * step)
        expiry = self._infer_expiry(timestamp)
        chain: list[dict] = []

        for strike in self._strike_grid(atm):
            distance_steps = abs(strike - atm) / max(step, 1)
            base_premium = max(5.0, ltp * self.config.base_premium_ratio)
            premium = round(base_premium * (1.0 + (distance_steps * 0.12)), 2)
            spread = max(0.5, premium * self.config.max_spread_pct)
            bid = round(max(0.05, premium - (spread / 2.0)), 2)
            ask = round(premium + (spread / 2.0), 2)
            moneyness = (ltp - strike) / max(ltp, 1e-6)
            for opt_type in ("CE", "PE"):
                chain.append(
                    {
                        "symbol": symbol,
                        "strike": strike,
                        "type": opt_type,
                        "ltp": premium,
                        "last_price": premium,
                        "bid": bid,
                        "ask": ask,
                        "best_bid": bid,
                        "best_ask": ask,
                        "mid_price": round((bid + ask) / 2.0, 2),
                        "mark_price": premium,
                        "price_source": "historical_replay",
                        "quote_source": "historical_replay",
                        "option_ltp_source": "historical_replay",
                        "quote_ok": True,
                        "quote_live": False,
                        "quote_age_sec": 0.0,
                        "volume": int(self.config.default_volume),
                        "oi": int(self.config.default_oi),
                        "oi_change": 0,
                        "spread_pct": (ask - bid) / max(premium, 1e-6),
                        "moneyness": moneyness,
                        "expiry": expiry,
                        "expiry_date": expiry,
                        "tradingsymbol": f"{symbol}{expiry.replace('-', '')}{int(strike)}{opt_type}",
                        "instrument_token": int(abs(hash((symbol, expiry, strike, opt_type))) % 10**9),
                        "chain_source": "historical_replay",
                        "planning_only": True,
                        "timestamp": timestamp.timestamp(),
                    }
                )
        return chain

    def _strike_grid(self, atm: int) -> Iterable[int]:
        width = int(self.config.strikes_around)
        step = int(self.config.strike_step)
        for i in range(-width, width + 1):
            yield atm + (i * step)

    @staticmethod
    def _infer_expiry(timestamp: pd.Timestamp) -> str:
        # Simple weekly Thursday expiry approximation.
        ts = pd.Timestamp(timestamp)
        days_ahead = (3 - ts.weekday()) % 7
        expiry = (ts + pd.Timedelta(days=days_ahead)).date()
        return expiry.isoformat()
