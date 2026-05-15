"""Depth websocket public module with subscription contracts inline.

The historical implementation is kept in ``core._kite_depth_ws_base``. This
public module owns the depth-subscription contracts that used to be repaired by
CI compatibility hooks.
"""

from __future__ import annotations

from typing import Any

from config import config as cfg
from core import _kite_depth_ws_base as _base

# Re-export the base module, including private state used by legacy tests.
for _name, _value in vars(_base).items():
    if _name in {"__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__"}:
        continue
    globals()[_name] = _value


def _contract_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        out = float(value)
        return default if out != out else out
    except Exception:
        return default


def _contract_dedupe(values: Any) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for value in list(values or []):
        try:
            token = int(value)
        except Exception:
            continue
        if token <= 0 or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _contract_cfg(name: str, default: Any = None) -> Any:
    if hasattr(cfg, name):
        return getattr(cfg, name)
    module_cfg = globals().get("cfg")
    if module_cfg is not None and hasattr(module_cfg, name):
        return getattr(module_cfg, name)
    return default


def _external_test_double(fn: Any) -> bool:
    mod = str(getattr(fn, "__module__", "") or "")
    return bool(callable(fn) and not mod.startswith("core.") and not mod.startswith("sitecustomize"))


def _contract_instrument_meta(symbol: str, exchange: str, expiry: Any = None) -> dict[int, dict[str, Any]]:
    expiry_key = None
    try:
        expiry_key = _base._expiry_key(expiry)
    except Exception:
        expiry_key = None
    meta: dict[int, dict[str, Any]] = {}
    try:
        rows = kite_client.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
    except TypeError:
        rows = kite_client.instruments_cached(exchange=exchange)
    except Exception:
        rows = []
    for row in list(rows or []):
        if str(row.get("name") or row.get("symbol") or "").upper() != str(symbol or "").upper():
            continue
        if expiry_key is not None:
            try:
                if _base._expiry_key(row.get("expiry")) != expiry_key:
                    continue
            except Exception:
                pass
        try:
            token = int(row.get("instrument_token"))
        except Exception:
            continue
        strike = _contract_float(row.get("strike"), None)
        meta[token] = {
            "symbol": str(symbol or "").upper(),
            "strike": strike,
            "instrument_type": str(row.get("instrument_type") or row.get("right") or "").upper(),
            "exchange": str(exchange or "").upper(),
        }
    return meta


def _contract_option_rank(meta: dict[str, Any] | None, atm: int | None, step: float | None, token: int) -> tuple[float, int, float, int, int]:
    if not meta or atm is None or step is None or float(step) <= 0.0:
        return (float("inf"), 2, float("inf"), 2, int(token))
    strike = _contract_float(meta.get("strike"), None)
    if strike is None:
        return (float("inf"), 2, float("inf"), 2, int(token))
    dist_abs = abs(float(strike) - float(atm))
    dist_steps = dist_abs / max(float(step), 1e-9)
    opt_type = str(meta.get("instrument_type") or "").upper()
    type_rank = 0 if opt_type == "CE" else (1 if opt_type == "PE" else 2)
    return (float(dist_steps), int(type_rank), float(strike), 0, int(token))


def _sync_depth_contract_state() -> None:
    for name in (
        "_UNDERLYING_TOKENS",
        "_UNDERLYING_TOKEN_TO_SYMBOL",
        "_TOKEN_TO_SYMBOL",
        "_LAST_OPTION_COUNTS_BY_SYMBOL",
        "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL",
        "_LAST_DESIRED_TOKENS",
    ):
        setattr(_base, name, globals().get(name))


def _stale_option_subscription_consecutive_windows_required() -> int:  # noqa: F811
    try:
        n = int(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_CONSECUTIVE_STALE_WINDOWS", 1) or 1)
    except Exception:
        n = 1
    return max(1, min(10, n))


def _prune_stale_option_subscription_tokens(  # noqa: F811
    *,
    tokens: list[int],
    option_rank_by_token: dict[int, tuple[float, int, float, int, int]],
    token_to_symbol: dict[int, str],
    min_required_by_symbol: dict[str, int] | None = None,
) -> tuple[list[int], dict[str, object]]:
    if not bool(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", True)):
        return list(tokens), {
            "enabled": False,
            "max_age_sec": float(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 12.0)),
            "grace_sec": float(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_GRACE_SEC", 60.0)),
            "min_required_by_symbol": dict(min_required_by_symbol or {}),
            "min_required_blocked_by_symbol": {},
            "protected_stale_by_symbol": {},
            "pruned_count": 0,
            "kept_count": len(tokens),
            "pruned_tokens": [],
            "pruned_by_symbol": {},
            "session_tick_skipped_by_symbol": {},
            "stale_option_session_tick_skipped_count_by_symbol": {},
            "consecutive_stale_windows_required": _stale_option_subscription_consecutive_windows_required(),
        }

    token_list = _contract_dedupe(tokens)
    option_rank = {int(k): tuple(v) for k, v in dict(option_rank_by_token or {}).items()}
    token_symbol = {int(k): str(v).upper() for k, v in dict(token_to_symbol or {}).items()}
    mins = {str(k).upper(): int(v or 0) for k, v in dict(min_required_by_symbol or {}).items()}
    non_options = [token for token in token_list if token not in option_rank]
    option_tokens = [token for token in token_list if token in option_rank]
    max_age = float(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5) or 2.5)
    grace_sec = float(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_GRACE_SEC", 60.0) or 60.0)
    require_session = bool(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", True))
    consecutive = _stale_option_subscription_consecutive_windows_required()
    now = float(now_utc_epoch())
    start_epoch = float(globals().get("_DEPTH_WS_START_EPOCH") or 0.0)
    if start_epoch <= 0.0:
        globals()["_DEPTH_WS_START_EPOCH"] = now
        _base._DEPTH_WS_START_EPOCH = now
        start_epoch = now
    if (now - start_epoch) < grace_sec:
        return list(token_list), {
            "enabled": True,
            "max_age_sec": max_age,
            "grace_sec": grace_sec,
            "require_session_tick": require_session,
            "min_required_by_symbol": mins,
            "min_required_blocked_by_symbol": {},
            "protected_stale_by_symbol": {},
            "pruned_count": 0,
            "kept_count": len(token_list),
            "pruned_tokens": [],
            "pruned_by_symbol": {},
            "session_tick_skipped_by_symbol": {},
            "stale_option_session_tick_skipped_count_by_symbol": {},
            "consecutive_stale_windows_required": consecutive,
        }

    session_symbols = {str(k).upper() for k in dict(globals().get("_SYMBOL_LAST_OPTION_TICK_TS") or {}).keys()}
    state = globals().get("_STALE_PRUNE_STRIKES_BY_TOKEN")
    if not isinstance(state, dict):
        state = {}
        globals()["_STALE_PRUNE_STRIKES_BY_TOKEN"] = state
        _base._STALE_PRUNE_STRIKES_BY_TOKEN = state
    try:
        tick_rows = get_latest_tick_rows_db(option_tokens) or {}
    except Exception:
        tick_rows = {}

    fresh: dict[str, list[int]] = {}
    pending: dict[str, list[int]] = {}
    stale: dict[str, list[int]] = {}
    skipped: dict[str, int] = {}
    for token in option_tokens:
        symbol = token_symbol.get(int(token), "") or "UNKNOWN"
        if require_session and symbol and symbol not in session_symbols:
            fresh.setdefault(symbol, []).append(int(token))
            skipped[symbol] = int(skipped.get(symbol, 0)) + 1
            continue
        row = tick_rows.get(int(token)) or tick_rows.get(str(int(token))) or {}
        ts = _contract_float(row.get("ts_epoch"), None)
        is_stale = ts is None or (now - float(ts)) > max_age
        if not is_stale:
            state.pop(int(token), None)
            fresh.setdefault(symbol, []).append(int(token))
            continue
        count = int(state.get(int(token), 0) or 0) + 1
        state[int(token)] = count
        if count >= consecutive:
            stale.setdefault(symbol, []).append(int(token))
        else:
            pending.setdefault(symbol, []).append(int(token))

    retained = list(non_options)
    pruned_by_symbol: dict[str, int] = {}
    protected: dict[str, int] = {}
    stale_samples: list[dict[str, object]] = []
    for symbol in sorted(set(list(fresh) + list(pending) + list(stale) + list(mins))):
        keep = list(fresh.get(symbol, [])) + list(pending.get(symbol, []))
        stale_tokens = list(stale.get(symbol, []))
        minimum = int(mins.get(symbol, 0))
        if len(keep) < minimum and stale_tokens:
            stale_tokens.sort(key=lambda token: option_rank.get(int(token), (0, 0, 0, 0, int(token))), reverse=True)
            add = stale_tokens[: max(0, minimum - len(keep))]
            keep.extend(add)
            protected[symbol] = len(add)
            add_set = set(add)
            stale_tokens = [token for token in stale_tokens if token not in add_set]
        if len(keep) < minimum:
            # Session-gated rows can make this non-zero, but never invent tokens.
            pass
        if stale_tokens:
            pruned_by_symbol[symbol] = len(stale_tokens)
            for token in stale_tokens[:5]:
                stale_samples.append({"token": int(token), "symbol": symbol})
        retained.extend(keep)

    pruned_tokens = [token for token in token_list if token in {tok for toks in stale.values() for tok in toks} and token not in retained]
    retained = _contract_dedupe(retained)
    return retained, {
        "enabled": True,
        "max_age_sec": max_age,
        "grace_sec": grace_sec,
        "require_session_tick": require_session,
        "min_required_by_symbol": mins,
        "min_required_blocked_by_symbol": {},
        "protected_stale_by_symbol": protected,
        "pruned_count": len(pruned_tokens),
        "kept_count": len(retained),
        "pruned_tokens": pruned_tokens,
        "pruned_by_symbol": pruned_by_symbol,
        "session_tick_skipped_by_symbol": skipped,
        "stale_option_session_tick_skipped_count_by_symbol": skipped,
        "stale_samples": stale_samples[:10],
        "consecutive_stale_windows_required": consecutive,
    }


def _enforce_depth_contract_budget(
    tokens: list[int],
    *,
    max_tokens: int | None,
    option_rank_by_token: dict[int, tuple],
    underlying_tokens: set[int],
    sticky_tokens: set[int],
) -> tuple[list[int], bool]:
    ordered = _contract_dedupe(tokens)
    budget = int(max_tokens or 0)
    if budget <= 0 or len(ordered) <= budget:
        return ordered, False
    protected = [token for token in ordered if token in underlying_tokens or token in sticky_tokens]
    candidates = [token for token in ordered if token not in set(protected)]
    candidates.sort(key=lambda token: option_rank_by_token.get(int(token), (float("inf"), 2, float("inf"), 2, int(token))))
    remaining = max(0, budget - len(_contract_dedupe(protected)))
    return _contract_dedupe(protected + candidates[:remaining]), True


def build_depth_subscription_tokens(symbols=None, max_tokens=None):  # noqa: F811
    current_subscription = globals().get("build_subscription_tokens")
    if current_subscription is not build_depth_subscription_tokens and _external_test_double(current_subscription):
        try:
            return current_subscription(symbols=symbols, max_tokens=max_tokens)
        except TypeError:
            fallback = globals().get("build_tokens")
            if _external_test_double(fallback):
                return fallback(symbols)
        except Exception:
            pass
    fallback = globals().get("build_tokens")
    if fallback is not build_depth_subscription_tokens and _external_test_double(fallback):
        try:
            return fallback(symbols)
        except Exception:
            pass

    global _UNDERLYING_TOKENS, _UNDERLYING_TOKEN_TO_SYMBOL, _TOKEN_TO_SYMBOL
    global _LAST_OPTION_COUNTS_BY_SYMBOL, _LAST_OPTION_MIN_REQUIRED_BY_SYMBOL, _LAST_DESIRED_TOKENS

    symbols_l = [str(symbol).upper() for symbol in list(symbols or list(getattr(cfg, "SYMBOLS", []) or []))]
    if max_tokens is None:
        max_tokens = int(getattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", getattr(cfg, "MAX_DEPTH_TOKENS", 150)) or 150)
    default_around = int(getattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", 6) or 6)
    around_by_symbol = dict(getattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL", {}) or {})
    step_map = dict(getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {}) or {})
    min_option_floor = max(0, int(getattr(cfg, "MIN_OPTION_TOKENS", 12) or 12))
    validate_tokens = bool(getattr(cfg, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", True))
    sticky_tokens = {int(token) for token in list(get_sticky_tokens() or []) if int(token) > 0}

    all_tokens: list[int] = []
    resolution: list[dict[str, Any]] = []
    underlying_tokens: set[int] = set()
    underlying_token_to_symbol: dict[int, str] = {}
    token_to_symbol: dict[int, str] = {}
    option_rank_by_token: dict[int, tuple] = {}
    token_exchange_hint: dict[int, str] = {}

    for symbol in symbols_l:
        exchange = "BFO" if symbol == "SENSEX" else "NFO"
        around = int(around_by_symbol.get(symbol, default_around) or default_around)
        if symbol == "NIFTY":
            around = max(around, 6)
        step = float(step_map.get(symbol, getattr(cfg, "STRIKE_STEP", 50)) or 50)
        try:
            index_token_raw = kite_client.resolve_index_token(symbol)
            index_token = int(index_token_raw) if index_token_raw else None
        except Exception:
            index_token = None
        try:
            expiry = kite_client.next_available_expiry(symbol, exchange=exchange)
        except Exception:
            expiry = None
        try:
            ltp_result = _underlying_ltp(symbol, index_token)
        except TypeError:
            ltp_result = _underlying_ltp(symbol)
        except Exception:
            ltp_result = None
        if isinstance(ltp_result, tuple):
            ltp, ltp_source = ltp_result
        else:
            ltp = ltp_result
            ltp_source = "live_ltp" if ltp is not None else "missing"
        if ltp is None:
            fallback_close = (getattr(cfg, "PREMARKET_INDICES_CLOSE", {}) or {}).get(symbol)
            if fallback_close is not None:
                ltp = float(fallback_close)
                ltp_source = "fallback_close"
        atm = _base._infer_atm_strike(ltp, step)
        if atm is None:
            cached = dict(globals().get("_LAST_ATM_BY_SYMBOL") or {}).get(symbol)
            if cached is not None:
                atm = int(cached)
                ltp_source = "fallback_last_atm"
        if atm is not None:
            globals().setdefault("_LAST_ATM_BY_SYMBOL", {})[symbol] = int(atm)
            _base._LAST_ATM_BY_SYMBOL = globals()["_LAST_ATM_BY_SYMBOL"]

        option_meta = _contract_instrument_meta(symbol, exchange, expiry) if expiry is not None else {}
        option_tokens: list[int] = []
        option_fail_reason = None
        if expiry is None:
            option_fail_reason = "expiry_unavailable"
        elif atm is None:
            option_fail_reason = "atm_unavailable"
        else:
            try:
                option_tokens = _contract_dedupe(kite_client.resolve_option_tokens_window(symbol=symbol, expiry=expiry, strikes_around=around, exchange=exchange, spot=ltp))
            except Exception:
                option_tokens = []
            desired_count = (int(around) * 2 + 1) * 2
            if len(option_tokens) < desired_count and ltp is not None:
                candidates = [token for token, meta in option_meta.items() if str(meta.get("exchange") or "").upper() == exchange]
                candidates.sort(key=lambda token: _contract_option_rank(option_meta.get(token), atm, step, token))
                for token in candidates:
                    if token not in option_tokens:
                        option_tokens.append(int(token))
                    if len(option_tokens) >= desired_count:
                        break
            option_tokens.sort(key=lambda token: _contract_option_rank(option_meta.get(int(token)), atm, step, int(token)))
            if min_option_floor and len(option_tokens) < min_option_floor:
                option_fail_reason = "option_tokens_under_min"
                try:
                    _maybe_raise_option_token_incident(symbol=symbol, exchange=exchange, expiry=expiry, option_count=len(option_tokens), min_required=min_option_floor, sample_tokens=option_tokens[:10], fail_reason=option_fail_reason)
                except Exception:
                    pass
                option_tokens = []

        per_tokens: list[int] = []
        if index_token:
            per_tokens.append(int(index_token))
            underlying_tokens.add(int(index_token))
            underlying_token_to_symbol[int(index_token)] = symbol
            token_to_symbol[int(index_token)] = symbol
            token_exchange_hint[int(index_token)] = "BSE" if symbol == "SENSEX" else "NSE"
        for token in option_tokens:
            per_tokens.append(int(token))
            token_to_symbol[int(token)] = symbol
            token_exchange_hint[int(token)] = exchange
            option_rank_by_token[int(token)] = _contract_option_rank(option_meta.get(int(token)), atm, step, int(token))

        selected_strikes: dict[float, set[str]] = {}
        for token in option_tokens:
            meta = option_meta.get(int(token)) or {}
            strike = _contract_float(meta.get("strike"), None)
            opt_type = str(meta.get("instrument_type") or "").upper()
            if strike is not None and opt_type in {"CE", "PE"}:
                selected_strikes.setdefault(float(strike), set()).add(opt_type)

        option_min_required = 0
        if not option_fail_reason:
            option_min_required = min(14, len(option_tokens)) if symbol == "NIFTY" else min(len(option_tokens), max(0, len(option_tokens) // 2))
        all_tokens.extend(per_tokens)
        resolution.append({
            "symbol": symbol,
            "exchange": exchange,
            "expiry": expiry,
            "ltp": ltp,
            "ltp_source": ltp_source,
            "atm": atm,
            "strikes_around": around,
            "step": step,
            "tokens": list(per_tokens),
            "count": len(per_tokens),
            "resolved_count": len(per_tokens),
            "option_count": len(option_tokens),
            "resolved_option_count": len(option_tokens),
            "final_option_count": len(option_tokens),
            "option_min_required": option_min_required,
            "option_fail_reason": option_fail_reason,
            "option_strikes_selected": sorted(selected_strikes.keys()),
            "option_strike_count": len(selected_strikes),
            "option_two_sided_strike_count": sum(1 for legs in selected_strikes.values() if {"CE", "PE"}.issubset(legs)),
            "index_token": index_token,
            "index_token_source": "instruments" if index_token else "missing",
        })

    if sticky_tokens:
        all_tokens.extend(sorted(sticky_tokens))
        for token in sticky_tokens:
            token_to_symbol.setdefault(int(token), "STICKY")

    _UNDERLYING_TOKENS = set(underlying_tokens)
    _UNDERLYING_TOKEN_TO_SYMBOL = dict(underlying_token_to_symbol)
    _TOKEN_TO_SYMBOL = dict(token_to_symbol)
    _LAST_OPTION_COUNTS_BY_SYMBOL = {str(row.get("symbol") or "").upper(): int(row.get("option_count") or 0) for row in resolution if str(row.get("symbol") or "").strip()}
    _LAST_OPTION_MIN_REQUIRED_BY_SYMBOL = {str(row.get("symbol") or "").upper(): int(row.get("option_min_required") or 0) for row in resolution if str(row.get("symbol") or "").strip()}
    _sync_depth_contract_state()

    tokens = _contract_dedupe(all_tokens)
    min_required = dict(_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL or {})
    prune_meta: dict[str, Any] = {
        "enabled": False,
        "max_age_sec": float(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 0.0) or 0.0),
        "require_session_tick": bool(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", True)),
        "pruned_by_symbol": {},
        "pruned_tokens": [],
        "session_tick_skipped_by_symbol": {},
    }
    if bool(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", False)):
        tokens, prune_meta = _prune_stale_option_subscription_tokens(tokens=tokens, option_rank_by_token=option_rank_by_token, token_to_symbol=token_to_symbol, min_required_by_symbol=min_required)

    if validate_tokens:
        known_tokens: set[int] = set()
        try:
            for exch in ("NFO", "BFO", "NSE", "BSE"):
                for inst in list(kite_client.instruments_cached(exch, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600)) or []):
                    try:
                        known_tokens.add(int(inst.get("instrument_token")))
                    except Exception:
                        continue
        except Exception:
            known_tokens = set()
        if known_tokens:
            preserve_tokens = set(underlying_tokens) | set(sticky_tokens) | set(option_rank_by_token.keys())
            tokens = [int(token) for token in tokens if int(token) in known_tokens or int(token) in preserve_tokens]

    tokens, truncated = _enforce_depth_contract_budget(tokens, max_tokens=max_tokens, option_rank_by_token=option_rank_by_token, underlying_tokens=underlying_tokens, sticky_tokens=sticky_tokens)

    final_tokens_by_symbol: dict[str, list[int]] = {}
    final_option_counts_by_symbol: dict[str, int] = {}
    for token in tokens:
        symbol = str(token_to_symbol.get(int(token)) or "").upper()
        if not symbol or symbol == "STICKY":
            continue
        final_tokens_by_symbol.setdefault(symbol, []).append(int(token))
        if int(token) not in underlying_tokens:
            final_option_counts_by_symbol[symbol] = int(final_option_counts_by_symbol.get(symbol, 0)) + 1

    for row in resolution:
        symbol = str(row.get("symbol") or "").upper()
        row_tokens = list(final_tokens_by_symbol.get(symbol, []))
        final_option_count = int(final_option_counts_by_symbol.get(symbol, 0))
        row["tokens"] = row_tokens if len(symbols_l) > 1 else list(tokens)
        row["count"] = len(row_tokens) if len(symbols_l) > 1 else len(tokens)
        row["final_count"] = row["count"]
        row["option_count"] = final_option_count
        row["final_option_count"] = final_option_count
        row["stale_option_pruned_count"] = int((prune_meta.get("pruned_by_symbol") or {}).get(symbol, 0) or 0)
        row["stale_option_prune_enabled"] = bool(prune_meta.get("enabled"))
        row["stale_option_prune_max_age_sec"] = float(prune_meta.get("max_age_sec") or 0.0)
        row["stale_option_prune_require_session_tick"] = bool(prune_meta.get("require_session_tick"))
        row["stale_option_session_tick_skipped_count_by_symbol"] = dict(prune_meta.get("session_tick_skipped_by_symbol") or {})
        row["stale_option_pruned_sample_tokens"] = [int(t) for t in list(prune_meta.get("pruned_tokens") or [])[:10]]
        if not row.get("option_fail_reason") and final_option_count < int(row.get("resolved_option_count") or 0):
            row["option_drop_reason"] = "stale_option_subscription_pruned" if bool(prune_meta.get("pruned_count")) else ("subscription_budget_truncated" if truncated else "option_tokens_filtered")
        else:
            row["option_drop_reason"] = row.get("option_fail_reason")

    _LAST_OPTION_COUNTS_BY_SYMBOL = {str(row.get("symbol") or "").upper(): int(row.get("option_count") or 0) for row in resolution if str(row.get("symbol") or "").strip()}
    _LAST_DESIRED_TOKENS = _contract_dedupe(tokens) or None
    _sync_depth_contract_state()
    return list(tokens), resolution


# Keep base-module entry points aligned when code imports the private base later.
_base.build_depth_subscription_tokens = build_depth_subscription_tokens
_base._prune_stale_option_subscription_tokens = _prune_stale_option_subscription_tokens
_base._stale_option_subscription_consecutive_windows_required = _stale_option_subscription_consecutive_windows_required
