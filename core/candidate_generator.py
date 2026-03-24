from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from config import config as cfg


logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _parse_symbols(raw: str) -> list[str]:
    if not raw:
        return []
    return [sym.strip().upper() for sym in raw.split(",") if sym.strip()]


def _parse_strategy_families(raw: str) -> list[str]:
    if not raw:
        return []
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _nearest_expiry(chain_rows: list[dict[str, Any]]) -> str | None:
    expiries: list[str] = []
    for row in chain_rows or []:
        exp = row.get("expiry_date") or row.get("expiry")
        if exp:
            expiries.append(str(exp))
    if not expiries:
        return None
    return sorted(expiries)[0]


def _strike_step(strikes: list[float]) -> float | None:
    if len(strikes) < 2:
        return None
    deltas = [abs(strikes[i + 1] - strikes[i]) for i in range(len(strikes) - 1)]
    deltas = [d for d in deltas if d > 0]
    if not deltas:
        return None
    return min(deltas)


def generate_candidates(
    market_data_by_symbol: dict[str, dict[str, Any]] | None,
    *,
    ts_epoch: float | None = None,
) -> list[dict[str, Any]]:
    if ts_epoch is None:
        ts_epoch = time.time()
    market_data_by_symbol = market_data_by_symbol or {}
    symbols = _parse_symbols(getattr(cfg, "V2_CANDIDATE_SYMBOLS", "NIFTY,BANKNIFTY"))
    strategy_families = _parse_strategy_families(
        getattr(cfg, "V2_CANDIDATE_STRATEGY_FAMILIES", "breakout,mean_reversion,volatility_expansion,expiry_momentum")
    )
    strike_window = int(getattr(cfg, "V2_CANDIDATE_STRIKE_WINDOW", 2))

    candidates: list[dict[str, Any]] = []
    counts_by_symbol: dict[str, int] = {}
    counts_by_family: dict[str, int] = {}

    for symbol in symbols:
        market_data = market_data_by_symbol.get(symbol, {})
        chain = list(market_data.get("option_chain") or [])
        strikes = sorted({s for s in (_safe_float(row.get("strike")) for row in chain) if s is not None})
        spot = _safe_float(
            market_data.get("underlying_spot")
            or market_data.get("spot")
            or market_data.get("ltp")
            or market_data.get("current_ltp")
        )
        atm = None
        if strikes and spot is not None:
            atm = min(strikes, key=lambda s: abs(float(s) - float(spot)))
        elif strikes:
            atm = strikes[len(strikes) // 2]
        step = _strike_step(strikes) or _safe_float(market_data.get("strike_step")) or 0.0
        expiry = _nearest_expiry(chain)

        if atm is None or step <= 0:
            logger.debug("candidate_generator_no_strikes symbol=%s", symbol)
            continue

        strike_list: list[float] = []
        for offset in range(-strike_window, strike_window + 1):
            strike_list.append(float(atm) + float(step) * float(offset))

        for strike in strike_list:
            for option_type in ("CE", "PE"):
                for family in strategy_families:
                    candidate = {
                        "symbol": symbol,
                        "strike": strike,
                        "option_type": option_type,
                        "expiry": expiry,
                        "strategy_family": family,
                        "timestamp": ts_epoch,
                        "timestamp_utc": datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat(),
                        "source": "candidate_generator_v2",
                    }
                    candidates.append(candidate)
                    counts_by_symbol[symbol] = counts_by_symbol.get(symbol, 0) + 1
                    counts_by_family[family] = counts_by_family.get(family, 0) + 1

    logger.info(
        "candidate_generator_v2_counts total=%s by_symbol=%s by_strategy_family=%s",
        len(candidates),
        counts_by_symbol,
        counts_by_family,
    )
    return candidates
