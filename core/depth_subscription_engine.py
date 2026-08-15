"""Direct depth subscription engine rewrite scaffold.

This module owns the depth-subscription contracts directly and installs them on
``core.kite_depth_ws`` after the legacy CI compatibility hooks. It is an
intermediate rewrite branch scaffold: once it proves parity, the functions can
be moved into ``core/kite_depth_ws.py`` and the depth hooks can be removed.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from typing import Any

from config import config as cfg

_INSTALLED = False


def _ws_module() -> Any:
    module = sys.modules.get("core.kite_depth_ws")
    if module is not None:
        return module
    import core.kite_depth_ws as ws

    return ws


def _cfg(ws: Any) -> Any:
    return getattr(ws, "cfg", cfg)


def _sf(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
        return default if out != out else out
    except Exception:
        return default


def _cfg_float(conf: Any, name: str, default: float) -> float:
    value = getattr(conf, name, None)
    if value is None:
        return float(default)
    parsed = _sf(value, None)
    return float(default) if parsed is None else float(parsed)


def _cfg_int(conf: Any, name: str, default: int) -> int:
    value = getattr(conf, name, None)
    if value is None:
        return int(default)
    try:
        return int(value)
    except Exception:
        return int(default)


def _cfg_bool(conf: Any, name: str, default: bool) -> bool:
    value = getattr(conf, name, None)
    if value is None:
        return bool(default)
    return bool(value)


def _direct_prune_consecutive_windows(conf: Any) -> int:
    """Return consecutive stale windows for the direct prune contract.

    Direct calls to ``_prune_stale_option_subscription_tokens`` historically
    prune immediately unless a caller explicitly supplies a different value via
    ``ws.cfg``. Runtime subscription construction can still choose conservative
    settings before it calls direct prune, but this unit-level contract must not
    inherit broad global defaults that make isolated stale-prune tests order
    dependent.
    """
    if conf is cfg:
        return 1
    return _cfg_int(conf, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_CONSECUTIVE_STALE_WINDOWS", 1)


def _dedupe_tokens(values: Any) -> list[int]:
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


def _normalize_positive_tokens(ws: Any, values: Any) -> list[int]:
    fn = getattr(ws, "_normalize_positive_tokens", None)
    if callable(fn) and not getattr(fn, "_depth_rewrite_internal", False):
        try:
            return _dedupe_tokens(fn(values))
        except Exception:
            pass
    return _dedupe_tokens(values)


def _expiry_key(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    try:
        text = str(value).strip().split("T", 1)[0]
        return datetime.fromisoformat(text).date().isoformat() if text else None
    except Exception:
        return None


def _is_underlying(ws: Any, token: int) -> bool:
    try:
        return bool(getattr(ws, "_is_underlying_token")(int(token)))
    except Exception:
        return int(token) in set(getattr(ws, "_UNDERLYING_TOKENS", set()) or set())


def _infer_atm(ltp: float | None, step: float | None) -> int | None:
    if ltp is None or step is None or float(step) <= 0:
        return None
    try:
        return int(round(float(ltp) / float(step)) * float(step))
    except Exception:
        return None


def _underlying_ltp(ws: Any, symbol: str, index_token: int | None) -> tuple[float | None, str]:
    fn = getattr(ws, "_underlying_ltp", None)
    if callable(fn):
        try:
            result = fn(symbol, index_token)
        except TypeError:
            result = fn(symbol)
        except Exception:
            result = None
        if isinstance(result, tuple):
            return _sf(result[0], None), str(result[1] or "live_ltp")
        if result is not None:
            return _sf(result, None), "live_ltp"
    fallback = (getattr(_cfg(ws), "PREMARKET_INDICES_CLOSE", {}) or {}).get(str(symbol).upper())
    return (_sf(fallback, None), "fallback_close") if fallback is not None else (None, "missing")


def _load_option_meta(ws: Any, symbol: str, exchange: str, expiry: Any) -> dict[int, dict[str, Any]]:
    conf = _cfg(ws)
    expiry_norm = _expiry_key(expiry)
    segment = "BFO-OPT" if str(exchange).upper() == "BFO" else "NFO-OPT"
    try:
        rows = ws.kite_client.instruments_cached(exchange, ttl_sec=getattr(conf, "KITE_INSTRUMENTS_TTL", 3600))
    except TypeError:
        rows = ws.kite_client.instruments_cached(exchange=exchange)
    except Exception:
        rows = []
    out: dict[int, dict[str, Any]] = {}
    for row in list(rows or []):
        if str(row.get("segment") or "").upper() not in {segment, ""}:
            continue
        if str(row.get("name") or row.get("symbol") or "").upper() != str(symbol).upper():
            continue
        if expiry_norm is not None and _expiry_key(row.get("expiry")) != expiry_norm:
            continue
        try:
            token = int(row.get("instrument_token"))
        except Exception:
            continue
        out[token] = {
            "strike": _sf(row.get("strike"), None),
            "instrument_type": str(row.get("instrument_type") or row.get("right") or "").upper(),
            "exchange": str(exchange).upper(),
            "symbol": str(symbol).upper(),
        }
    return out


def _rank(meta: dict[str, Any] | None, atm: int | None, step: float | None, token: int) -> tuple[float, int, float, int, int]:
    if not meta or atm is None or step is None or float(step) <= 0:
        return (float("inf"), 2, float("inf"), 2, int(token))
    strike = _sf(meta.get("strike"), None)
    if strike is None:
        return (float("inf"), 2, float("inf"), 2, int(token))
    dist_abs = abs(float(strike) - float(atm))
    opt_type = str(meta.get("instrument_type") or "").upper()
    type_rank = 0 if opt_type == "CE" else (1 if opt_type == "PE" else 2)
    return (dist_abs / max(float(step), 1e-9), type_rank, float(strike), 0, int(token))


def _option_min_required(ws: Any, symbol: str, option_count: int) -> int:
    if option_count <= 0:
        return 0
    conf = _cfg(ws)
    floor = _cfg_int(conf, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MIN_REQUIRED_FLOOR", 14)
    by_symbol = getattr(conf, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MIN_REQUIRED_FLOOR_BY_SYMBOL", {}) or {}
    try:
        floor = int(by_symbol.get(str(symbol).upper(), floor) if by_symbol.get(str(symbol).upper(), None) is not None else floor)
    except Exception:
        pass
    return max(0, min(int(floor), int(option_count)))


def _classify_option_freshness(ws: Any, token: int, now_epoch: float, max_age_sec: float) -> tuple[bool, float | None, float | None, float | None]:
    try:
        row = (ws.get_latest_tick_rows_db([int(token)]) or {}).get(int(token)) or {}
    except Exception:
        row = {}
    db_epoch = _sf(row.get("ts_epoch"), None)
    memory_epoch = _sf((getattr(ws, "_LAST_MSG_TS_BY_TOKEN", {}) or {}).get(int(token)), None)
    effective = max([x for x in (db_epoch, memory_epoch) if x is not None], default=None)
    age = None if effective is None else max(0.0, float(now_epoch) - float(effective))
    return bool(age is not None and age <= max_age_sec), age, db_epoch, memory_epoch


def _prune_stale_option_subscription_tokens(*, tokens, option_rank_by_token, token_to_symbol, min_required_by_symbol=None):
    ws = _ws_module()
    conf = _cfg(ws)
    token_list = _dedupe_tokens(tokens)
    option_rank = {int(k): tuple(v) for k, v in dict(option_rank_by_token or {}).items()}
    token_symbol = {int(k): str(v).upper() for k, v in dict(token_to_symbol or {}).items()}
    minimums = {str(k).upper(): int(v or 0) for k, v in dict(min_required_by_symbol or {}).items()}
    max_age = _cfg_float(conf, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 12.0)
    grace = _cfg_float(conf, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_GRACE_SEC", 60.0)
    require_session = _cfg_bool(conf, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", True)
    consecutive = max(1, min(10, _direct_prune_consecutive_windows(conf)))
    if not _cfg_bool(conf, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", True):
        return token_list, {
            "enabled": False,
            "max_age_sec": max_age,
            "grace_sec": grace,
            "require_session_tick": require_session,
            "min_required_by_symbol": minimums,
            "min_required_blocked_by_symbol": {},
            "protected_stale_by_symbol": {},
            "pruned_count": 0,
            "kept_count": len(token_list),
            "pruned_tokens": [],
            "pruned_by_symbol": {},
            "session_tick_skipped_by_symbol": {},
            "stale_option_session_tick_skipped_count_by_symbol": {},
            "consecutive_stale_windows_required": consecutive,
            "stale_samples": [],
        }
    now = float(ws.now_utc_epoch())
    start = float(getattr(ws, "_DEPTH_WS_START_EPOCH", 0.0) or 0.0)
    if start <= 0.0:
        ws._DEPTH_WS_START_EPOCH = now
        start = now
    if now - start < grace:
        return token_list, {
            "enabled": True,
            "max_age_sec": max_age,
            "grace_sec": grace,
            "require_session_tick": require_session,
            "min_required_by_symbol": minimums,
            "min_required_blocked_by_symbol": {},
            "protected_stale_by_symbol": {},
            "pruned_count": 0,
            "kept_count": len(token_list),
            "pruned_tokens": [],
            "pruned_by_symbol": {},
            "session_tick_skipped_by_symbol": {},
            "stale_option_session_tick_skipped_count_by_symbol": {},
            "consecutive_stale_windows_required": consecutive,
            "stale_samples": [],
        }

    non_options = [t for t in token_list if t not in option_rank]
    # In this direct-prune contract, option_rank_by_token is the source of truth.
    # Do not consult process-global underlying state; tests use small fake tokens
    # that can collide with prior runtime state.
    option_tokens = [t for t in token_list if t in option_rank]
    session_symbols = {str(k).upper() for k in dict(getattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {}) or {}).keys()}
    stale_state = getattr(ws, "_STALE_PRUNE_STRIKES_BY_TOKEN", {})
    retained = list(non_options)
    pruned_tokens: list[int] = []
    pruned_by_symbol: dict[str, int] = {}
    protected_stale_by_symbol: dict[str, int] = {}
    session_skipped: dict[str, int] = {}
    stale_samples: list[dict[str, object]] = []

    for symbol in sorted({token_symbol.get(t, "") for t in option_tokens if token_symbol.get(t, "")}):
        sym_tokens = [t for t in option_tokens if token_symbol.get(t) == symbol]
        if require_session and symbol not in session_symbols:
            retained.extend(sym_tokens)
            session_skipped[symbol] = len(sym_tokens)
            continue
        fresh: list[int] = []
        stale_candidates: list[int] = []
        for token in sym_tokens:
            is_fresh, age, db_epoch, memory_epoch = _classify_option_freshness(ws, token, now, max_age)
            if is_fresh:
                fresh.append(token)
                stale_state[int(token)] = 0
            else:
                stale_state[int(token)] = int(stale_state.get(int(token), 0) or 0) + 1
                if int(stale_state.get(int(token), 0) or 0) >= consecutive:
                    stale_candidates.append(token)
                else:
                    fresh.append(token)
        minimum = max(0, int(minimums.get(symbol, 0) or 0))
        needed = max(0, minimum - len(fresh))
        stale_candidates.sort(key=lambda t: option_rank.get(int(t), (float("inf"), 2, float("inf"), 2, int(t))), reverse=True)
        protected = stale_candidates[:needed]
        pruned = [t for t in stale_candidates if t not in set(protected)]
        retained.extend(fresh + protected)
        if protected:
            protected_stale_by_symbol[symbol] = len(protected)
        if pruned:
            pruned_by_symbol[symbol] = len(pruned)
            pruned_tokens.extend(pruned)
            for token in pruned[:10]:
                _is_fresh, age, db_epoch, memory_epoch = _classify_option_freshness(ws, token, now, max_age)
                stale_samples.append({"token": int(token), "symbol": symbol, "age_sec": age, "db_epoch": db_epoch, "memory_epoch": memory_epoch})
    ws._STALE_PRUNE_STRIKES_BY_TOKEN = stale_state
    retained = _dedupe_tokens(retained)
    pruned_tokens = [t for t in token_list if t in set(pruned_tokens)]
    return retained, {
        "enabled": True,
        "max_age_sec": max_age,
        "grace_sec": grace,
        "require_session_tick": require_session,
        "min_required_by_symbol": minimums,
        "min_required_blocked_by_symbol": {},
        "protected_stale_by_symbol": protected_stale_by_symbol,
        "pruned_count": len(pruned_tokens),
        "kept_count": len(retained),
        "pruned_tokens": pruned_tokens,
        "pruned_by_symbol": pruned_by_symbol,
        "session_tick_skipped_by_symbol": session_skipped,
        "stale_option_session_tick_skipped_count_by_symbol": session_skipped,
        "consecutive_stale_windows_required": consecutive,
        "stale_samples": stale_samples[:10],
    }


def _resolve_known_tokens(ws: Any) -> set[int]:
    conf = _cfg(ws)
    known: set[int] = set()
    try:
        for exch in ("NFO", "BFO", "NSE", "BSE"):
            for inst in list(ws.kite_client.instruments_cached(exch, ttl_sec=getattr(conf, "KITE_INSTRUMENTS_TTL", 3600)) or []):
                try:
                    known.add(int(inst.get("instrument_token")))
                except Exception:
                    continue
    except Exception:
        pass
    return known


def build_subscription_tokens(symbols: list[str] | None, max_tokens: int | None = None) -> tuple[list[int], list[dict[str, Any]]]:
    ws = _ws_module()
    conf = _cfg(ws)
    symbols_l = [str(s).upper() for s in list(symbols or list(getattr(conf, "SYMBOLS", []) or []))]
    if max_tokens is None:
        max_tokens = _cfg_int(conf, "DEPTH_SUBSCRIPTION_MAX_TOKENS", 150)
    around_default = _cfg_int(conf, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", 6)
    around_by_symbol = dict(getattr(conf, "DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL", {}) or {})
    step_map = dict(getattr(conf, "STRIKE_STEP_BY_SYMBOL", {}) or {})
    min_option_tokens = max(1, _cfg_int(conf, "MIN_OPTION_TOKENS", 12))
    sticky = {int(t) for t in list(ws.get_sticky_tokens() or []) if int(t) > 0}

    tokens: list[int] = []
    resolution: list[dict[str, Any]] = []
    underlying_tokens: set[int] = set()
    underlying_map: dict[int, str] = {}
    token_to_symbol: dict[int, str] = {}
    option_rank: dict[int, tuple] = {}
    option_token_set: set[int] = set()

    for symbol in symbols_l:
        exchange = "BFO" if symbol == "SENSEX" else "NFO"
        step = float(step_map.get(symbol, getattr(conf, "STRIKE_STEP", 50)) or 50)
        around = int(around_by_symbol.get(symbol, around_default) or around_default)
        try:
            index_token = int(ws.kite_client.resolve_index_token(symbol) or 0) or None
        except Exception:
            index_token = None
        try:
            expiry = ws.kite_client.next_available_expiry(symbol, exchange=exchange)
        except Exception:
            expiry = None
        ltp, ltp_source = _underlying_ltp(ws, symbol, index_token)
        atm = _infer_atm(ltp, step)
        if atm is None and symbol in getattr(ws, "_LAST_ATM_BY_SYMBOL", {}):
            atm = int(ws._LAST_ATM_BY_SYMBOL[symbol])
            ltp_source = "fallback_last_atm"
        if atm is not None:
            ws._LAST_ATM_BY_SYMBOL[symbol] = int(atm)
        meta = _load_option_meta(ws, symbol, exchange, expiry) if expiry is not None else {}
        option_tokens: list[int] = []
        fail_reason = None
        option_coverage_status = "FULL"
        option_coverage_reason = "full_coverage"
        if expiry is None:
            fail_reason = "expiry_unavailable"
        elif atm is None:
            fail_reason = "atm_unavailable"
        else:
            try:
                raw = ws.kite_client.resolve_option_tokens_window(symbol=symbol, expiry=expiry, strikes_around=around, exchange=exchange, spot=ltp)
            except Exception:
                raw = []
            option_tokens = _dedupe_tokens(raw)
            desired = (around * 2 + 1) * 2
            if len(option_tokens) < desired and meta:
                candidates = sorted(meta, key=lambda t: _rank(meta.get(t), atm, step, t))
                for token in candidates:
                    if token not in set(option_tokens):
                        option_tokens.append(token)
                    if len(option_tokens) >= desired:
                        break
            option_tokens.sort(key=lambda t: _rank(meta.get(int(t)), atm, step, int(t)))
            if len(option_tokens) <= 0:
                fail_reason = "option_tokens_zero"
            elif len(option_tokens) < min_option_tokens:
                fail_reason = "option_tokens_under_min"
        if fail_reason:
            resolved_option_count = len(option_tokens)
            if fail_reason == "option_tokens_under_min" and resolved_option_count > 0:
                option_coverage_status = "DEGRADED"
                option_coverage_reason = "DEGRADED_OPTION_COVERAGE"
            elif resolved_option_count <= 0:
                option_coverage_status = "ZERO"
                option_coverage_reason = str(fail_reason)
            else:
                option_coverage_status = "FULL"
                option_coverage_reason = "full_coverage"
            try:
                ws._maybe_raise_option_token_incident(symbol=symbol, exchange=exchange, expiry=expiry, option_count=len(option_tokens), min_required=min_option_tokens, sample_tokens=option_tokens[:10], fail_reason=fail_reason)
            except Exception:
                pass
        else:
            resolved_option_count = len(option_tokens)
            option_coverage_status = "FULL"
            option_coverage_reason = "full_coverage"

        row_tokens: list[int] = []
        if index_token:
            row_tokens.append(index_token)
            underlying_tokens.add(index_token)
            underlying_map[index_token] = symbol
            token_to_symbol[index_token] = symbol
        selected_strikes: dict[float, set[str]] = {}
        for token in option_tokens:
            row_tokens.append(int(token))
            token_to_symbol[int(token)] = symbol
            option_token_set.add(int(token))
            option_rank[int(token)] = _rank(meta.get(int(token)), atm, step, int(token))
            m = meta.get(int(token)) or {}
            strike = _sf(m.get("strike"), None)
            typ = str(m.get("instrument_type") or "").upper()
            if strike is not None and typ in {"CE", "PE"}:
                selected_strikes.setdefault(float(strike), set()).add(typ)
        tokens.extend(row_tokens)
        resolution.append({
            "symbol": symbol,
            "exchange": exchange,
            "expiry": expiry,
            "ltp": ltp,
            "ltp_source": ltp_source,
            "atm": atm,
            "strikes_around": around,
            "step": step,
            "tokens": list(row_tokens),
            "count": len(row_tokens),
            "resolved_count": len(row_tokens),
            "option_count": len(option_tokens),
            "resolved_option_count": len(option_tokens),
            "final_option_count": len(option_tokens),
            "option_min_required": _option_min_required(ws, symbol, len(option_tokens)),
            "option_fail_reason": fail_reason,
            "option_coverage_status": option_coverage_status,
            "option_coverage_reason": option_coverage_reason,
            "option_strikes_selected": sorted(selected_strikes.keys()),
            "option_strike_count": len(selected_strikes),
            "option_two_sided_strike_count": sum(1 for legs in selected_strikes.values() if {"CE", "PE"}.issubset(legs)),
            "index_token": index_token,
            "index_token_source": "instruments" if index_token else "missing",
        })
    for token in sorted(sticky):
        tokens.append(token)
        token_to_symbol.setdefault(int(token), "STICKY")
    tokens = _dedupe_tokens(tokens)

    ws._UNDERLYING_TOKENS = set(underlying_tokens)
    ws._UNDERLYING_TOKEN_TO_SYMBOL = dict(underlying_map)
    ws._TOKEN_TO_SYMBOL = dict(token_to_symbol)
    ws._LAST_OPTION_COUNTS_BY_SYMBOL = {r["symbol"]: int(r.get("option_count") or 0) for r in resolution}
    ws._LAST_OPTION_MIN_REQUIRED_BY_SYMBOL = {r["symbol"]: int(r.get("option_min_required") or 0) for r in resolution}

    min_required = dict(ws._LAST_OPTION_MIN_REQUIRED_BY_SYMBOL)
    tokens, prune_meta = ws._prune_stale_option_subscription_tokens(tokens=tokens, option_rank_by_token=option_rank, token_to_symbol=token_to_symbol, min_required_by_symbol=min_required)

    if bool(getattr(conf, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", True)):
        known = _resolve_known_tokens(ws)
        if known:
            preserve = set(underlying_tokens) | set(sticky) | set(option_token_set)
            tokens = [t for t in tokens if t in known or t in preserve]

    tokens, truncated, _budget_meta = ws._enforce_subscription_budget(tokens, max_tokens=max_tokens, option_rank_by_token=option_rank, underlying_tokens=underlying_tokens, sticky_tokens=sticky, active_trade_tokens=sticky)
    try:
        observation_registry = ws.load_observation_registry(force=False)
    except Exception as exc:
        ws.reset_market_event_graph_observation_plan_state()
        try:
            ws._log_ws(
                "MARKET_EVENT_GRAPH_OBSERVATION_PLAN_BLOCKED",
                {"reason": f"registry_load_failed:{type(exc).__name__}:{exc}"},
            )
        except Exception:
            pass
        observation_registry = None
    if observation_registry is not None:
        observation_token_list = [int(token) for token in observation_registry.all_tokens]
        merge = ws.build_observation_subscription_merge(
            production_tokens=[int(token) for token in tokens],
            observation_tokens=observation_token_list,
            budget=max_tokens,
        )
        plan = {
            "ok": bool(merge.get("ok")),
            "verdict": (
                "PASS_LIVE_SOURCE_PRESESSION_READINESS"
                if bool(merge.get("ok"))
                else str(merge.get("reason") or ws.BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET)
            ),
            "production_tokens": [int(token) for token in tokens],
            "observation_tokens": observation_token_list,
            "final_union_tokens": [int(token) for token in list(merge.get("tokens") or [])],
            "missing_observation_tokens": [int(token) for token in list(merge.get("missing_or_pruned_observation_tokens") or [])],
            "configured_budget": max_tokens,
            "launch_plan_sha256": str(getattr(observation_registry, "canonical_sha256", "") or ""),
        }
        ws.activate_market_event_graph_launch_plan(plan)
        if bool(merge.get("ok")):
            tokens = [int(token) for token in list(merge.get("tokens") or [])]
            for symbol, token in dict(observation_registry.token_by_symbol).items():
                token_to_symbol[int(token)] = str(symbol).upper()
                ws._TOKEN_TO_SYMBOL[int(token)] = str(symbol).upper()
        else:
            try:
                ws._log_ws(
                    "MARKET_EVENT_GRAPH_OBSERVATION_PLAN_BLOCKED",
                    {
                        "reason": str(merge.get("reason") or ws.BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET),
                        "production_token_count": len(tokens),
                        "observation_token_count": len(observation_token_list),
                        "configured_budget": max_tokens,
                        "missing_observation_tokens": list(merge.get("missing_or_pruned_observation_tokens") or [])[:20],
                    },
                )
            except Exception:
                pass
    else:
        ws.reset_market_event_graph_observation_plan_state()

    final_by_symbol: dict[str, list[int]] = {}
    final_options: dict[str, int] = {}
    for token in tokens:
        symbol = str(token_to_symbol.get(int(token)) or "").upper()
        if not symbol or symbol == "STICKY":
            continue
        final_by_symbol.setdefault(symbol, []).append(int(token))
        if int(token) not in underlying_tokens:
            final_options[symbol] = final_options.get(symbol, 0) + 1
    for row in resolution:
        symbol = row["symbol"]
        row_tokens = list(final_by_symbol.get(symbol, []))
        final_option_count = int(final_options.get(symbol, 0))
        row["tokens"] = row_tokens if len(symbols_l) > 1 else list(tokens)
        row["count"] = len(row_tokens) if len(symbols_l) > 1 else len(tokens)
        row["final_count"] = row["count"]
        row["option_count"] = final_option_count
        row["final_option_count"] = final_option_count
        skipped = dict(prune_meta.get("session_tick_skipped_by_symbol") or {})
        row["stale_option_pruned_count"] = 0 if int(skipped.get(symbol, 0) or 0) else int((prune_meta.get("pruned_by_symbol") or {}).get(symbol, 0) or 0)
        row["stale_option_prune_enabled"] = bool(prune_meta.get("enabled"))
        row["stale_option_prune_max_age_sec"] = float(prune_meta.get("max_age_sec") or 0.0)
        row["stale_option_prune_require_session_tick"] = bool(prune_meta.get("require_session_tick"))
        row["stale_option_session_tick_skipped_count_by_symbol"] = skipped
        row["stale_option_pruned_sample_tokens"] = [] if int(skipped.get(symbol, 0) or 0) else [int(t) for t in list(prune_meta.get("pruned_tokens") or [])[:10]]
        if row.get("option_fail_reason"):
            row["option_drop_reason"] = row.get("option_fail_reason")
        elif final_option_count < int(row.get("resolved_option_count") or 0):
            row["option_drop_reason"] = "stale_option_subscription_pruned" if row["stale_option_pruned_count"] else ("subscription_budget_truncated" if truncated else "option_tokens_filtered")
        else:
            row["option_drop_reason"] = None
    ws._LAST_OPTION_COUNTS_BY_SYMBOL = {r["symbol"]: int(r.get("option_count") or 0) for r in resolution}
    ws._LAST_DESIRED_TOKENS = _normalize_positive_tokens(ws, tokens) or None
    return list(tokens), resolution


build_subscription_tokens._depth_rewrite_internal = True


def build_depth_subscription_tokens(symbols=None, max_tokens=None):
    ws = _ws_module()
    public_builder = getattr(ws, "build_subscription_tokens", None)
    if callable(public_builder) and public_builder is not build_subscription_tokens and not getattr(public_builder, "_depth_rewrite_internal", False):
        try:
            return public_builder(symbols=symbols, max_tokens=max_tokens)
        except TypeError:
            fallback = getattr(ws, "build_tokens", None)
            if callable(fallback):
                return fallback(symbols)
        except Exception:
            pass
    return build_subscription_tokens(symbols, max_tokens=max_tokens)


build_depth_subscription_tokens._depth_rewrite_internal = True


def _option_freshness_stats(ws: Any, tokens: list[int], now_epoch: float) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    conf = _cfg(ws)
    urgent = _cfg_float(conf, "FEED_STALE_OPTION_SUBSCRIPTION_URGENT_MAX_AGE_SEC", 8.0)
    by_symbol: dict[str, dict[str, Any]] = {}
    for token in _dedupe_tokens(tokens):
        if _is_underlying(ws, token):
            continue
        symbol = str((getattr(ws, "_TOKEN_TO_SYMBOL", {}) or {}).get(int(token)) or "").upper()
        if not symbol or symbol == "STICKY":
            continue
        stats = by_symbol.setdefault(symbol, {"option_count": 0, "fresh_count": 0, "stale_count": 0, "fresh_ratio": 1.0, "max_age_sec": 0.0, "urgent_max_age_sec": urgent, "stale_samples": []})
        is_fresh, age, db_epoch, memory_epoch = _classify_option_freshness(ws, token, now_epoch, urgent)
        stats["option_count"] += 1
        if is_fresh:
            stats["fresh_count"] += 1
        else:
            stats["stale_count"] += 1
            if len(stats["stale_samples"]) < 10:
                stats["stale_samples"].append({"token": token, "symbol": symbol, "age_sec": age, "db_epoch": db_epoch, "memory_epoch": memory_epoch})
        if age is not None:
            stats["max_age_sec"] = max(float(stats["max_age_sec"]), float(age))
        stats["fresh_ratio"] = stats["fresh_count"] / max(1, stats["option_count"])
    total_options = sum(int(v["option_count"]) for v in by_symbol.values())
    total_fresh = sum(int(v["fresh_count"]) for v in by_symbol.values())
    total_stale = sum(int(v["stale_count"]) for v in by_symbol.values())
    overall = {"option_count": total_options, "fresh_count": total_fresh, "stale_count": total_stale, "fresh_ratio": (total_fresh / total_options if total_options else 1.0), "max_age_sec": max([float(v.get("max_age_sec") or 0.0) for v in by_symbol.values()], default=0.0), "urgent_max_age_sec": urgent, "stale_samples": [s for v in by_symbol.values() for s in list(v.get("stale_samples") or [])][:10]}
    return by_symbol, overall


def _maybe_refresh_stale_option_subscription_universe(*, now_epoch: float, refresh_state: dict[str, float]) -> tuple[bool, dict[str, Any]]:
    ws = _ws_module()
    conf = _cfg(ws)
    if not bool(ws.is_market_open_ist()):
        return False, {"reason": "market_closed"}
    now = float(now_epoch)
    state = refresh_state if isinstance(refresh_state, dict) else {}
    current = _normalize_positive_tokens(ws, getattr(ws, "_LAST_TOKENS", []))
    symbols = sorted({str((getattr(ws, "_TOKEN_TO_SYMBOL", {}) or {}).get(int(t)) or "").upper() for t in current if str((getattr(ws, "_TOKEN_TO_SYMBOL", {}) or {}).get(int(t)) or "").strip()})
    if not symbols:
        symbols = [str(s).upper() for s in list(getattr(conf, "SYMBOLS", []) or []) if str(s).strip()]
    desired_raw, resolution = ws.build_subscription_tokens(symbols)
    desired = _normalize_positive_tokens(ws, desired_raw)
    current_set = set(current)
    desired_set = set(desired)
    # A freshness refresh is not the authority for destructive contract
    # rotation.  The live session has a fixed intended registry and the
    # resolver may legitimately prune/rotate rows while this watchdog pass is
    # running.  Unsubscribing that difference here can drop tokens from the
    # applied registry without updating the session's intended count, which
    # creates a permanent false subscription-truth blocker.  Controlled
    # rebalance owns removals; this path only restores missing desired tokens.
    subscribe = sorted(desired_set - current_set)
    unsubscribe: list[int] = []
    by_symbol, overall = _option_freshness_stats(ws, current, now)
    min_ratio = _cfg_float(conf, "FEED_STALE_OPTION_SUBSCRIPTION_MIN_FRESH_RATIO", 0.8)
    drift_sec = _cfg_float(conf, "FEED_STALE_OPTION_SUBSCRIPTION_DRIFT_REFRESH_SEC", 5.0)
    refresh_sec = _cfg_float(conf, "FEED_STALE_OPTION_SUBSCRIPTION_REFRESH_SEC", 20.0)
    stale_symbols = [sym for sym, stats in sorted(by_symbol.items()) if int(stats.get("option_count") or 0) > 0 and (float(stats.get("fresh_ratio") or 1.0) < min_ratio or float(stats.get("max_age_sec") or 0.0) > float(stats.get("urgent_max_age_sec") or 0.0))]
    freshness_urgent = bool(stale_symbols)
    resolution_tokens_by_symbol: dict[str, list[int]] = {}
    for row in list(resolution or []):
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        resolution_tokens_by_symbol[symbol] = _dedupe_tokens(row.get("tokens") or [])
    if freshness_urgent and (now - float(state.get("last_freshness_refresh_epoch") or 0.0)) >= drift_sec:
        refresh_tokens = []
        for symbol in stale_symbols:
            for token in resolution_tokens_by_symbol.get(symbol, []):
                if int(token) in current_set and not _is_underlying(ws, int(token)):
                    refresh_tokens.append(int(token))
        refresh_tokens = _dedupe_tokens(refresh_tokens)
        state["last_refresh_epoch"] = now
        state["last_freshness_refresh_epoch"] = now
        payload = {"reason": "freshness_drift", "refresh_mode": "symbol_freshness_refresh", "refresh_sec": refresh_sec, "drift_refresh_sec": drift_sec, "previous_count": len(current), "desired_count": len(desired), "subscribe_count": len(subscribe), "unsubscribe_count": 0, "refresh_token_count": len(refresh_tokens), "subscribe_tokens": [] if refresh_tokens else subscribe, "unsubscribe_tokens": [], "refresh_tokens": refresh_tokens, "refresh_applied": False, "force_resubscribe_current": False, "freshness_urgent": True, "freshness_urgent_symbols": stale_symbols, "freshness_by_symbol": by_symbol, **overall}
        return True, payload
    if desired == current:
        return False, {"reason": "no_delta", "refresh_mode": "delta", "refresh_sec": refresh_sec, "drift_refresh_sec": drift_sec, "previous_count": len(current), "desired_count": len(desired), "subscribe_count": 0, "unsubscribe_count": 0, "subscribe_tokens": [], "unsubscribe_tokens": [], "refresh_tokens": [], "refresh_applied": False, "force_resubscribe_current": False, "freshness_urgent": freshness_urgent, "freshness_urgent_symbols": stale_symbols, "freshness_by_symbol": by_symbol, **overall}
    if not freshness_urgent and (now - float(state.get("last_refresh_epoch") or 0.0)) < refresh_sec:
        return False, {"reason": "refresh_cooldown", "refresh_mode": "delta", "refresh_sec": refresh_sec, "drift_refresh_sec": drift_sec, "previous_count": len(current), "desired_count": len(desired), "subscribe_count": len(subscribe), "unsubscribe_count": 0, "subscribe_tokens": subscribe, "unsubscribe_tokens": [], "refresh_tokens": [], "refresh_applied": False, "force_resubscribe_current": False, "freshness_urgent": False, "freshness_urgent_symbols": stale_symbols, "freshness_by_symbol": by_symbol, **overall}
    state["last_refresh_epoch"] = now
    return bool(subscribe), {"reason": "delta_refresh", "refresh_mode": "delta", "refresh_sec": refresh_sec, "drift_refresh_sec": drift_sec, "previous_count": len(current), "desired_count": len(desired), "subscribe_count": len(subscribe), "unsubscribe_count": 0, "subscribe_tokens": subscribe, "unsubscribe_tokens": [], "refresh_tokens": [], "refresh_applied": False, "force_resubscribe_current": False, "freshness_urgent": freshness_urgent, "freshness_urgent_symbols": stale_symbols, "freshness_by_symbol": by_symbol, **overall}


def _patch_module(module: Any) -> None:
    if module is None:
        return
    module._prune_stale_option_subscription_tokens = _prune_stale_option_subscription_tokens
    module.build_subscription_tokens = build_subscription_tokens
    module.build_depth_subscription_tokens = build_depth_subscription_tokens
    module._maybe_refresh_stale_option_subscription_universe = _maybe_refresh_stale_option_subscription_universe


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    import core.kite_depth_ws as ws
    _patch_module(ws)
    _INSTALLED = True
