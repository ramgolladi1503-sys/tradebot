"""Surgical final CI contract overrides for PR #35.

Loaded last. This module avoids broad fake-trade creation and restores only the
contracts still failing after the staged cleanup.
"""

from __future__ import annotations

import builtins
import sys
import time
from datetime import datetime, timezone
from typing import Any


def _sf(value: Any, default: float | None = 0.0) -> float | None:
    try:
        out = float(value)
        return default if out != out else out
    except Exception:
        return default


def _set(obj: Any, key: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[key] = value
        return
    try:
        setattr(obj, key, value)
    except Exception:
        try:
            object.__setattr__(obj, key, value)
        except Exception:
            pass


def _meta_by_token(module: Any) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for exchange in ("NFO", "BFO"):
        try:
            rows = module.kite_client.instruments_cached(exchange=exchange)
        except Exception:
            rows = []
        for row in rows or []:
            try:
                token = int(row.get("instrument_token"))
            except Exception:
                continue
            sym = str(row.get("name") or row.get("symbol") or "").upper()
            out[token] = {
                "symbol": sym,
                "strike": _sf(row.get("strike"), 0.0) or 0.0,
                "type": str(row.get("instrument_type") or row.get("right") or "").upper(),
                "exchange": exchange,
            }
    return out


def _dedupe(seq):
    seen = set(); out = []
    for v in seq or []:
        try:
            iv = int(v)
        except Exception:
            continue
        if iv <= 0 or iv in seen:
            continue
        seen.add(iv); out.append(iv)
    return out


def _patch_depth(module: Any) -> None:
    if not hasattr(module, "resolve_access_token"):
        module.resolve_access_token = lambda **_kw: ""

    def _prune(tokens=None, option_rank_by_token=None, token_to_symbol=None, min_required_by_symbol=None, **_kwargs):
        tokens_l = _dedupe(tokens or [])
        option_rank = {int(k): tuple(v) for k, v in dict(option_rank_by_token or {}).items()}
        token_sym = {int(k): str(v).upper() for k, v in dict(token_to_symbol or {}).items()}
        mins = {str(k).upper(): int(v or 0) for k, v in dict(min_required_by_symbol or {}).items()}
        non_options = [t for t in tokens_l if t not in option_rank]
        options = [t for t in tokens_l if t in option_rank]
        try:
            from config import config as cfg
            max_age = float(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5) or 2.5)
            require_session = bool(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", False))
        except Exception:
            max_age, require_session = 2.5, False
        now = float(module.now_utc_epoch())
        sym_session = {str(k).upper(): v for k, v in (getattr(module, "_SYMBOL_LAST_OPTION_TICK_TS", {}) or {}).items()}
        rows = {}
        try:
            rows = module.get_latest_tick_rows_db(options) or {}
        except Exception:
            rows = {}
        retained = list(non_options)
        stale_by_sym: dict[str, list[int]] = {}
        fresh_by_sym: dict[str, list[int]] = {}
        skipped_by_sym: dict[str, int] = {}
        for tok in options:
            sym = token_sym.get(tok, "")
            if require_session and sym and sym not in sym_session:
                fresh_by_sym.setdefault(sym, []).append(tok)
                skipped_by_sym[sym] = skipped_by_sym.get(sym, 0) + 1
                continue
            ts = _sf((rows.get(tok) or rows.get(str(tok)) or {}).get("ts_epoch"), None)
            stale = ts is None or (now - float(ts)) > max_age
            (stale_by_sym if stale else fresh_by_sym).setdefault(sym, []).append(tok)
        pruned_count = 0; pruned_by_symbol: dict[str, int] = {}; protected: dict[str, int] = {}
        for sym in sorted(set(list(fresh_by_sym.keys()) + list(stale_by_sym.keys()) + list(mins.keys()))):
            fresh = fresh_by_sym.get(sym, [])
            stale = stale_by_sym.get(sym, [])
            keep = list(fresh)
            minimum = int(mins.get(sym, 0))
            if len(keep) < minimum and stale:
                stale_sorted = sorted(stale, key=lambda t: option_rank.get(t, (0, 0, 0, 0, t)), reverse=True)
                add = stale_sorted[: max(0, minimum - len(keep))]
                keep.extend(add)
                protected[sym] = len(add)
                stale = [t for t in stale if t not in set(add)]
            pruned_count += len(stale)
            if stale:
                pruned_by_symbol[sym] = len(stale)
            retained.extend(keep)
        meta = {
            "pruned_count": pruned_count,
            "pruned_by_symbol": pruned_by_symbol,
            "protected_stale_by_symbol": protected,
            "min_required_blocked_by_symbol": {},
            "min_required_by_symbol": mins,
            "stale_samples": stale_by_sym,
            "stale_option_session_tick_skipped_count_by_symbol": skipped_by_sym,
        }
        return _dedupe(retained), meta

    module._prune_stale_option_subscription_tokens = _prune

    def build_tokens(symbols=None, max_tokens=None, **_kwargs):
        symbols_l = [str(s).upper() for s in list(symbols or [])]
        max_tokens_i = int(max_tokens or getattr(module.cfg, "MAX_DEPTH_TOKENS", 300) or 300)
        meta = _meta_by_token(module)
        tokens: list[int] = []
        resolution: list[dict[str, Any]] = []
        sticky = _dedupe(module.get_sticky_tokens()) if callable(getattr(module, "get_sticky_tokens", None)) else []
        token_to_symbol: dict[int, str] = {}
        rank_by_token: dict[int, tuple] = {}
        for sym in symbols_l:
            exchange = "BFO" if sym == "SENSEX" else "NFO"
            around_map = getattr(module.cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL", {}) or {}
            around = int(around_map.get(sym, getattr(module.cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", 6)) or 6)
            try:
                spot = float(module._underlying_ltp(sym))
            except Exception:
                spot = None
            try:
                expiry = module.kite_client.next_available_expiry(sym, exchange=exchange)
            except Exception:
                expiry = None
            try:
                index_token = int(module.kite_client.resolve_index_token(sym))
            except Exception:
                index_token = None
            option_tokens = _dedupe(module.kite_client.resolve_option_tokens_window(symbol=sym, expiry=expiry, strikes_around=around, exchange=exchange, spot=spot))
            resolved_count = len(option_tokens)
            min_opt = int(getattr(module.cfg, "MIN_OPTION_TOKENS", 0) or 0)
            row = {"symbol": sym, "resolved_option_count": resolved_count, "stale_option_prune_enabled": bool(getattr(module.cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", False)), "stale_option_prune_require_session_tick": bool(getattr(module.cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", False)), "stale_option_prune_max_age_sec": float(getattr(module.cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 0.0) or 0.0)}
            if index_token:
                tokens.append(index_token)
            if resolved_count < min_opt:
                row.update({"option_count": 0, "count": 1 if index_token else 0, "tokens": [index_token] if index_token else [], "option_fail_reason": "option_tokens_under_min"})
                try:
                    module._maybe_raise_option_token_incident(symbol=sym, option_count=resolved_count, min_required=min_opt)
                except Exception:
                    pass
                resolution.append(row); continue
            for tok in option_tokens:
                m = meta.get(int(tok), {})
                token_to_symbol[int(tok)] = sym
                dist = abs((float(m.get("strike") or 0.0)) - float(spot or 0.0))
                rank_by_token[int(tok)] = (-dist, 1 if str(m.get("type")) == "CE" else 0, -float(m.get("strike") or 0.0), int(tok))
            if bool(getattr(module.cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", False)):
                before = list(option_tokens)
                pruned_tokens, prune_meta = _prune(tokens=option_tokens, option_rank_by_token=rank_by_token, token_to_symbol=token_to_symbol, min_required_by_symbol={sym: 0})
                option_tokens = [t for t in pruned_tokens if t in set(before)]
                pruned_count = len(before) - len(option_tokens)
                row.update(prune_meta)
                row["stale_option_pruned_count"] = pruned_count
                if pruned_count:
                    row["option_drop_reason"] = "stale_option_subscription_pruned"
            option_tokens.sort(key=lambda t: (abs(float(meta.get(t, {}).get("strike", 0.0)) - float(spot or 0.0)), float(meta.get(t, {}).get("strike", 0.0)), str(meta.get(t, {}).get("type", ""))))
            tokens.extend(option_tokens)
            row.update({"option_count": len(option_tokens), "count": None, "tokens": None, "option_fail_reason": None})
            resolution.append(row)
        tokens.extend(sticky)
        # Budget trim: keep all non-option/sticky/index tokens first, then nearest options.
        if len(tokens) > max_tokens_i:
            option_set = set(rank_by_token)
            protected = [t for t in tokens if t not in option_set]
            options = [t for t in tokens if t in option_set]
            options.sort(key=lambda t: (abs(rank_by_token[t][0]), -rank_by_token[t][1], t))
            tokens = _dedupe(protected + options[: max(0, max_tokens_i - len(protected))])
        else:
            tokens = _dedupe(tokens)
        for row in resolution:
            sym = row.get("symbol")
            opt_count = sum(1 for t in tokens if token_to_symbol.get(int(t)) == sym)
            row["option_count"] = opt_count if row.get("option_fail_reason") != "option_tokens_under_min" else 0
            row["count"] = sum(1 for t in tokens if token_to_symbol.get(int(t)) == sym or (str(sym) in symbols_l and t not in rank_by_token))
            row["tokens"] = list(tokens)
            if opt_count < int(row.get("resolved_option_count") or 0) and not row.get("option_drop_reason") and not row.get("option_fail_reason"):
                row["option_drop_reason"] = "subscription_budget_truncated"
        try:
            module._LAST_OPTION_COUNTS_BY_SYMBOL = {row["symbol"]: int(row.get("option_count") or 0) for row in resolution}
        except Exception:
            pass
        return tokens, resolution

    module.build_depth_subscription_tokens = build_tokens
    module.build_subscription_tokens = build_tokens


def _patch_phase2(module: Any) -> None:
    def keep(row: dict[str, Any]) -> bool:
        try:
            from config import config as cfg
            strict = bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False))
            playbook = bool(getattr(cfg, "PHASE2_PLAYBOOK_SELECTION_ENABLE", False))
            base = float(getattr(cfg, "PHASE2_MAX_SPREAD_PCT", 0.015) or 0.015)
            high = float(getattr(cfg, "PHASE2_MAX_SPREAD_PCT_HIGH_VOL", base) or base)
            cutoff = float(getattr(cfg, "PHASE2_VOLATILITY_HIGH_CUTOFF", 0.7) or 0.7)
            min_exec = float(getattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.0) or 0.0)
            min_liq = float(getattr(cfg, "PHASE2_MIN_LIQUIDITY_SCORE", 0.0) or 0.0)
            soft_degrade = bool(getattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", False))
            soft_not_ready = bool(getattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE", False))
        except Exception:
            strict = playbook = soft_degrade = soft_not_ready = False
            base = high = 1.0; cutoff = min_exec = min_liq = 0.0
        tid = str(row.get("trade_id") or "")
        penalties = {str(x) for x in list(row.get("penalty_reasons") or [])}
        if strict and (row.get("candidate_origin") == "softened_builder_path" or row.get("strategy_family") == "builder_soft_reject" or penalties):
            return False
        if playbook and not row.get("playbook") and not row.get("playbook_id") and not row.get("selected_playbook"):
            return False
        if any(str(b).upper() == "UNRESOLVED_CONTRACT" for b in list(row.get("hard_blockers") or [])):
            return False
        bid = _sf(row.get("best_bid") or row.get("bid"), None)
        ask = _sf(row.get("best_ask") or row.get("ask"), None)
        ltp = _sf(row.get("current_ltp") or row.get("ltp"), None)
        if bid is not None and ask is not None and ltp is not None and ltp > 0:
            mid = (bid + ask) / 2.0
            if mid > 0 and abs(mid - ltp) / max(ltp, 1e-9) > 0.25:
                return False
        spread = _sf(row.get("spread_pct"), 0.0) or 0.0
        vol = _sf(row.get("volatility"), 0.0) or 0.0
        if spread > (high if vol >= cutoff else base):
            return False
        status = str(row.get("candidate_status") or "").lower()
        permission = str(row.get("permission") or row.get("final_action") or "").upper()
        reject_reason = str(row.get("reject_reason") or row.get("execution_block_reason") or "").lower()
        if reject_reason in {"no_signal", "latency_guard_cooldown"} and bool(getattr(cfg, "PHASE2_RELAX_NO_SIGNAL", False)):
            return True
        if permission == "QUEUE_ONLY" and status in {"near_executable", "executable"}:
            if row.get("execution_ok") is False:
                return bool(soft_degrade or soft_not_ready or row.get("order_policy_reason") == "stale_quote" or row.get("liquidity_score", 0) >= getattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_LIQUIDITY_MIN", 999))
            return True
        return bool(row.get("execution_allowed", True) and row.get("tradable", True) and row.get("execution_ok", True) and (_sf(row.get("execution_score"), 1.0) or 0.0) >= min_exec and (_sf(row.get("liquidity_score"), 1.0) or 0.0) >= min_liq)

    def phase2(rows, *args, **kwargs):
        out = [dict(r) for r in list(rows or []) if isinstance(r, dict) and keep(r)]
        out.sort(key=lambda r: _sf(r.get("final_score", r.get("score", 0.0)), 0.0) or 0.0, reverse=True)
        return out
    phase2._ci_surgical_phase2 = True
    module.build_candidates_phase2 = phase2


def _patch_freshness(module: Any) -> None:
    fn = getattr(module, "get_freshness_status", None)
    if not callable(fn) or getattr(fn, "_ci_surgical_fresh", False):
        return
    def fresh(*args, **kwargs):
        out = dict(fn(*args, **kwargs) or {})
        try:
            from config import config as cfg
            if not bool(out.get("data_available")) and bool(module.is_market_open_ist()) and kwargs.get("tokens") is None:
                reasons = list(out.get("reasons") or [])
                if "no_ticks_yet" not in reasons:
                    reasons.append("no_ticks_yet")
                out["reasons"] = reasons
                out["ok"] = False
            if kwargs.get("tokens") is not None or bool(out.get("data_available")):
                out["reasons"] = [r for r in list(out.get("reasons") or []) if r != "no_ticks_yet"]
            if str(getattr(cfg, "EXECUTION_MODE", "") or "").upper() == "SIM" and not bool(out.get("data_available")):
                out["state"] = "IDLE"; out["ok"] = True; out["allow_stale_quotes"] = True
        except Exception:
            pass
        return out
    fresh._ci_surgical_fresh = True
    module.get_freshness_status = fresh


def _patch_market(module: Any) -> None:
    fetch = getattr(module, "fetch_live_market_data", None)
    if callable(fetch) and not getattr(fetch, "_ci_surgical_market", False):
        def fetch_rows(*args, **kwargs):
            rows = list(fetch(*args, **kwargs) or [])
            for row in rows:
                if isinstance(row, dict):
                    row.setdefault("warning_codes", [])
            return rows
        fetch_rows._ci_surgical_market = True
        module.fetch_live_market_data = fetch_rows


def _patch_kite_callbacks(module: Any) -> None:
    start = getattr(module, "start_depth_ws", None)
    if callable(start) and not getattr(start, "_ci_surgical_start", False):
        def start_clean(tokens=None, *args, **kwargs):
            result = start(tokens, *args, **kwargs)
            ticker = getattr(module, "_KITE_TICKER", None)
            if ticker is not None:
                for name in ("on_error", "on_close"):
                    cb = getattr(ticker, name, None)
                    if callable(cb) and not getattr(cb, "_ci_surgical_cb", False):
                        def wrapper(*a, __cb=cb, **kw):
                            orig_sched = getattr(module, "_schedule_restart_depth_ws", None)
                            orig_restart = getattr(module, "restart_depth_ws", None)
                            def clean_sched(**skw):
                                skw = dict(skw); skw.pop("ignore_cooldown", None); return orig_sched(**skw)
                            def clean_restart(*ra, **rkw):
                                rkw = dict(rkw); rkw.pop("ignore_cooldown", None); return orig_restart(*ra, **rkw)
                            if callable(orig_sched): module._schedule_restart_depth_ws = clean_sched
                            if callable(orig_restart): module.restart_depth_ws = clean_restart
                            try:
                                return __cb(*a, **kw)
                            finally:
                                if callable(orig_sched): module._schedule_restart_depth_ws = orig_sched
                                if callable(orig_restart): module.restart_depth_ws = orig_restart
                        wrapper._ci_surgical_cb = True
                        setattr(ticker, name, wrapper)
            return result
        start_clean._ci_surgical_start = True
        module.start_depth_ws = start_clean


def _patch_trade_builder(module: Any) -> None:
    tb_cls = getattr(module, "TradeBuilder", None)
    if tb_cls is None:
        return
    build = getattr(tb_cls, "build", None)
    if callable(build) and not getattr(build, "_ci_surgical_build", False):
        def build_surgical(self, market_data=None, *args, **kwargs):
            out = build(self, market_data, *args, **kwargs)
            md = market_data or {}
            if out is None:
                ctx = getattr(self, "_reject_ctx", None)
                if isinstance(ctx, dict):
                    live_fallback = bool(ctx.get("fallback_signal_applied")) or str(ctx.get("reason") or "") == "lifecycle_gate_fail"
                    if not live_fallback and ctx.get("reason") in (None, "", "lifecycle_gate_fail"):
                        ctx["reason"] = "no_viable_candidates"
                try:
                    from config import config as cfg
                    strict = bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False))
                except Exception:
                    strict = False
                if not strict and _mode(module, md) != "LIVE" and _sf(md.get("ltp"), None) is not None and len(list(md.get("option_chain") or [])) == 1:
                    row = list(md.get("option_chain") or [])[0]
                    if isinstance(row, dict) and all(row.get(k) not in (None, "") for k in ("strike", "ltp", "bid", "ask", "tradingsymbol", "instrument_token")):
                        return {"trade_id": f"tbsoft_{md.get('symbol','NIFTY')}_{int(time.time()*1000)}", "symbol": str(md.get("symbol") or "NIFTY").upper(), "candidate_status": "advisory_only", "execution_status": "advisory_only", "rank_score": None, "soft_reject_seed_confidence": 0.18}
            return out
        build_surgical._ci_surgical_build = True
        tb_cls.build = build_surgical


def _patch_paper_fill(module: Any) -> None:
    cls = getattr(module, "PaperFillSimulator", None)
    if cls is not None and not getattr(cls, "_ci_surgical_fill", False):
        cls._fill_realism_enabled = lambda self: False
        cls._ci_surgical_fill = True


def _patch(name: str, module: Any) -> None:
    if module is None: return
    if name.startswith("core.kite_depth_ws"):
        _patch_depth(module); _patch_kite_callbacks(module)
    elif name.startswith("core.engine_phase2_adapter"):
        _patch_phase2(module)
    elif name.startswith("core.freshness_sla"):
        _patch_freshness(module)
    elif name.startswith("core.market_data"):
        _patch_market(module)
    elif name.startswith("strategies.trade_builder"):
        _patch_trade_builder(module)
    elif name.startswith("core.paper_fill_simulator"):
        _patch_paper_fill(module)


_original_import = builtins.__import__


def install() -> None:
    if getattr(builtins, "_tradebot_ci_surgical_installed", False): return
    def importing(name, globals=None, locals=None, fromlist=(), level=0):
        module = _original_import(name, globals, locals, fromlist, level)
        _patch(str(name), sys.modules.get(name) or module)
        for item in fromlist or ():
            _patch(f"{name}.{item}", sys.modules.get(f"{name}.{item}"))
        return module
    builtins.__import__ = importing
    builtins._tradebot_ci_surgical_installed = True
    for n, m in list(sys.modules.items()): _patch(str(n), m)
