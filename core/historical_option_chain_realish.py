from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, log, sqrt
from typing import Iterable

import pandas as pd


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


@dataclass(frozen=True)
class RealishOptionChainConfig:
    strike_step: int = 50
    strikes_around: int = 6
    risk_free_rate: float = 0.06
    min_iv: float = 0.10
    base_iv: float = 0.18
    max_iv: float = 0.55
    smile_per_step: float = 0.015
    skew_per_step: float = 0.006
    min_spread_pct: float = 0.008
    max_spread_pct: float = 0.025
    default_volume: int = 1200
    default_oi: int = 6000
    volume_decay: float = 0.22
    oi_decay: float = 0.12


class RealishHistoricalOptionChainBuilder:
    """Semi-realistic option-chain simulator for replay backtests.

    This is still synthetic, but it is materially better than a flat premium model.
    It adds:
    - Black-Scholes-ish premium curve
    - IV smile/skew by strike distance and side
    - Time-to-expiry decay
    - OI and volume concentrated around ATM
    - Wider spreads for far OTM strikes
    """

    def __init__(self, config: RealishOptionChainConfig | None = None):
        self.config = config or RealishOptionChainConfig()

    def build_for_row(self, row: dict, symbol: str = "NIFTY") -> list[dict]:
        spot = float(row.get("close") or row.get("ltp") or 0.0)
        timestamp = pd.to_datetime(row.get("timestamp"))
        if spot <= 0:
            return []

        step = int(self.config.strike_step)
        atm = int(round(spot / step) * step)
        expiry_ts = self._infer_expiry_ts(timestamp)
        t = max((expiry_ts - timestamp).total_seconds() / (365.0 * 24.0 * 3600.0), 1e-5)
        tte_hrs = max((expiry_ts - timestamp).total_seconds() / 3600.0, 0.01)

        chain: list[dict] = []
        for strike in self._strike_grid(atm):
            distance_steps = abs(strike - atm) / max(step, 1)
            moneyness = (spot - strike) / max(spot, 1e-6)
            for opt_type in ("CE", "PE"):
                iv = self._iv_for_strike(distance_steps=distance_steps, opt_type=opt_type)
                premium = self._bs_price(spot=spot, strike=float(strike), t=t, iv=iv, opt_type=opt_type)
                premium = max(0.5, round(premium, 2))

                spread_pct = min(
                    self.config.max_spread_pct,
                    self.config.min_spread_pct + (distance_steps * 0.0025),
                )
                spread = max(0.5, premium * spread_pct)
                bid = round(max(0.05, premium - (spread / 2.0)), 2)
                ask = round(premium + (spread / 2.0), 2)

                volume = max(50, int(self.config.default_volume * exp(-self.config.volume_decay * distance_steps)))
                oi = max(100, int(self.config.default_oi * exp(-self.config.oi_decay * distance_steps)))

                delta = self._delta(spot=spot, strike=float(strike), t=t, iv=iv, opt_type=opt_type)
                gamma = self._gamma(spot=spot, strike=float(strike), t=t, iv=iv)
                theta = self._theta(spot=spot, strike=float(strike), t=t, iv=iv, opt_type=opt_type)
                vega = self._vega(spot=spot, strike=float(strike), t=t, iv=iv)

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
                        "price_source": "historical_replay_realish",
                        "quote_source": "historical_replay_realish",
                        "option_ltp_source": "historical_replay_realish",
                        "quote_ok": True,
                        "quote_live": False,
                        "quote_age_sec": 0.0,
                        "quote_tradable": True,
                        "volume": volume,
                        "current_volume": volume,
                        "oi": oi,
                        "oi_change": 0,
                        "spread_pct": (ask - bid) / max(premium, 1e-6),
                        "moneyness": moneyness,
                        "iv": round(iv, 4),
                        "delta": round(delta, 4),
                        "gamma": round(gamma, 6),
                        "theta": round(theta, 4),
                        "vega": round(vega, 4),
                        "days_to_expiry": max((expiry_ts.date() - timestamp.date()).days, 1),
                        "time_to_expiry_hrs": round(tte_hrs, 2),
                        "expiry": expiry_ts.date().isoformat(),
                        "expiry_date": expiry_ts.date().isoformat(),
                        "tradingsymbol": f"{symbol}{expiry_ts.strftime('%Y%m%d')}{int(strike)}{opt_type}",
                        "instrument_token": int(abs(hash((symbol, expiry_ts.date().isoformat(), strike, opt_type))) % 10**9),
                        "chain_source": "historical_replay_realish",
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
    def _infer_expiry_ts(timestamp: pd.Timestamp) -> pd.Timestamp:
        ts = pd.Timestamp(timestamp)
        days_ahead = (3 - ts.weekday()) % 7
        expiry_date = (ts + pd.Timedelta(days=days_ahead)).normalize()
        return expiry_date + pd.Timedelta(hours=15, minutes=30)

    def _iv_for_strike(self, *, distance_steps: float, opt_type: str) -> float:
        smile = self.config.smile_per_step * distance_steps
        skew = self.config.skew_per_step * distance_steps
        iv = self.config.base_iv + smile
        if opt_type == "PE":
            iv += skew
        else:
            iv -= min(skew * 0.5, 0.03)
        return max(self.config.min_iv, min(self.config.max_iv, iv))

    def _d1(self, *, spot: float, strike: float, t: float, iv: float) -> float:
        return (log(spot / strike) + (self.config.risk_free_rate + 0.5 * iv * iv) * t) / max(iv * sqrt(t), 1e-9)

    def _d2(self, *, d1: float, t: float, iv: float) -> float:
        return d1 - (iv * sqrt(t))

    def _bs_price(self, *, spot: float, strike: float, t: float, iv: float, opt_type: str) -> float:
        d1 = self._d1(spot=spot, strike=strike, t=t, iv=iv)
        d2 = self._d2(d1=d1, t=t, iv=iv)
        discounted_strike = strike * exp(-self.config.risk_free_rate * t)
        if opt_type == "CE":
            return (spot * _norm_cdf(d1)) - (discounted_strike * _norm_cdf(d2))
        return (discounted_strike * _norm_cdf(-d2)) - (spot * _norm_cdf(-d1))

    def _delta(self, *, spot: float, strike: float, t: float, iv: float, opt_type: str) -> float:
        d1 = self._d1(spot=spot, strike=strike, t=t, iv=iv)
        if opt_type == "CE":
            return _norm_cdf(d1)
        return _norm_cdf(d1) - 1.0

    def _gamma(self, *, spot: float, strike: float, t: float, iv: float) -> float:
        d1 = self._d1(spot=spot, strike=strike, t=t, iv=iv)
        pdf = exp(-0.5 * d1 * d1) / sqrt(2.0 * 3.141592653589793)
        return pdf / max(spot * iv * sqrt(t), 1e-9)

    def _vega(self, *, spot: float, strike: float, t: float, iv: float) -> float:
        d1 = self._d1(spot=spot, strike=strike, t=t, iv=iv)
        pdf = exp(-0.5 * d1 * d1) / sqrt(2.0 * 3.141592653589793)
        return spot * pdf * sqrt(t) * 0.01

    def _theta(self, *, spot: float, strike: float, t: float, iv: float, opt_type: str) -> float:
        d1 = self._d1(spot=spot, strike=strike, t=t, iv=iv)
        d2 = self._d2(d1=d1, t=t, iv=iv)
        pdf = exp(-0.5 * d1 * d1) / sqrt(2.0 * 3.141592653589793)
        first = -(spot * pdf * iv) / (2.0 * sqrt(t))
        discounted_strike = strike * exp(-self.config.risk_free_rate * t)
        if opt_type == "CE":
            second = -self.config.risk_free_rate * discounted_strike * _norm_cdf(d2)
        else:
            second = self.config.risk_free_rate * discounted_strike * _norm_cdf(-d2)
        return (first + second) / 365.0
