from datetime import datetime, date
from config import config as cfg
from core.market_calendar import (
    choose_nearest_available_expiry,
    next_expiry_by_type,
    next_expiry_after,
)
from core.kite_client import kite_client
from core.greeks import implied_vol, greeks

def _infer_atm_strike(ltp, step):
    if not ltp or step <= 0:
        return None
    return int(round(ltp / step) * step)

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

def _write_chain_snapshot(chain, symbol=None):
    try:
        import json
        from pathlib import Path
        path = Path("data/option_chain_latest.json")
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
            prev = _PREV_OI.get(token)
            c["oi_change"] = (c.get("oi", 0) - prev) if prev is not None else 0
            _PREV_OI[token] = c.get("oi", 0)
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

def fetch_option_chain(symbol, ltp, strikes_around=None, force_synthetic: bool = False):
    """
    Build a lightweight option chain around ATM (fallback-friendly).
    This is a placeholder until live option chain is wired from broker API.
    """
    try:
        # No synthetic chains in LIVE mode
        if str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "LIVE" and force_synthetic:
            return []
        step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {})
        step = step_map.get(symbol, getattr(cfg, "STRIKE_STEP", 50))
        if strikes_around is None:
            per_sym = getattr(cfg, "STRIKES_AROUND_BY_SYMBOL", {})
            strikes_around = per_sym.get(symbol, getattr(cfg, "STRIKES_AROUND", 6))
        atm = _infer_atm_strike(ltp, step)
        if atm is None:
            return []

        expiry_type = getattr(cfg, "TERM_STRUCTURE_EXPIRY", "WEEKLY")
        def _exp_str(x):
            try:
                return str(_coerce_expiry_date(x) or x)
            except Exception:
                return ""
        # Exchange-provided expiries are source of truth.
        exchange = "BFO" if symbol.upper() == "SENSEX" else "NFO"
        fallback_expiry = kite_client.next_available_expiry(symbol, exchange=exchange)
        if not fallback_expiry:
            fallback_expiry = next_expiry_by_type(expiry_type, symbol=symbol)
        next_exp = None
        expiry_for_term = _coerce_expiry_date(fallback_expiry)
        if expiry_for_term:
            next_exp = next_expiry_after(expiry_for_term, expiry_type=expiry_type, symbol=symbol)
        min_prem = getattr(cfg, "MIN_PREMIUM", 40)
        max_prem = getattr(cfg, "MAX_PREMIUM", 150)

        # Try live Kite option chain (unless forced synthetic)
        if not force_synthetic:
            kite_client.ensure()
        if (not force_synthetic) and cfg.KITE_USE_API and kite_client.kite:
            instruments = kite_client.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
            if not instruments:
                raise ValueError("No instruments loaded")
            seg_name = "BFO-OPT" if exchange == "BFO" else "NFO-OPT"
            symbol_instruments = [
                inst
                for inst in instruments
                if inst.get("name") == symbol and inst.get("segment") == seg_name
            ]
            if symbol.upper() == "SENSEX" and not symbol_instruments:
                print(
                    "[OPTION_CHAIN_WARN]"
                    f" symbol={symbol} exchange={exchange} segment={seg_name} instruments=0 -> unsupported, skipping"
                )
                return []
            available_expiries = sorted(
                {
                    str(exp)
                    for exp in (
                        _coerce_expiry_date(inst.get("expiry"))
                        for inst in symbol_instruments
                    )
                    if exp is not None
                }
            )
            expiry_date = _choose_expiry(
                [inst.get("expiry") for inst in symbol_instruments],
                fallback_expiry,
            )
            if symbol.upper() in {"NIFTY", "BANKNIFTY", "SENSEX"}:
                print(
                    "[OPTION_CHAIN_DEBUG]"
                    f" symbol={symbol}"
                    f" exchange={exchange}"
                    f" total_opt_instruments={len(symbol_instruments)}"
                    f" available_expiries={available_expiries}"
                    f" chosen_expiry={str(expiry_date) if expiry_date else None}"
                )
            if expiry_date is None:
                expiry_date = _coerce_expiry_date(fallback_expiry)
            if expiry_date is None:
                raise ValueError(f"No expiry available for {symbol}")
            next_exp = next_expiry_after(expiry_date, expiry_type=expiry_type, symbol=symbol) if expiry_date else None
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
            quotes = kite_client.quote(tradingsymbols) if tradingsymbols else {}
            if not opt_rows or not quotes:
                raise ValueError("No option quotes available")
            chain = []
            for inst in opt_rows:
                ts = f"{exchange}:{inst['tradingsymbol']}"
                q = quotes.get(ts, {})
                ltp_opt = q.get("last_price", 0) or 0
                quote_source = "live"
                quote_live = True
                if not ltp_opt:
                    quote_source = "missing"
                    quote_live = False
                    if getattr(cfg, "REQUIRE_LIVE_OPTION_QUOTES", False):
                        continue
                depth = q.get("depth") or {}
                bid = depth.get("buy", [{}])[0].get("price")
                ask = depth.get("sell", [{}])[0].get("price")
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
                    quote_age_sec = max(0.0, (datetime.utcnow().timestamp() - float(quote_ts_epoch)))
                else:
                    quote_age_sec = 10**9
                # quote_ok requires bid/ask and freshness under strict live mode
                quote_ok = bool(ltp_opt > 0 and bid and ask)
                if getattr(cfg, "STRICT_LIVE_QUOTES", True) and quote_age_sec is not None:
                    if quote_age_sec > getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8):
                        quote_ok = False
                spread_pct = None
                if bid and ask:
                    base = ltp_opt or ((bid + ask) / 2.0)
                    if base:
                        spread_pct = (ask - bid) / base
                volume = q.get("volume", 0)
                oi = q.get("oi", 0)
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
                    "strike": inst["strike"],
                    "type": inst.get("instrument_type"),
                    "ltp": ltp_opt,
                    "bid": bid,
                    "ask": ask,
                    "bid_qty": depth.get("buy", [{}])[0].get("quantity") if depth else None,
                    "ask_qty": depth.get("sell", [{}])[0].get("quantity") if depth else None,
                    "volume": volume,
                    "oi": oi,
                    "quote_ok": quote_ok,
                    "quote_source": quote_source,
                    "quote_live": quote_live,
                    "quote_ts": quote_ts,
                    "quote_ts_epoch": quote_ts_epoch,
                    "quote_age_sec": quote_age_sec,
                    "spread_pct": spread_pct,
                    "depth_ok": depth_ok,
                    "instrument_token": inst.get("instrument_token"),
                    "iv": vol,
                    "moneyness": moneyness,
                    "days_to_expiry": dte,
                    **g,
                    "expiry": str(expiry_date),
                    "timestamp": datetime.now().timestamp()
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
            _write_chain_snapshot(chain, symbol=symbol)
            return chain
        if not getattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False):
            return []
        chain = []
        strikes = [atm + i * step for i in range(-strikes_around, strikes_around + 1)]
        for strike in strikes:
            for opt_type in ("CE", "PE"):
                # Simple premium proxy
                base = max(min_prem, min(max_prem, (ltp * 0.004)))
                ltp_opt = max(min_prem, min(max_prem, base * (1 + (abs(strike - atm) / (10 * step)))))
                bid = round(ltp_opt * 0.995, 2)
                ask = round(ltp_opt * 1.005, 2)
                chain.append({
                        "symbol": symbol,
                        "strike": strike,
                        "type": opt_type,
                        "ltp": round(ltp_opt, 2),
                        "bid": bid,
                        "ask": ask,
                        "volume": 1000,
                        "oi": 0,
                        "quote_ok": True,
                        "quote_source": "synthetic",
                        "quote_live": False,
                        "chain_source": "synthetic",
                        "instrument_token": None,
                        "moneyness": 0,
                        "days_to_expiry": 1,
                        "expiry": str(expiry),
                        "timestamp": datetime.now().timestamp()
                    })
        chain = _annotate_iv_oi(chain)
        _write_chain_snapshot(chain, symbol=symbol)
        return chain
    except Exception as e:
        try:
            if getattr(cfg, "REQUIRE_LIVE_QUOTES", True) and not force_synthetic:
                return []
            # fallback to synthetic chain when live chain is unavailable
            if str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "LIVE":
                return []
            if not getattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False):
                return []
            step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {})
            step = step_map.get(symbol, getattr(cfg, "STRIKE_STEP", 50))
            atm = _infer_atm_strike(ltp, step)
            if atm is None:
                return []
            min_prem = getattr(cfg, "MIN_PREMIUM", 40)
            max_prem = getattr(cfg, "MAX_PREMIUM", 150)
            strikes = [atm + i * step for i in range(-strikes_around, strikes_around + 1)]
            chain = []
            for strike in strikes:
                for opt_type in ("CE", "PE"):
                    base = max(min_prem, min(max_prem, (ltp * 0.004)))
                    ltp_opt = max(min_prem, min(max_prem, base * (1 + (abs(strike - atm) / (10 * step)))))
                    bid = round(ltp_opt * 0.995, 2)
                    ask = round(ltp_opt * 1.005, 2)
                    chain.append({
                        "symbol": symbol,
                        "strike": strike,
                        "type": opt_type,
                        "ltp": round(ltp_opt, 2),
                        "bid": bid,
                        "ask": ask,
                        "volume": 1000,
                        "oi": 0,
                        "quote_ok": True,
                        "quote_source": "synthetic",
                        "quote_live": False,
                        "chain_source": "synthetic",
                        "instrument_token": None,
                        "moneyness": 0,
                        "days_to_expiry": 1,
                        "expiry": str(datetime.now().date()),
                        "timestamp": datetime.now().timestamp()
                    })
            chain = _annotate_iv_oi(chain)
            _write_chain_snapshot(chain, symbol=symbol)
            return chain
        except Exception:
            print(f"Option chain error: {e}")
            return []
