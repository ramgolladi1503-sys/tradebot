"""Trade identity helpers.

Migration note:
Adds deterministic trade_key generation to deduplicate repeated trade ideas.
"""

from __future__ import annotations

import hashlib
from typing import Any


def _norm_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _norm_strike(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    text = str(value).strip().upper()
    if text == "ATM":
        return "ATM"
    try:
        return str(float(text))
    except Exception:
        return "UNKNOWN"


def _norm_expiry(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    text = str(value).strip()
    if not text:
        return "UNKNOWN"
    if "T" in text:
        text = text.split("T", 1)[0]
    return text


def derive_strategy_id(strategy_id: Any, fallback: Any | None = None) -> str:
    base = _norm_text(strategy_id)
    if base:
        return base
    return _norm_text(fallback) or "UNKNOWN"


def compute_trade_key(
    symbol: Any,
    expiry_date: Any,
    strike: Any,
    option_type: Any,
    side: Any,
    strategy_id: Any,
) -> str:
    sym = _norm_text(symbol) or "UNKNOWN"
    exp = _norm_expiry(expiry_date)
    stk = _norm_strike(strike)
    opt = _norm_text(option_type) or "UNKNOWN"
    sde = _norm_text(side) or "UNKNOWN"
    strat = derive_strategy_id(strategy_id)
    raw = f"{sym}|{exp}|{stk}|{opt}|{sde}|{strat}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

