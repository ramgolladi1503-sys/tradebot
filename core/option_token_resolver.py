"""Option instrument token resolver.

Migration note:
Resolves option instrument tokens without caching per-expiry results.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Any

from config import config as cfg
from core.kite_client import kite_client
from core.log_writer import get_jsonl_writer
from core.paths import logs_dir

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
    exchange = (exchange or ("BFO" if sym == "SENSEX" else "NFO")).upper()
    segment = "NFO-OPT" if exchange == "NFO" else "BFO-OPT"
    try:
        data = kite_client.instruments_cached(exchange, ttl_sec=0)
    except Exception:
        data = []
    if not data:
        _LOGGER.write(
            {
                "ts": datetime.utcnow().isoformat(),
                "event": "OPTION_TOKEN_RESOLUTION_EMPTY",
                "symbol": sym,
                "expiry": str(exp),
                "strike": strike,
                "option_type": opt_type,
                "exchange": exchange,
            }
        )
        return None
    for inst in data:
        if inst.get("segment") != segment:
            continue
        if _norm_text(inst.get("name")) != sym:
            continue
        inst_exp = _coerce_expiry(inst.get("expiry"))
        if inst_exp != exp:
            continue
        try:
            inst_strike = float(inst.get("strike"))
        except Exception:
            continue
        if abs(inst_strike - float(strike)) > 1e-6:
            continue
        if _norm_text(inst.get("instrument_type")) != opt_type:
            continue
        token = inst.get("instrument_token")
        if not token:
            continue
        payload = {
            "instrument_token": int(token),
            "tradingsymbol": inst.get("tradingsymbol"),
            "exchange": exchange,
            "segment": segment,
        }
        _LOGGER.write(
            {
                "ts": datetime.utcnow().isoformat(),
                "event": "OPTION_TOKEN_RESOLVED",
                "symbol": sym,
                "expiry": str(exp),
                "strike": float(strike),
                "option_type": opt_type,
                "instrument_token": int(token),
                "tradingsymbol": inst.get("tradingsymbol"),
                "exchange": exchange,
            }
        )
        return payload
    _LOGGER.write(
        {
            "ts": datetime.utcnow().isoformat(),
            "event": "OPTION_TOKEN_NOT_FOUND",
            "symbol": sym,
            "expiry": str(exp),
            "strike": float(strike),
            "option_type": opt_type,
            "exchange": exchange,
        }
    )
    return None

