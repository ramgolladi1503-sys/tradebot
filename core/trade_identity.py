"""Trade identity helpers.

Migration note:
Adds deterministic trade_key generation to deduplicate repeated trade ideas.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


def _norm_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _norm_slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


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


_GENERIC_STRATEGY_IDS = {"", "core", "unknown", "legacy_queue", "no_signal_planning"}
_STRATEGY_FAMILY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "breakout",
        (
            "breakout",
            "orb",
            "opening_range",
            "opening range",
            "range_break",
            "momentum",
            "trend_break",
        ),
    ),
    (
        "pullback",
        (
            "pullback",
            "retest",
            "retracement",
            "retrace",
            "dip",
            "buy_the_dip",
        ),
    ),
    (
        "mean_reversion",
        (
            "mean_reversion",
            "mean reversion",
            "reversion",
            "fade",
            "contrarian",
            "revert",
        ),
    ),
    (
        "volatility_expansion",
        (
            "volatility_expansion",
            "volatility expansion",
            "vol_expansion",
            "zero_hero",
            "zero hero",
            "quick_synth",
            "quick synth",
            "quick_opt",
            "quick opt",
            "gamma",
            "expansion",
        ),
    ),
)


def infer_candidate_identity(payload: Any) -> dict[str, str]:
    if isinstance(payload, dict):
        get_value = payload.get
    else:
        get_value = lambda key, default=None: getattr(payload, key, default)

    explicit_candidate_type = _norm_slug(get_value("candidate_type"))
    explicit_family = _norm_slug(get_value("strategy_family"))
    explicit_variant = _norm_slug(get_value("setup_variant"))

    raw_texts = [
        get_value("strategy_id"),
        get_value("strategy_name"),
        get_value("strategy"),
        get_value("generator"),
        get_value("entry_condition"),
        get_value("trade_id"),
    ]
    source_flags = get_value("source_flags") if isinstance(get_value("source_flags"), dict) else {}
    if isinstance(source_flags, dict):
        raw_texts.extend(
            [
                source_flags.get("pattern"),
                source_flags.get("setup"),
                source_flags.get("strategy"),
            ]
        )
        pattern_flags = source_flags.get("pattern_flags")
        if isinstance(pattern_flags, (list, tuple, set)):
            raw_texts.extend(pattern_flags)
    pattern_flags = get_value("pattern_flags")
    if isinstance(pattern_flags, (list, tuple, set)):
        raw_texts.extend(pattern_flags)

    normalized_texts = [str(text or "").strip().lower() for text in raw_texts if str(text or "").strip()]
    strategy_family = explicit_family if explicit_family else "unknown"
    if strategy_family == "unknown":
        for family, keywords in _STRATEGY_FAMILY_KEYWORDS:
            if any(keyword in text for text in normalized_texts for keyword in keywords):
                strategy_family = family
                break

    instrument = _norm_text(get_value("instrument_type") or get_value("instrument"))
    if explicit_candidate_type:
        candidate_type = explicit_candidate_type
    elif instrument == "OPT":
        candidate_type = "options"
    elif instrument in {"EQ", "STOCK"}:
        candidate_type = "equity"
    elif instrument in {"FUT", "FUTURE", "FUTURES"}:
        candidate_type = "futures"
    else:
        candidate_type = "unknown"

    setup_variant = explicit_variant
    if not setup_variant:
        for field in ("setup_variant", "strategy_name", "strategy", "strategy_id", "generator", "entry_condition"):
            candidate = _norm_slug(get_value(field))
            if candidate and candidate not in _GENERIC_STRATEGY_IDS:
                setup_variant = candidate
                break
    if not setup_variant:
        setup_variant = strategy_family or "unknown"
    if not setup_variant:
        setup_variant = "unknown"

    direction = str(get_value("direction") or "").strip()
    if not direction:
        side = _norm_text(get_value("side"))
        option_type = _norm_text(get_value("option_type") or get_value("type"))
        if side and option_type in {"CE", "CALL"}:
            direction = f"{side}_CALL"
        elif side and option_type in {"PE", "PUT"}:
            direction = f"{side}_PUT"
        elif side:
            direction = side
        else:
            direction = "UNKNOWN"

    return {
        "candidate_type": candidate_type or "unknown",
        "strategy_family": strategy_family or "unknown",
        "setup_variant": setup_variant or "unknown",
        "direction": direction or "UNKNOWN",
    }


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
    return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
