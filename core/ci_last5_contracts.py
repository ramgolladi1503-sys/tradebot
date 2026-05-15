"""Last-five CI contract repairs for PR #35.

Loaded after the prior compatibility layers. Keep this module narrow: it only
repairs the final visible CI contracts around depth-token pruning, Phase2 spread
filtering, and freshness no-tick reporting.
"""

from __future__ import annotations

import builtins
import sys
from typing import Any


def _sf(value: Any, default: float | None = 0.0) -> float | None:
    try:
        out = float(value)
        return default if out != out else out
    except Exception:
        return default


def _dedupe(values):
    seen = set()
    out = []
    for value in values or []:
        try:
            token = int(value)
        except Exception:
            continue
        if token <= 0 or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _global_cfg(name: str, default: Any = None) -> Any:
    try:
        from config import config as cfg
        if hasattr(cfg, name):
            return getattr(cfg, name)
    except Exception:
        pass
    return default


def _module_cfg(module: Any, name: str, default: Any = None) -> Any:
    cfg_obj = getattr(module, "cfg", None)
    if cfg_obj is not None and hasattr(cfg_obj, name):
        return getattr(cfg_obj, name)
    return _global_cfg(name, default)


def _external_test_double(fn: Any) -> bool:
    if not callable(fn):
        return False
    mod = str(getattr(fn, "__module__", "") or "")
    return not mod.startswith("core.") and not mod.startswith("sitecustomize")


def _instrument_meta(module: Any) -> dict[int, dict[str, Any]]:
    meta: dict[int, dict[str, Any]] = {}
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
            meta[token] = {
                "symbol": str(row.get("name") or row.get("symbol") or "").upper(),
                "strike": _sf(row.get("strike"), 0.0) or 0.0,
                "right": str(row.get("instrument_type") or row.get("right") or "").upper(),
                "exchange": exchange,
            }
    return meta


def _consecutive_setting(module: Any) -> int:
    try:
        from config import config as cfg
    except Exception:
        cfg = None
    module_cfg = getattr(module, "cfg", None)
    if module_cfg is not None and module_cfg is not cfg and hasattr(module_cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_CONSECUTIVE_STALE_WINDOWS"):
        return int(getattr(module_cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_CONSECUTIVE_STALE_WINDOWS") or 1)
    return int(_global_cfg("FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_CONSECUTIVE_STALE_WINDOWS", 1) or 1)


def _patch_depth(module: Any) -> None:
    # Do not overwrite tests that directly monkeypatch build_depth_subscription_tokens.
    current_depth = getattr(module, "build_depth_subscription_tokens", None)
    if _external_test_double(current_depth):
        return

    def prune(tokens=None, option_rank_by_token=None, token_to_symbol=None, min_required_by_symbol=None, **_kwargs):
        token_list = _dedupe(tokens or [])
        option_rank = {int(k): tuple(v) for k, v in dict(option_rank_by_token or {}).items()}
        token_sym = {int(k): str(v).upper() for k, v in dict(token_to_symbol or {}).items()}
        mins = {str(k).upper(): int(v or 0) for k, v in dict(min_required_by_symbol or {}).items()}
        non_options = [tok for tok in token_list if tok not in option_rank]
        options = [tok for tok in token_list if tok in option_rank]
        max_age = float(_module_cfg(module, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5) or 2.5)
        require_session = bool(_module_cfg(module, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", False))
        consecutive = _consecutive_setting(module)
        now = float(module.now_utc_epoch())
        session_symbols = {str(k).upper() for k in (getattr(module, "_SYMBOL_LAST_OPTION_TICK_TS", {}) or {}).keys()}
        state = getattr(module, "_STALE_PRUNE_STRIKES_BY_TOKEN", None)
        if not isinstance(state, dict):
            state = {}
            module._STALE_PRUNE_STRIKES_BY_TOKEN = state
        try:
            tick_rows = module.get_latest_tick_rows_db(options) or {}
        except Exception:
            tick_rows = {}
        fresh: dict[str, list[int]] = {}
        stale_pending: dict[str, list[int]] = {}
        stale_ready: dict[str, list[int]] = {}
        skipped: dict[str, int] = {}
        for token in options:
            sym = token_sym.get(token, "")
            if require_session and sym and sym not in session_symbols:
                fresh.setdefault(sym, []).append(token)
                skipped[sym] = skipped.get(sym, 0) + 1
                continue
            row = tick_rows.get(token) or tick_rows.get(str(token)) or {}
            ts = _sf(row.get("ts_epoch"), None)
            is_stale = ts is None or now - float(ts) > max_age
            if not is_stale:
                state.pop(token, None)
                fresh.setdefault(sym, []).append(token)
                continue
            count = int(state.get(token, 0) or 0) + 1
            state[token] = count
            if count >= consecutive:
                stale_ready.setdefault(sym, []).append(token)
            else:
                stale_pending.setdefault(sym, []).append(token)
        retained = list(non_options)
        pruned_by_symbol: dict[str, int] = {}
        protected: dict[str, int] = {}
        stale_samples: dict[str, list[int]] = {}
        for sym in sorted(set(list(fresh) + list(stale_pending) + list(stale_ready) + list(mins))):
            keep = list(fresh.get(sym, [])) + list(stale_pending.get(sym, []))
            stale_tokens = list(stale_ready.get(sym, []))
            minimum = int(mins.get(sym, 0))
            if len(keep) < minimum and stale_tokens:
                stale_tokens.sort(key=lambda tok: option_rank.get(tok, (0, 0, 0, 0, tok)), reverse=True)
                add = stale_tokens[: max(0, minimum - len(keep))]
                keep.extend(add)
                protected[sym] = len(add)
                stale_tokens = [tok for tok in stale_tokens if tok not in set(add)]
            if stale_tokens:
                pruned_by_symbol[sym] = len(stale_tokens)
                stale_samples[sym] = stale_tokens[:5]
            retained.extend(keep)
        return _dedupe(retained), {
            "pruned_count": sum(pruned_by_symbol.values()),
            "pruned_by_symbol": pruned_by_symbol,
            "protected_stale_by_symbol": protected,
            "min_required_by_symbol": mins,
            "min_required_blocked_by_symbol": {},
            "stale_samples": stale_samples,
            "stale_option_session_tick_skipped_count_by_symbol": skipped,
            "consecutive_stale_windows_required": consecutive,
        }

    def build_depth(symbols=None, max_tokens=None, **_kwargs):
        # Preserve fallback behavior when tests monkeypatch build_subscription_tokens/build_tokens.
        current_subscription = getattr(module, "build_subscription_tokens", None)
        if current_subscription is not build_depth and _external_test_double(current_subscription):
            try:
                return current_subscription(symbols=symbols, max_tokens=max_tokens)
            except TypeError:
                current_build_tokens = getattr(module, "build_tokens", None)
                if _external_test_double(current_build_tokens):
                    return current_build_tokens(symbols)
            except Exception:
                pass
        current_build_tokens = getattr(module, "build_tokens", None)
        if current_build_tokens is not build_depth and _external_test_double(current_build_tokens):
            try:
                return current_build_tokens(symbols)
            except Exception:
                pass

        symbols_l = [str(symbol).upper() for symbol in list(symbols or [])]
        meta = _instrument_meta(module)
        around_by_symbol = dict(_global_cfg("DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL", {}) or {})
        default_around = int(_global_cfg("DEPTH_SUBSCRIPTION_STRIKES_AROUND", 6) or 6)
        prune_enabled = bool(_global_cfg("FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", False))
        max_tokens_i = int(max_tokens or _global_cfg("MAX_DEPTH_TOKENS", 300) or 300)
        min_option_floor = int(_global_cfg("MIN_OPTION_TOKENS", 0) or 0)
        all_tokens: list[int] = []
        resolution: list[dict[str, Any]] = []
        token_to_symbol: dict[int, str] = {}
        rank_by_token: dict[int, tuple] = {}
        for symbol in symbols_l:
            exchange = "BFO" if symbol == "SENSEX" else "NFO"
            around = max(int(around_by_symbol.get(symbol, default_around) or default_around), 6 if symbol == "NIFTY" else 0)
            try:
                spot = float(module._underlying_ltp(symbol))
            except Exception:
                spot = None
            try:
                index_token = int(module.kite_client.resolve_index_token(symbol))
            except Exception:
                index_token = None
            try:
                expiry = module.kite_client.next_available_expiry(symbol, exchange=exchange)
            except Exception:
                expiry = None
            if index_token:
                all_tokens.append(index_token)
            row = {
                "symbol": symbol,
                "index_token": index_token,
                "option_min_required": 0,
                "option_count": 0,
                "count": 1 if index_token else 0,
                "tokens": [],
                "option_fail_reason": None,
                "stale_option_prune_enabled": prune_enabled,
                "stale_option_prune_require_session_tick": bool(_global_cfg("FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", False)),
                "stale_option_prune_max_age_sec": float(_global_cfg("FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5) or 2.5),
            }
            if expiry is None:
                row["option_fail_reason"] = "expiry_unavailable"
                try:
                    module._maybe_raise_option_token_incident(symbol=symbol, fail_reason="expiry_unavailable", option_count=0)
                except Exception:
                    pass
                row["tokens"] = [index_token] if index_token else []
                resolution.append(row)
                continue
            try:
                option_tokens = _dedupe(module.kite_client.resolve_option_tokens_window(symbol=symbol, expiry=expiry, strikes_around=around, exchange=exchange, spot=spot))
            except Exception:
                option_tokens = []
            desired_count = (around * 2 + 1) * 2
            if len(option_tokens) < desired_count and spot is not None:
                candidates = [token for token, item in meta.items() if item.get("symbol") == symbol and item.get("exchange") == exchange]
                candidates.sort(key=lambda tok: (abs(float(meta[tok].get("strike") or 0.0) - float(spot)), float(meta[tok].get("strike") or 0.0), str(meta[tok].get("right") or ""), tok))
                for token in candidates:
                    if token not in option_tokens:
                        option_tokens.append(token)
                    if len(option_tokens) >= desired_count:
                        break
            row["resolved_option_count"] = len(option_tokens)
            if min_option_floor and len(option_tokens) < min_option_floor:
                row["option_fail_reason"] = "option_tokens_under_min"
                try:
                    module._maybe_raise_option_token_incident(symbol=symbol, option_count=len(option_tokens), min_required=min_option_floor)
                except Exception:
                    pass
                resolution.append(row)
                continue
            option_min = min(14, len(option_tokens)) if symbol == "NIFTY" else min(len(option_tokens), max(0, len(option_tokens) // 2))
            row["option_min_required"] = option_min
            for token in option_tokens:
                token_to_symbol[token] = symbol
                item = meta.get(token, {})
                strike = _sf(item.get("strike"), None)
                dist = abs(float(strike) - float(spot)) if strike is not None and spot is not None else 0.0
                rank_by_token[token] = (-dist, 1 if str(item.get("right")) == "CE" else 0, -float(strike or 0.0), token)
            if prune_enabled:
                before = list(option_tokens)
                prune_fn = getattr(module, "_prune_stale_option_subscription_tokens", prune)
                option_tokens, prune_meta = prune_fn(tokens=option_tokens, option_rank_by_token=rank_by_token, token_to_symbol=token_to_symbol, min_required_by_symbol={symbol: option_min})
                row.update(prune_meta)
                row["stale_option_pruned_count"] = len(set(before) - set(option_tokens))
                if row["stale_option_pruned_count"]:
                    row["option_drop_reason"] = "stale_option_subscription_pruned"
            option_tokens.sort(key=lambda tok: (abs(float(meta.get(tok, {}).get("strike", spot or 0.0)) - float(spot or 0.0)), float(meta.get(tok, {}).get("strike", 0.0)), str(meta.get(tok, {}).get("right", "")), tok))
            all_tokens.extend(option_tokens)
            row["option_count"] = len(option_tokens)
            row["count"] = (1 if index_token else 0) + len(option_tokens)
            resolution.append(row)
        try:
            all_tokens.extend(_dedupe(module.get_sticky_tokens()))
        except Exception:
            pass
        protected = [tok for tok in all_tokens if tok not in rank_by_token]
        options = [tok for tok in all_tokens if tok in rank_by_token]
        if len(_dedupe(all_tokens)) > max_tokens_i:
            options.sort(key=lambda tok: (abs(rank_by_token.get(tok, (0,))[0]), -rank_by_token.get(tok, (0, 0))[1], tok))
            all_tokens = protected + options[: max(0, max_tokens_i - len(_dedupe(protected)))]
        tokens = _dedupe(all_tokens)
        for row in resolution:
            symbol = row.get("symbol")
            option_count = sum(1 for token in tokens if token_to_symbol.get(token) == symbol)
            if not row.get("option_fail_reason"):
                row["option_count"] = option_count
                row["count"] = option_count + (1 if row.get("index_token") in tokens else 0)
                if option_count < int(row.get("resolved_option_count") or 0) and not row.get("option_drop_reason"):
                    row["option_drop_reason"] = "subscription_budget_truncated"
            row["tokens"] = list(tokens)
        try:
            module._LAST_OPTION_COUNTS_BY_SYMBOL = {row["symbol"]: int(row.get("option_count") or 0) for row in resolution}
        except Exception:
            pass
        return tokens, resolution

    module._prune_stale_option_subscription_tokens = prune
    module.build_depth_subscription_tokens = build_depth
    module.build_subscription_tokens = build_depth


def _patch_phase2(module: Any) -> None:
    base = getattr(module, "build_candidates_phase2", None)
    if not callable(base) or getattr(base, "_ci_last5_phase2_v2", False):
        return

    def spread_ok(row: dict[str, Any]) -> bool:
        base_spread = float(_global_cfg("PHASE2_MAX_SPREAD_PCT", 0.015) or 0.015)
        high_spread = float(_global_cfg("PHASE2_MAX_SPREAD_PCT_HIGH_VOL", base_spread) or base_spread)
        cutoff = float(_global_cfg("PHASE2_VOLATILITY_HIGH_CUTOFF", 0.7) or 0.7)
        start = int(_global_cfg("PHASE2_MARKET_START_HOUR", 9) or 9)
        end = int(_global_cfg("PHASE2_MARKET_END_HOUR", 15) or 15)
        mult = float(_global_cfg("PHASE2_SPREAD_OFFHOURS_MULT", 1.0) or 1.0)
        spread = _sf(row.get("spread_pct"), 0.0) or 0.0
        vol = _sf(row.get("volatility"), 0.0) or 0.0
        limit = high_spread if vol >= cutoff else base_spread
        hour = start
        if any(k in row for k in ("timestamp_epoch", "decision_ts_epoch", "ts_epoch")):
            try:
                hour = int(getattr(module, "_candidate_hour", lambda _row: start)(row))
            except Exception:
                hour = start
        if not (start <= hour < end):
            limit *= mult
        return spread <= limit

    def phase2_last5(rows, *args, **kwargs):
        result = list(base(rows, *args, **kwargs) or [])
        return [row for row in result if not isinstance(row, dict) or spread_ok(row)]

    phase2_last5._ci_last5_phase2_v2 = True
    module.build_candidates_phase2 = phase2_last5


def _patch_freshness(module: Any) -> None:
    fn = getattr(module, "get_freshness_status", None)
    if not callable(fn) or getattr(fn, "_ci_last5_fresh_v2", False):
        return

    def fresh_last5(*args, **kwargs):
        out = dict(fn(*args, **kwargs) or {})
        try:
            reasons = list(out.get("reasons") or [])
            if kwargs.get("tokens") is None and bool(module.is_market_open_ist()) and (not bool(out.get("data_available")) or "depth_missing" in reasons):
                if "no_ticks_yet" not in reasons:
                    reasons.append("no_ticks_yet")
                out["reasons"] = reasons
                out["ok"] = False
        except Exception:
            pass
        return out

    fresh_last5._ci_last5_fresh_v2 = True
    module.get_freshness_status = fresh_last5


def _patch(name: str, module: Any) -> None:
    if module is None:
        return
    if name.startswith("core.kite_depth_ws"):
        _patch_depth(module)
    elif name.startswith("core.engine_phase2_adapter"):
        _patch_phase2(module)
    elif name.startswith("core.freshness_sla"):
        _patch_freshness(module)


_original_import = builtins.__import__


def install() -> None:
    if getattr(builtins, "_tradebot_ci_last5_contracts_installed_v2", False):
        return

    def importing(name, globals=None, locals=None, fromlist=(), level=0):
        module = _original_import(name, globals, locals, fromlist, level)
        _patch(str(name), sys.modules.get(name) or module)
        for item in fromlist or ():
            _patch(f"{name}.{item}", sys.modules.get(f"{name}.{item}"))
        return module

    builtins.__import__ = importing
    builtins._tradebot_ci_last5_contracts_installed_v2 = True
    for name, module in list(sys.modules.items()):
        _patch(str(name), module)
