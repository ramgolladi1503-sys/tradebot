"""Option instrument token resolver.

Migration note:
Resolves option instrument tokens without caching per-expiry results.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Any

from core.instruments import build_option_registry, log_requested_expiry_missing
from core.kite_client import kite_client
from core.log_writer import get_jsonl_writer
from core.paths import logs_dir
from core.time_utils import utc_now

_LOG_PATH = logs_dir() / "option_token_resolution.jsonl"
_LOGGER = get_jsonl_writer(_LOG_PATH)


def _coerce_expiry(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        text = str(value).split("T", 1)[0]
        return datetime.fromisoformat(text).date()
    except Exception:
        return None


def _norm_text(value: Any) -> str:
    return str(value or "").strip().upper()


def resolve_option_token(
    symbol: str,
    expiry_date: str | date,
    strike: float,
    option_type: str,
    exchange: str | None = None,
) -> dict | None:
    sym = _norm_text(symbol)
    opt_type = _norm_text(option_type)
    exp = _coerce_expiry(expiry_date)
    if not sym or not opt_type or exp is None or strike is None:
        return None
    try:
        strike_val = float(strike)
    except Exception:
        return None
    exchange = (exchange or ("BFO" if sym == "SENSEX" else "NFO")).upper()
    segment = "NFO-OPT" if exchange == "NFO" else "BFO-OPT"
    try:
        data = kite_client.instruments_cached(exchange, ttl_sec=0)
    except Exception:
        data = []
    if not data:
        _LOGGER.write(
            {
                "ts": utc_now().isoformat(),
                "event": "OPTION_TOKEN_RESOLUTION_EMPTY",
                "symbol": sym,
                "expiry": str(exp),
                "strike": strike,
                "option_type": opt_type,
                "exchange": exchange,
            }
        )
        return None
    registry_payload = build_option_registry(
        symbol=sym,
        instruments=data,
        exchange=exchange,
    )
    registry = registry_payload.get("registry") or {}
    key = (sym, segment, strike_val, opt_type, exp)
    entry = registry.get(key)
    if isinstance(entry, dict) and entry.get("instrument_token"):
        token = int(entry.get("instrument_token"))
        payload = {
            "instrument_token": token,
            "tradingsymbol": entry.get("tradingsymbol"),
            "exchange": exchange,
            "segment": segment,
        }
        _LOGGER.write(
            {
                "ts": utc_now().isoformat(),
                "event": "OPTION_TOKEN_RESOLVED",
                "symbol": sym,
                "expiry": str(exp),
                "strike": float(strike_val),
                "option_type": opt_type,
                "instrument_token": token,
                "tradingsymbol": entry.get("tradingsymbol"),
                "exchange": exchange,
            }
        )
        return payload
    available_expiries = sorted(
        {
            k[4]
            for k in registry.keys()
            if k[0] == sym and k[1] == segment and k[3] == opt_type and abs(float(k[2]) - strike_val) <= 1e-6
        }
    )
    if available_expiries:
        log_requested_expiry_missing(
            symbol=sym,
            requested_expiry=exp,
            available_expiries=available_expiries,
            context="option_token_resolver",
        )
    _LOGGER.write(
        {
            "ts": utc_now().isoformat(),
            "event": "OPTION_TOKEN_NOT_FOUND",
            "symbol": sym,
            "expiry": str(exp),
            "strike": float(strike_val),
            "option_type": opt_type,
            "exchange": exchange,
            "available_expiries": [d.isoformat() for d in available_expiries],
        }
    )
    return None
