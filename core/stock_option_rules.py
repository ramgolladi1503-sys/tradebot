from __future__ import annotations

import os

from config.stock_option_universe import DEFAULT_STOCK_OPTION_UNIVERSE


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return list(default)
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def _env_strategy_families(name: str, default: list[str]) -> list[str]:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return list(default)
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def stock_option_v2_enabled() -> bool:
    return _env_flag("ENABLE_STOCK_OPTION_CANDIDATE_GENERATOR_V2", False)


def load_stock_option_rules() -> dict[str, object]:
    default_symbols = list(DEFAULT_STOCK_OPTION_UNIVERSE.keys())
    symbols = [symbol for symbol in _env_list("STOCK_OPTION_V2_SYMBOLS", default_symbols) if symbol in DEFAULT_STOCK_OPTION_UNIVERSE]
    if not symbols:
        symbols = default_symbols[:3]

    min_oi = max(_env_float("STOCK_OPTION_V2_MIN_OI", 50000.0), min(float(DEFAULT_STOCK_OPTION_UNIVERSE[symbol]["min_oi"]) for symbol in symbols))
    min_volume = max(_env_float("STOCK_OPTION_V2_MIN_VOLUME", 10000.0), min(float(DEFAULT_STOCK_OPTION_UNIVERSE[symbol]["min_volume"]) for symbol in symbols))
    max_spread_pct = min(_env_float("STOCK_OPTION_V2_MAX_SPREAD_PCT", 1.10), max(float(DEFAULT_STOCK_OPTION_UNIVERSE[symbol]["max_spread_pct"]) for symbol in symbols))
    max_quote_age_sec = min(_env_float("STOCK_OPTION_V2_MAX_QUOTE_AGE_SEC", 2.5), max(float(DEFAULT_STOCK_OPTION_UNIVERSE[symbol]["max_quote_age_sec"]) for symbol in symbols))

    return {
        "rule_version": 1,
        "symbols": symbols,
        "max_symbols_per_cycle": max(1, _env_int("STOCK_OPTION_V2_MAX_SYMBOLS_PER_CYCLE", 3)),
        "max_expiries_per_symbol": max(1, _env_int("STOCK_OPTION_V2_MAX_EXPIRIES_PER_SYMBOL", 1)),
        "strikes_around_atm": max(0, _env_int("STOCK_OPTION_V2_STRIKES_AROUND_ATM", 1)),
        "min_oi": float(min_oi),
        "min_volume": float(min_volume),
        "max_spread_pct": float(max_spread_pct),
        "max_quote_age_sec": float(max_quote_age_sec),
        "require_tradingsymbol": _env_flag("STOCK_OPTION_V2_REQUIRE_TRADINGSYMBOL", True),
        "require_instrument_token": _env_flag("STOCK_OPTION_V2_REQUIRE_INSTRUMENT_TOKEN", True),
        "strategy_families": _env_strategy_families("STOCK_OPTION_V2_STRATEGY_FAMILIES", ["breakout", "trend_continuation", "mean_reversion", "volatility_expansion"]),
        "paper_only": True,
    }
