"""Safe derivation helpers for dashboard exploration filters."""

from __future__ import annotations

import re


_UNDERLYING_ORDER = ("BANKNIFTY", "NIFTY", "SENSEX")
_OPTION_SIDE_RE = re.compile(r"(?:^|[^A-Z0-9])(CE|PE)(?:$|[^A-Z0-9])")


def _normalize_text(value) -> str:
    return str(value or "").strip().upper()


def parse_underlying(symbol) -> str:
    text = _normalize_text(symbol)
    if not text:
        return "UNKNOWN"
    for root in _UNDERLYING_ORDER:
        if root in text:
            return root
    return "UNKNOWN"


def parse_option_side(symbol) -> str:
    text = _normalize_text(symbol)
    if not text:
        return "UNKNOWN"
    if text.endswith("CE"):
        return "CE"
    if text.endswith("PE"):
        return "PE"
    if " CALL" in text or text.startswith("CALL ") or "-CALL" in text:
        return "CE"
    if " PUT" in text or text.startswith("PUT ") or "-PUT" in text:
        return "PE"
    match = _OPTION_SIDE_RE.search(text)
    if match:
        return match.group(1)
    return "UNKNOWN"


def map_strategy_category(strategy_hint) -> str:
    text = _normalize_text(strategy_hint)
    if not text or text == "UNKNOWN":
        return "UNKNOWN"

    if any(token in text for token in ("EVENT", "NEWS", "SPIKE")):
        return "EVENT"

    if any(
        token in text
        for token in (
            "MEAN",
            "REVERT",
            "RANGE",
            "SCALP",
            "MICRO",
            "PULLBACK",
            "FADE",
        )
    ):
        return "MEAN_REVERT"

    if any(token in text for token in ("TREND", "VWAP", "ORB", "MOMENTUM", "BREAKOUT")):
        return "TREND"

    return "UNKNOWN"
