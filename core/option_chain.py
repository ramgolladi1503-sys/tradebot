# Migration note:
# Option-chain strictness now follows core.market_context.derive_market_context.

from datetime import datetime, date
import logging
import os
from config import config as cfg
from core.paths import data_root
from core.paths import logs_dir
from core.market_calendar import (
    choose_nearest_available_expiry,
)
from core.instruments import (
    build_option_registry,
    coerce_expiry_date,
    log_requested_expiry_missing,
    select_expiry as select_registry_expiry,
    select_next_expiry as select_registry_next_expiry,
)
from core.market_context import derive_market_context
from config.profile import get_option_filter_profile
from core.kite_client import kite_client
from core.option_liquidity_cache import update_option_liquidity_cache
from core.greeks import implied_vol, greeks
from core.tick_store import get_latest_tick_rows_db_no_flush
from core.depth_store import depth_store
from core.time_utils import compute_age_sec, now_utc_epoch


logger = logging.getLogger(__name__)
_OPTION_CHAIN_ERROR_LAST_TS: dict[str, float] = {}


def _log_option_chain_error(symbol: str, *, stage: str, error: Exception) -> None:
    """
    Always-on, rate-limited error breadcrumb for LIVE chain failures.
    Without this, LIVE failures silently become empty chains and trip non_live_option_chain gates.
    """
    try:
        now = float(now_utc_epoch())
        sym = str(symbol or "").upper() or "UNKNOWN"
        key = f"{sym}:{stage}"
        last = float(_OPTION_CHAIN_ERROR_LAST_TS.get(key) or 0.0)
        if last and (now - last) < 30.0:
            return
        _OPTION_CHAIN_ERROR_LAST_TS[key] = now
        import json as _json
        p = logs_dir() / "option_chain_errors.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts_epoch": now,
            "ts_ist": datetime.fromtimestamp(now).isoformat(),
            "symbol": sym,
            "stage": str(stage),
            "error_type": type(error).__name__,
            "error": str(error),
            "execution_mode": str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper(),
        }
        with p.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        return


def _ws_quotes_for_instruments(*, exchange: str, instruments: list[dict]) -> dict:
    """
    Build a kite.quote-like payload from WS tick/depth stores.
    This avoids blocking LIVE cycles on REST quote latency.
    """
    out: dict = {}
    tokens: list[int] = []
    token_by_key: dict[str, int] = {}
    inst_by_key: dict[str, dict] = {}
    for inst in list(instruments or []):
        tsym = inst.get("tradingsymbol")
        if not tsym:
            continue
        tok = inst.get("instrument_token") or inst.get("instrumentToken") or inst.get("token")
        try:
            tok_int = int(tok) if tok is not None else None
        except Exception:
            tok_int = None
        if not tok_int or tok_int <= 0:
            continue
        key = f"{exchange}:{tsym}"
        tokens.append(tok_int)
        token_by_key[key] = tok_int
        inst_by_key[key] = inst

    rows = get_latest_tick_rows_db_no_flush(tokens) if tokens else {}
    for key, tok_int in token_by_key.items():
        row = rows.get(int(tok_int)) or {}
        ltp = row.get("ltp")
        ts_epoch = row.get("ts_epoch")
        book = depth_store.get(tok_int) or {}
        depth = book.get("depth") or {}
        if ts_epoch is None:
            ts_epoch = book.get("ts_epoch")
        out[key] = {
            "last_price": ltp,
            "depth": depth,
            # keep as epoch seconds; downstream tries float conversion
            "timestamp": ts_epoch,
            "oi": None,
            "volume": None,
        }
    return out


def _env_flag_enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _skip_broker_auth_resolution() -> bool:
    mode = str(
        getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM")) or "SIM"
    ).strip().upper()
    dry_run_enabled = bool(getattr(cfg, "DRY_RUN", False) or _env_flag_enabled("DRY_RUN"))
    return mode in {"SIM", "DRY_RUN"} or dry_run_enabled


def _debug_option_chain_enabled() -> bool:
    return str(os.getenv("TRADEBOT_DEBUG_OPTION_CHAIN", "")).strip().lower() in {"1", "true", "yes", "on"}


def _to_pos_float(value):
    try:
        out = float(value)
    except Exception:
        return None
    if out <= 0:
        return None
    return out


def _to_float_or_none(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _normalize_strike_step(symbol: str, raw_step) -> int | None:
    """
    Strike step is used for ATM rounding and strike ladder construction.
    Production requirement: must never throw, and must be strictly positive.
    """
    try:
        sym = str(symbol or "").strip().upper()
    except Exception:
        sym = ""

    # Prefer per-symbol step first, but tolerate bad/None values.
    try:
        step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {}) or {}
    except Exception:
        step_map = {}

    step_val = None
    if sym and isinstance(step_map, dict):
        step_val = step_map.get(sym)

    if step_val is None:
        step_val = raw_step
    if step_val is None:
        step_val = getattr(cfg, "STRIKE_STEP", 50)

    try:
        step_f = float(step_val)
    except Exception:
        return None
    if not (step_f > 0.0):
        return None

    # Keep as int for strike arithmetic (range, multiplication).
    try:
        step_i = int(round(step_f))
    except Exception:
        return None
    if step_i <= 0:
        return None
    return step_i


def _top_depth_price(depth: dict, side: str):
    if not isinstance(depth, dict):
        return None
    book = depth.get(side)
    if isinstance(book, list) and book:
        top = book[0]
        if isinstance(top, dict):
            return _to_pos_float(top.get("price"))
    return None


def _derive_option_price_fields(last_price, best_bid, best_ask, quote_age_sec, max_quote_age_sec):
    last_val = _to_pos_float(last_price)
    bid_val = _to_pos_float(best_bid)
    ask_val = _to_pos_float(best_ask)
    mid_val = None
    if bid_val is not None and ask_val is not None:
        mid_val = (bid_val + ask_val) / 2.0
    stale_quote = quote_age_sec is None or float(quote_age_sec) > float(max_quote_age_sec)
    outside_tol = float(getattr(cfg, "OPTION_LAST_OUTSIDE_BAND_PCT", 0.01))
    outside_band = False
    if (
        last_val is not None
        and bid_val is not None
        and ask_val is not None
    ):
        lo = min(bid_val, ask_val) * max(0.0, 1.0 - outside_tol)
        hi = max(bid_val, ask_val) * (1.0 + outside_tol)
        outside_band = bool(last_val < lo or last_val > hi)

    if mid_val is not None and (outside_band or stale_quote or last_val is None):
        mark_price = mid_val
        price_source = "mid"
    elif last_val is not None:
        mark_price = last_val
        price_source = "last"
    elif ask_val is not None:
        mark_price = ask_val
        price_source = "ask"
    elif bid_val is not None:
        mark_price = bid_val
        price_source = "bid"
    elif mid_val is not None:
        mark_price = mid_val
        price_source = "mid"
    else:
        mark_price = 0.0
        price_source = "none"

    entry_buy = ask_val if ask_val is not None else mark_price
    entry_sell = bid_val if bid_val is not None else mark_price
    spread_pct = None
    if (
        bid_val is not None
        and ask_val is not None
        and mark_price is not None
        and mark_price > 0
    ):
        spread_pct = (ask_val - bid_val) / mark_price
    return {
        "last_price": last_val,
        "best_bid": bid_val,
        "best_ask": ask_val,
        "mid_price": mid_val,
        "mark_price": mark_price,
        "price_source": price_source,
        "entry_price_proxy_buy": entry_buy,
        "entry_price_proxy_sell": entry_sell,
        "spread_pct": spread_pct,
    }


def _infer_atm_strike(ltp, step):
    ltp_val = _to_pos_float(ltp)
    step_val = _to_float_or_none(step)
    if ltp_val is None or step_val is None or not (step_val > 0.0):
        return None
    return int(round(float(ltp_val) / float(step_val)) * float(step_val))

_PREV_OI = {}
_PREV_LTP = {}


def _coerce_expiry_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.fromisoformat(text).date()
    except Exception:
        return None


def _choose_expiry(available_expiries, preferred_expiry):
    chosen = choose_nearest_available_expiry(available_expiries, today=date.today())
    if chosen is not None:
        return chosen
    return _coerce_expiry_date(preferred_expiry)


def _choose_expiry_by_mode(available_expiries, *, symbol: str, preferred_expiry=None):
    available = [coerce_expiry_date(value) for value in list(available_expiries or [])]
    available = sorted({exp for exp in available if exp is not None})
    preferred = coerce_expiry_date(preferred_expiry)
    if preferred is not None and preferred in available:
        return preferred
    if preferred is not None and preferred not in available:
        log_requested_expiry_missing(
            symbol=symbol,
            requested_expiry=preferred,
            available_expiries=available,
            context="option_chain",
        )
    mode = str(getattr(cfg, "OPTION_EXPIRY_SELECTION", "NEAREST") or "NEAREST").upper()
    if mode == "MONTHLY":
        return select_registry_expiry(available, selection_mode="MONTHLY", today=date.today())
    return _choose_expiry(available, preferred)

def _write_chain_snapshot(chain, symbol=None):
    try:
        import json
        from pathlib import Path
        path = data_root() / "option_chain_latest.json"
        path.parent.mkdir(exist_ok=True)
        if symbol:
            payload = {}
            if path.exists():
                try:
                    payload = json.loads(path.read_text())
                except Exception:
                    payload = {}
            if not isinstance(payload, dict):
                payload = {}
            payload[str(symbol)] = chain
            path.write_text(json.dumps(payload, default=str))
        else:
            path.write_text(json.dumps(chain, default=str))
    except Exception:
        pass

def _annotate_iv_oi(chain):
    ivs = [c.get("iv") for c in chain if c.get("iv") is not None]
    if ivs:
        mean = sum(ivs) / len(ivs)
        var = sum((x - mean) ** 2 for x in ivs) / max(1, len(ivs))
        std = var ** 0.5 if var > 0 else 1.0
    else:
        mean, std = 0, 1

    # IV skew: compare ATM call vs put IV
    atm_iv_call = None
    atm_iv_put = None
    for c in chain:
        if c.get("iv") is None:
            continue
        if c.get("moneyness", 0) == 0:
            if c.get("type") == "CE":
                atm_iv_call = c["iv"]
            if c.get("type") == "PE":
                atm_iv_put = c["iv"]
    iv_skew = None
    if atm_iv_call is not None and atm_iv_put is not None:
        iv_skew = atm_iv_call - atm_iv_put

    # IV surface slope: simple slope of IV vs moneyness
    iv_pairs = [(c.get("moneyness", 0), c.get("iv")) for c in chain if c.get("iv") is not None]
    iv_surface_slope = None
    if len(iv_pairs) >= 3:
        xs = [p[0] for p in iv_pairs]
        ys = [p[1] for p in iv_pairs]
        denom = sum(x * x for x in xs) or 1.0
        iv_surface_slope = sum(x * y for x, y in zip(xs, ys)) / denom

    # Skew curve fit (quadratic)
    try:
        import numpy as np
        if len(iv_pairs) >= 5:
            xs = np.array([p[0] for p in iv_pairs])
            ys = np.array([p[1] for p in iv_pairs])
            coeffs = np.polyfit(xs, ys, 2)
            skew_curvature = float(coeffs[0])
        else:
            skew_curvature = None
    except Exception:
        skew_curvature = None

    # ATM-specific skew curves for calls and puts
    skew_curv_call = None
    skew_curv_put = None
    try:
        import numpy as np
        call_pairs = [(c.get("moneyness", 0), c.get("iv")) for c in chain if c.get("iv") is not None and c.get("type") == "CE"]
        put_pairs = [(c.get("moneyness", 0), c.get("iv")) for c in chain if c.get("iv") is not None and c.get("type") == "PE"]
        if len(call_pairs) >= 5:
            xs = np.array([p[0] for p in call_pairs])
            ys = np.array([p[1] for p in call_pairs])
            skew_curv_call = float(np.polyfit(xs, ys, 2)[0])
        if len(put_pairs) >= 5:
            xs = np.array([p[0] for p in put_pairs])
            ys = np.array([p[1] for p in put_pairs])
            skew_curv_put = float(np.polyfit(xs, ys, 2)[0])
    except Exception:
        pass

    for c in chain:
        iv = c.get("iv")
        if iv is not None:
            c["iv_z"] = (iv - mean) / std if std else 0
        if iv_skew is not None:
            c["iv_skew"] = iv_skew
            # Normalize by expiry (sqrt time)
            dte = c.get("days_to_expiry", 1)
            norm = (dte / 365.0) ** 0.5 if dte else 1.0
            c["iv_skew_norm"] = iv_skew / norm if norm else iv_skew
        if iv_surface_slope is not None:
            c["iv_surface_slope"] = iv_surface_slope
        if skew_curvature is not None:
            c["iv_skew_curvature"] = skew_curvature
        if skew_curv_call is not None:
            c["iv_skew_curvature_call"] = skew_curv_call
        if skew_curv_put is not None:
            c["iv_skew_curvature_put"] = skew_curv_put

        token = c.get("instrument_token")
        if token is not None:
            oi_val = _to_float_or_none(c.get("oi"))
            prev = _PREV_OI.get(token)
            if oi_val is not None:
                c["oi_change"] = (oi_val - prev) if prev is not None else 0
                _PREV_OI[token] = oi_val
            elif "oi_change" not in c:
                c["oi_change"] = None
            prev_ltp = _PREV_LTP.get(token)
            c["ltp_change"] = (c.get("ltp", 0) - prev_ltp) if prev_ltp is not None else 0
            _PREV_LTP[token] = c.get("ltp", 0)

            # OI buildup logic
            oi_ch = c.get("oi_change", 0)
            px_ch = c.get("ltp_change", 0)
            if oi_ch > 0 and px_ch > 0:
                c["oi_build"] = "LONG"
            elif oi_ch > 0 and px_ch < 0:
                c["oi_build"] = "SHORT"
            elif oi_ch < 0 and px_ch > 0:
                c["oi_build"] = "SHORT_COVER"
            elif oi_ch < 0 and px_ch < 0:
                c["oi_build"] = "LONG_LIQ"
            else:
                c["oi_build"] = "FLAT"
    return chain

def fetch_option_chain(symbol, ltp, strikes_around=None, force_synthetic: bool = False, market_context: dict | None = None):
    """
    Build a lightweight option chain around ATM (fallback-friendly).
    This is a placeholder until live option chain is wired from broker API.
    """
    try:
        exec_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
        ctx = derive_market_context(
            market_context
            or {
                "execution_mode": exec_mode,
                "segment": getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO"),
            }
        )
        offhours_mode = ctx.mode == "OFFHOURS"
        strict_live_market_open = bool(ctx.mode == "LIVE")
        synthetic_chain_source = "synthetic_offhours" if (ctx.mode != "LIVE") else "synthetic"
        filter_profile = get_option_filter_profile(mode=ctx.mode, base_max_spread_pct=getattr(cfg, "MAX_SPREAD_PCT", 0.03))

        # Keep strict behavior only during live market hours.
        if strict_live_market_open and force_synthetic:
            return []
        step = _normalize_strike_step(symbol, getattr(cfg, "STRIKE_STEP", 50))
        if strikes_around is None:
            per_sym = getattr(cfg, "STRIKES_AROUND_BY_SYMBOL", {})
            strikes_around = per_sym.get(symbol, getattr(cfg, "STRIKES_AROUND", 6))
        atm = _infer_atm_strike(ltp, step)
        if atm is None:
            return []

        expiry_type = str(getattr(cfg, "TERM_STRUCTURE_EXPIRY", "WEEKLY") or "WEEKLY").upper()
        def _exp_str(x):
            try:
                return str(_coerce_expiry_date(x) or x)
            except Exception:
                return ""
        # Exchange-provided expiries are source of truth.
        exchange = "BFO" if symbol.upper() == "SENSEX" else "NFO"
        next_exp = None
        min_prem = getattr(cfg, "MIN_PREMIUM", 40)
        max_prem = getattr(cfg, "MAX_PREMIUM", 150)

        # Try live Kite option chain (unless forced synthetic)
        if not force_synthetic:
            try:
                kite_client.ensure()
            except Exception as exc:
                # Best-effort: we may still be able to build from cached instruments without a live client.
                _log_option_chain_error(symbol, stage="kite_client_ensure", error=exc)
        if (not force_synthetic) and cfg.KITE_USE_API and kite_client.kite:
            instruments = kite_client.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
            if not instruments:
                raise ValueError("No instruments loaded")
            registry_payload = build_option_registry(
                symbol=symbol,
                instruments=instruments,
                exchange=exchange,
            )
            seg_name = registry_payload.get("segment") or ("BFO-OPT" if exchange == "BFO" else "NFO-OPT")
            symbol_instruments = list(registry_payload.get("instruments") or [])
            if symbol.upper() == "SENSEX" and not symbol_instruments:
                logger.warning(
                    "option_chain_unsupported symbol=%s exchange=%s segment=%s instruments=0",
                    symbol,
                    exchange,
                    seg_name,
                )
                return []
            available_expiries = list(registry_payload.get("available_expiries") or [])
            expiry_date = _choose_expiry_by_mode(
                available_expiries,
                symbol=symbol,
            )
            if symbol.upper() in {"NIFTY", "BANKNIFTY", "SENSEX"} and _debug_option_chain_enabled():
                logger.debug(
                    "option_chain_selection symbol=%s exchange=%s total_opt_instruments=%d available_expiries=%s chosen_expiry=%s",
                    symbol,
                    exchange,
                    len(symbol_instruments),
                    [exp.isoformat() for exp in available_expiries],
                    str(expiry_date) if expiry_date else None,
                )
            if expiry_date is None:
                raise ValueError(f"No expiry available for {symbol}")
            next_mode = "MONTHLY" if expiry_type == "MONTHLY" else "NEAREST"
            next_exp = select_registry_next_expiry(
                available_expiries,
                expiry_date,
                selection_mode=next_mode,
            )
            expiry_date_str = _exp_str(expiry_date)
            opt_rows = []
            for inst in symbol_instruments:
                if _exp_str(inst.get("expiry")) != expiry_date_str:
                    continue
                strike = inst.get("strike")
                if strike is None:
                    continue
                if abs(strike - atm) > strikes_around * step:
                    continue
                opt_rows.append(inst)

            # Fallback: if strict ATM window is empty, choose nearest strikes by distance to ATM.
            if not opt_rows:
                expiry_rows = [
                    inst for inst in symbol_instruments
                    if _exp_str(inst.get("expiry")) == expiry_date_str and inst.get("strike") is not None
                ]
                if expiry_rows:
                    unique_strikes = sorted({float(inst.get("strike")) for inst in expiry_rows})
                    nearest = sorted(unique_strikes, key=lambda strike: abs(strike - atm))[: (2 * strikes_around + 1)]
                    nearest_set = set(nearest)
                    opt_rows = [inst for inst in expiry_rows if float(inst.get("strike")) in nearest_set]

            tradingsymbols = [f"{exchange}:{c['tradingsymbol']}" for c in opt_rows]
            # For term structure, collect next expiry too
            next_candidates = []
            if cfg.ENABLE_TERM_STRUCTURE and next_exp:
                for inst in symbol_instruments:
                    if _exp_str(inst.get("expiry")) != _exp_str(next_exp):
                        continue
                    strike = inst.get("strike")
                    if strike is None:
                        continue
                    if abs(strike - atm) > strikes_around * step:
                        continue
                    next_candidates.append(inst)
                tradingsymbols += [f"{exchange}:{c['tradingsymbol']}" for c in next_candidates]

            exec_mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM")) or "SIM").strip().upper()
            use_ws_quotes = exec_mode == "LIVE" and bool(getattr(cfg, "OPTION_CHAIN_LIVE_USE_WS_QUOTES", True))
            if use_ws_quotes:
                quotes = _ws_quotes_for_instruments(exchange=exchange, instruments=list(opt_rows) + list(next_candidates))
                if (not quotes) and _debug_option_chain_enabled():
                    logger.debug(
                        "option_chain_ws_quotes_empty symbol=%s exchange=%s opt_rows=%d next_rows=%d sample_inst_keys=%s",
                        symbol,
                        exchange,
                        len(opt_rows),
                        len(next_candidates),
                        sorted(list((opt_rows[0] or {}).keys())) if opt_rows else [],
                    )
            else:
                quotes = kite_client.quote(tradingsymbols) if tradingsymbols else {}
            if not opt_rows or not quotes:
                raise ValueError("No option quotes available")
            chain = []
            for inst in opt_rows:
                ts = f"{exchange}:{inst['tradingsymbol']}"
                q = quotes.get(ts, {})
                ltp_opt_raw = q.get("last_price", 0) or 0
                quote_source = "live"
                quote_live = True
                if not ltp_opt_raw:
                    quote_source = "missing"
                    quote_live = False
                    if getattr(cfg, "REQUIRE_LIVE_OPTION_QUOTES", False):
                        continue
                depth = q.get("depth") or {}
                bid = _top_depth_price(depth, "buy")
                ask = _top_depth_price(depth, "sell")
                depth_ok = bool(bid) and bool(ask)
                if not depth_ok and quote_source == "live":
                    quote_source = "no_depth"
                if getattr(cfg, "REQUIRE_DEPTH_QUOTES_FOR_TRADE", False) and not depth_ok:
                    if getattr(cfg, "REQUIRE_LIVE_OPTION_QUOTES", False):
                        continue
                quote_ts = q.get("timestamp") or q.get("last_trade_time")
                if hasattr(quote_ts, "isoformat"):
                    quote_ts = quote_ts.isoformat()
                quote_ts_epoch = None
                try:
                    if hasattr(quote_ts, "timestamp"):
                        quote_ts_epoch = float(quote_ts.timestamp())
                    elif isinstance(quote_ts, (int, float)):
                        quote_ts_epoch = float(quote_ts)
                    elif quote_ts:
                        try:
                            quote_ts_epoch = float(quote_ts)
                        except Exception:
                            quote_ts_epoch = datetime.fromisoformat(str(quote_ts)).timestamp()
                except Exception:
                    quote_ts_epoch = None
                quote_age_sec = None
                if quote_ts_epoch is not None:
                    quote_age_sec = compute_age_sec(quote_ts_epoch, now_utc_epoch())
                else:
                    quote_age_sec = 10**9
                price_fields = _derive_option_price_fields(
                    ltp_opt_raw,
                    bid,
                    ask,
                    quote_age_sec,
                    getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8),
                )
                ltp_opt = float(price_fields.get("mark_price") or 0.0)
                # quote_ok requires bid/ask and freshness under strict live mode
                quote_ok = bool(ltp_opt > 0 and bid and ask)
                if getattr(cfg, "STRICT_LIVE_QUOTES", True) and quote_age_sec is not None:
                    if quote_age_sec > getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8):
                        quote_ok = False
                spread_pct = price_fields.get("spread_pct")
                quote_tradable = bool(
                    price_fields.get("best_bid") is not None
                    and price_fields.get("best_ask") is not None
                    and quote_age_sec is not None
                    and float(quote_age_sec) <= float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8))
                    and (spread_pct is not None and float(spread_pct) <= float(filter_profile.max_spread_pct))
                )
                volume = _to_float_or_none(q.get("volume"))
                oi = _to_float_or_none(q.get("oi"))
                dte = max((expiry_date - date.today()).days, 1)
                t = dte / 365.0
                is_call = inst.get("instrument_type") == "CE"
                vol = None
                g = {}
                if ltp_opt and ltp_opt > 0:
                    vol = implied_vol(ltp_opt, ltp, inst["strike"], t, is_call=is_call)
                    g = greeks(ltp, inst["strike"], t, vol, is_call=is_call)
                moneyness = 0
                if ltp and inst["strike"]:
                    moneyness = (ltp - inst["strike"]) / ltp
                chain.append({
                    "symbol": symbol,
                    "tradingsymbol": inst.get("tradingsymbol"),
                    "strike": inst["strike"],
                    "type": inst.get("instrument_type"),
                    "ltp": ltp_opt,
                    "last_price": price_fields.get("last_price"),
                    "best_bid": price_fields.get("best_bid"),
                    "best_ask": price_fields.get("best_ask"),
                    "mid_price": price_fields.get("mid_price"),
                    "mark_price": price_fields.get("mark_price"),
                    "entry_price_proxy_buy": price_fields.get("entry_price_proxy_buy"),
                    "entry_price_proxy_sell": price_fields.get("entry_price_proxy_sell"),
                    "price_source": price_fields.get("price_source"),
                    "bid": price_fields.get("best_bid"),
                    "ask": price_fields.get("best_ask"),
                    "bid_qty": depth.get("buy", [{}])[0].get("quantity") if depth else None,
                    "ask_qty": depth.get("sell", [{}])[0].get("quantity") if depth else None,
                    "volume": volume,
                    "oi": oi,
                    "quote_ok": quote_ok,
                    "quote_source": quote_source,
                    "option_ltp_source": quote_source,
                    "quote_live": quote_live,
                    "quote_ts": quote_ts,
                    "quote_ts_epoch": quote_ts_epoch,
                    "quote_age_sec": quote_age_sec,
                    "spread_pct": spread_pct,
                    "quote_tradable": quote_tradable,
                    "filter_profile": str(filter_profile.name),
                    "depth_ok": depth_ok,
                    "instrument_token": inst.get("instrument_token"),
                    "iv": vol,
                    "moneyness": moneyness,
                    "days_to_expiry": dte,
                    **g,
                    "expiry": str(expiry_date),
                    "expiry_date": str(expiry_date),
                    "timestamp": datetime.now().timestamp(),
                    "planning_only": False,
                })
            # term structure iv: compare with next expiry for same strike/type
            if cfg.ENABLE_TERM_STRUCTURE and next_candidates:
                next_iv_map = {}
                for inst in next_candidates:
                    ts = f"{exchange}:{inst['tradingsymbol']}"
                    q = quotes.get(ts, {})
                    ltp_opt = q.get("last_price", 0)
                    if ltp_opt <= 0:
                        continue
                    is_call = inst.get("instrument_type") == "CE"
                    dte = max((next_exp - date.today()).days, 1)
                    t = dte / 365.0
                    iv = implied_vol(ltp_opt, ltp, inst["strike"], t, is_call=is_call)
                    next_iv_map[(inst["strike"], inst.get("instrument_type"))] = iv
                for c in chain:
                    key = (c["strike"], c["type"])
                    if key in next_iv_map:
                        c["iv_term"] = c.get("iv") - next_iv_map[key]
            for c in chain:
                c["chain_source"] = "live"
            chain = _annotate_iv_oi(chain)
            update_option_liquidity_cache(
                chain,
                symbol=symbol,
                snapshot_ts_epoch=now_utc_epoch(),
                source="option_chain_live",
            )
            _write_chain_snapshot(chain, symbol=symbol)
            return chain
        if not getattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False):
            return []
        chain = []
        synthetic_quote_epoch = now_utc_epoch()
        synthetic_expiry_date = date.today()
        if not _skip_broker_auth_resolution():
            synthetic_expiry_date = (
                coerce_expiry_date(kite_client.next_available_expiry(symbol, exchange=exchange))
                or synthetic_expiry_date
            )
        synthetic_expiry = str(synthetic_expiry_date)
        strikes = [atm + i * step for i in range(-strikes_around, strikes_around + 1)]
        for strike in strikes:
            for opt_type in ("CE", "PE"):
                # Simple premium proxy
                base = max(min_prem, min(max_prem, (ltp * 0.004)))
                ltp_opt = max(min_prem, min(max_prem, base * (1 + (abs(strike - atm) / (10 * step)))))
                bid = round(ltp_opt * 0.995, 2)
                ask = round(ltp_opt * 1.005, 2)
                price_fields = _derive_option_price_fields(
                    ltp_opt,
                    bid,
                    ask,
                    quote_age_sec=0.0,
                    max_quote_age_sec=getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8),
                )
                chain.append({
                        "symbol": symbol,
                        "tradingsymbol": None,
                        "strike": strike,
                        "type": opt_type,
                        "ltp": round(float(price_fields.get("mark_price") or ltp_opt), 2),
                        "last_price": round(float(price_fields.get("last_price") or ltp_opt), 2),
                        "best_bid": price_fields.get("best_bid"),
                        "best_ask": price_fields.get("best_ask"),
                        "mid_price": price_fields.get("mid_price"),
                        "mark_price": price_fields.get("mark_price"),
                        "entry_price_proxy_buy": price_fields.get("entry_price_proxy_buy"),
                        "entry_price_proxy_sell": price_fields.get("entry_price_proxy_sell"),
                        "price_source": price_fields.get("price_source"),
                        "bid": price_fields.get("best_bid"),
                        "ask": price_fields.get("best_ask"),
                        "volume": 1000,
                        "oi": 0,
                        "quote_ok": True,
                        "quote_source": synthetic_chain_source,
                        "option_ltp_source": synthetic_chain_source,
                        "quote_live": False,
                        "quote_ts_epoch": synthetic_quote_epoch,
                        "quote_age_sec": 0.0,
                        "quote_tradable": bool(
                            price_fields.get("best_bid") is not None
                            and price_fields.get("best_ask") is not None
                            and (price_fields.get("spread_pct") is not None and float(price_fields.get("spread_pct")) <= float(filter_profile.max_spread_pct))
                        ),
                        "filter_profile": str(filter_profile.name),
                        "chain_source": synthetic_chain_source,
                        "instrument_token": None,
                        "moneyness": 0,
                        "days_to_expiry": 1,
                        "expiry": synthetic_expiry,
                        "expiry_date": synthetic_expiry,
                        "timestamp": datetime.now().timestamp(),
                        "planning_only": True,
                    })
        chain = _annotate_iv_oi(chain)
        _write_chain_snapshot(chain, symbol=symbol)
        return chain
    except Exception as e:
        _log_option_chain_error(symbol, stage="fetch_option_chain", error=e)
        try:
            if getattr(cfg, "REQUIRE_LIVE_QUOTES", True) and not force_synthetic:
                return []
            # fallback to synthetic chain when live chain is unavailable
            if strict_live_market_open:
                return []
            if not getattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False):
                return []
            step = _normalize_strike_step(symbol, getattr(cfg, "STRIKE_STEP", 50))
            atm = _infer_atm_strike(ltp, step)
            if atm is None:
                return []
            min_prem = getattr(cfg, "MIN_PREMIUM", 40)
            max_prem = getattr(cfg, "MAX_PREMIUM", 150)
            strikes = [atm + i * step for i in range(-strikes_around, strikes_around + 1)]
            chain = []
            synthetic_quote_epoch = now_utc_epoch()
            fallback_filter_profile = get_option_filter_profile(
                mode=str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
                base_max_spread_pct=getattr(cfg, "MAX_SPREAD_PCT", 0.03),
            )
            for strike in strikes:
                for opt_type in ("CE", "PE"):
                    base = max(min_prem, min(max_prem, (ltp * 0.004)))
                    ltp_opt = max(min_prem, min(max_prem, base * (1 + (abs(strike - atm) / (10 * step)))))
                    bid = round(ltp_opt * 0.995, 2)
                    ask = round(ltp_opt * 1.005, 2)
                    price_fields = _derive_option_price_fields(
                        ltp_opt,
                        bid,
                        ask,
                        quote_age_sec=0.0,
                        max_quote_age_sec=getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8),
                    )
                    chain.append({
                        "symbol": symbol,
                        "tradingsymbol": None,
                        "strike": strike,
                        "type": opt_type,
                        "ltp": round(float(price_fields.get("mark_price") or ltp_opt), 2),
                        "last_price": round(float(price_fields.get("last_price") or ltp_opt), 2),
                        "best_bid": price_fields.get("best_bid"),
                        "best_ask": price_fields.get("best_ask"),
                        "mid_price": price_fields.get("mid_price"),
                        "mark_price": price_fields.get("mark_price"),
                        "entry_price_proxy_buy": price_fields.get("entry_price_proxy_buy"),
                        "entry_price_proxy_sell": price_fields.get("entry_price_proxy_sell"),
                        "price_source": price_fields.get("price_source"),
                        "bid": price_fields.get("best_bid"),
                        "ask": price_fields.get("best_ask"),
                        "volume": 1000,
                        "oi": 0,
                        "quote_ok": True,
                        "quote_source": synthetic_chain_source,
                        "option_ltp_source": synthetic_chain_source,
                        "quote_live": False,
                        "quote_ts_epoch": synthetic_quote_epoch,
                        "quote_age_sec": 0.0,
                        "quote_tradable": bool(
                            price_fields.get("best_bid") is not None
                            and price_fields.get("best_ask") is not None
                            and (price_fields.get("spread_pct") is not None and float(price_fields.get("spread_pct")) <= float(fallback_filter_profile.max_spread_pct))
                        ),
                        "filter_profile": str(fallback_filter_profile.name),
                        "chain_source": synthetic_chain_source,
                        "instrument_token": None,
                        "moneyness": 0,
                        "days_to_expiry": 1,
                        "expiry": str(datetime.now().date()),
                        "expiry_date": str(datetime.now().date()),
                        "timestamp": datetime.now().timestamp(),
                        "planning_only": True,
                    })
            chain = _annotate_iv_oi(chain)
            _write_chain_snapshot(chain, symbol=symbol)
            return chain
        except Exception as inner_exc:
            logger.warning("option_chain_error err=%s fallback_error=%s", e, inner_exc)
            return []
