from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from config import config as cfg
from config.stock_option_universe import DEFAULT_STOCK_OPTION_UNIVERSE
from core.stock_option_rules import load_stock_option_rules, stock_option_v2_enabled

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


def _spread_pct(bid: float | None, ask: float | None, ltp: float | None = None) -> float | None:
    if bid is None or ask is None:
        return None
    if bid <= 0 or ask <= 0 or ask < bid:
        return None
    mid = (bid + ask) / 2.0
    if mid <= 0:
        if ltp is None or ltp <= 0:
            return None
        mid = float(ltp)
    return ((ask - bid) / mid) * 100.0


def _select_stock_option_rows(symbol: str, market_data: dict[str, Any], rules: dict[str, Any]) -> list[dict[str, Any]]:
    chain = list(market_data.get("option_chain") or [])
    if not chain:
        return []
    spot = _safe_float(
        market_data.get("underlying_spot")
        or market_data.get("spot")
        or market_data.get("ltp")
        or market_data.get("current_ltp")
    )
    if spot is None or spot <= 0:
        return []

    symbol_cfg = DEFAULT_STOCK_OPTION_UNIVERSE.get(symbol, {})
    min_oi = max(float(rules.get("min_oi", 0.0) or 0.0), float(symbol_cfg.get("min_oi", 0.0) or 0.0))
    min_volume = max(float(rules.get("min_volume", 0.0) or 0.0), float(symbol_cfg.get("min_volume", 0.0) or 0.0))
    max_spread_pct = min(float(rules.get("max_spread_pct", 999.0) or 999.0), float(symbol_cfg.get("max_spread_pct", 999.0) or 999.0))
    max_quote_age_sec = min(float(rules.get("max_quote_age_sec", 999.0) or 999.0), float(symbol_cfg.get("max_quote_age_sec", 999.0) or 999.0))
    strikes_around_atm = max(0, int(rules.get("strikes_around_atm", 1) or 1))
    max_expiries_per_symbol = max(1, int(rules.get("max_expiries_per_symbol", 1) or 1))

    rows: list[dict[str, Any]] = []
    for raw in chain:
        if not isinstance(raw, dict):
            continue
        expiry = raw.get("expiry_date") or raw.get("expiry")
        strike = _safe_float(raw.get("strike"))
        option_type = str(raw.get("option_type") or raw.get("type") or raw.get("right") or "").strip().upper()
        if not expiry or strike is None or option_type not in {"CE", "PE"}:
            continue
        bid = _safe_float(raw.get("best_bid") or raw.get("bid"))
        ask = _safe_float(raw.get("best_ask") or raw.get("ask"))
        ltp = _safe_float(raw.get("ltp") or raw.get("last_price") or raw.get("opt_ltp"))
        oi = _safe_float(raw.get("oi")) or 0.0
        volume = _safe_float(raw.get("volume") or raw.get("current_volume")) or 0.0
        quote_age_sec = _safe_float(raw.get("quote_age_sec") or raw.get("ltp_age_sec") or raw.get("price_age_sec"))
        spread_pct = _spread_pct(bid, ask, ltp)
        if bool(rules.get("require_tradingsymbol", True)) and not raw.get("tradingsymbol"):
            continue
        if bool(rules.get("require_instrument_token", True)) and raw.get("instrument_token") in (None, "", 0):
            continue
        if oi < min_oi or volume < min_volume:
            continue
        if quote_age_sec is None or quote_age_sec > max_quote_age_sec:
            continue
        if spread_pct is None or spread_pct > max_spread_pct:
            continue
        row = dict(raw)
        row.update(
            {
                "symbol": symbol,
                "underlying": symbol,
                "expiry": str(expiry),
                "strike": float(strike),
                "option_type": option_type,
                "spot": float(spot),
                "spread_pct": float(spread_pct),
                "quote_age_sec": float(quote_age_sec),
                "oi": float(oi),
                "volume": float(volume),
                "ltp": ltp,
                "best_bid": bid,
                "best_ask": ask,
                "moneyness_abs": abs(float(strike) - float(spot)),
            }
        )
        rows.append(row)

    if not rows:
        return []
    expiries = sorted({str(row["expiry"]) for row in rows})[:max_expiries_per_symbol]
    allowed_expiries = set(expiries)
    rows = [row for row in rows if str(row["expiry"]) in allowed_expiries]
    rows.sort(key=lambda row: (float(row["moneyness_abs"]), str(row["expiry"]), str(row["option_type"])))
    unique_strikes: list[float] = []
    for row in rows:
        strike = float(row["strike"])
        if strike not in unique_strikes:
            unique_strikes.append(strike)
    allowed_strikes = set(unique_strikes[: (strikes_around_atm * 2) + 1])
    rows = [row for row in rows if float(row["strike"]) in allowed_strikes]
    rows.sort(key=lambda row: (float(row["moneyness_abs"]), str(row["expiry"]), str(row["option_type"])))
    return rows


def _build_stock_option_candidates(symbol: str, rows: list[dict[str, Any]], strategy_families: list[str], ts_epoch: float) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    lot_size = int(DEFAULT_STOCK_OPTION_UNIVERSE.get(symbol, {}).get("lot_size", 1) or 1)
    for row in rows:
        ltp = _safe_float(row.get("ltp")) or _safe_float(row.get("best_ask")) or _safe_float(row.get("best_bid")) or 0.0
        bid = _safe_float(row.get("best_bid")) or 0.0
        ask = _safe_float(row.get("best_ask")) or 0.0
        spot = _safe_float(row.get("spot")) or 0.0
        strike = _safe_float(row.get("strike")) or 0.0
        moneyness_abs = _safe_float(row.get("moneyness_abs")) or 0.0
        signal_conf = max(0.35, min(0.90, 0.75 - (moneyness_abs / max(spot, 1.0))))
        for family in strategy_families:
            candidates.append(
                {
                    "symbol": symbol,
                    "underlying": symbol,
                    "instrument": "OPT",
                    "instrument_type": "OPT_STK",
                    "candidate_type": "stock_option",
                    "strategy_family": family,
                    "timestamp": ts_epoch,
                    "timestamp_utc": datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat(),
                    "source": "candidate_generator_v2_stock_options",
                    "source_module": "candidate_generator",
                    "expiry": str(row.get("expiry")),
                    "expiry_date": str(row.get("expiry")),
                    "strike": strike,
                    "option_type": str(row.get("option_type")),
                    "right": str(row.get("option_type")),
                    "tradingsymbol": row.get("tradingsymbol"),
                    "instrument_token": row.get("instrument_token"),
                    "underlying_spot": spot,
                    "opt_ltp": ltp,
                    "current_ltp": ltp,
                    "best_bid": bid,
                    "best_ask": ask,
                    "opt_bid": bid,
                    "opt_ask": ask,
                    "volume": float(row.get("volume") or 0.0),
                    "current_volume": float(row.get("volume") or 0.0),
                    "oi": float(row.get("oi") or 0.0),
                    "quote_age_sec": float(row.get("quote_age_sec") or 0.0),
                    "ltp_age_sec": float(row.get("quote_age_sec") or 0.0),
                    "spread_pct": float(row.get("spread_pct") or 0.0),
                    "entry_price": ask if ask > 0 else ltp,
                    "display_entry": ask if ask > 0 else ltp,
                    "display_entry_source": "ask" if ask > 0 else "last",
                    "display_entry_status": "displayable",
                    "execution_entry": None,
                    "execution_entry_source": "none",
                    "execution_entry_status": "non_executable",
                    "planning_only": True,
                    "execution_allowed": False,
                    "tradable": False,
                    "qty": lot_size,
                    "qty_lots": 1,
                    "qty_units": lot_size,
                    "rank_score": round(signal_conf, 4),
                    "confidence": round(signal_conf, 4),
                    "builder_confidence": round(signal_conf, 4),
                    "gating_final_confidence": round(signal_conf, 4),
                    "reason": "stock_option_shadow_candidate",
                    "source_flags": {
                        "candidate_origin": "stock_option_v2",
                        "stock_option_shadow": True,
                        "stock_option_paper_only": True,
                        "liquidity_ok": True,
                        "spread_ok": True,
                        "fresh_quote_ok": True,
                    },
                }
            )
    return candidates


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

    if stock_option_v2_enabled():
        stock_rules = load_stock_option_rules()
        stock_symbols = list(stock_rules.get("symbols") or [])[: int(stock_rules.get("max_symbols_per_cycle", 3) or 3)]
        stock_families = list(stock_rules.get("strategy_families") or ["breakout"])
        stock_counts_by_symbol: dict[str, int] = {}
        for symbol in stock_symbols:
            market_data = market_data_by_symbol.get(symbol, {})
            selected_rows = _select_stock_option_rows(symbol, market_data, stock_rules)
            stock_candidates = _build_stock_option_candidates(symbol, selected_rows, stock_families, ts_epoch)
            candidates.extend(stock_candidates)
            stock_counts_by_symbol[symbol] = len(stock_candidates)
            for family in stock_families:
                family_count = sum(1 for candidate in stock_candidates if candidate.get("strategy_family") == family)
                if family_count:
                    counts_by_family[family] = counts_by_family.get(family, 0) + family_count
        logger.info(
            "candidate_generator_v2_stock_options total=%s by_symbol=%s",
            sum(stock_counts_by_symbol.values()),
            stock_counts_by_symbol,
        )

    logger.info(
        "candidate_generator_v2_counts total=%s by_symbol=%s by_strategy_family=%s",
        len(candidates),
        counts_by_symbol,
        counts_by_family,
    )
    return candidates
