# Migration note:
# Freshness SLA now derives runtime mode from core.market_context and uses compute_age_sec.

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from config import config as cfg
from core.depth_store import depth_store
from core.fs_utils import ensure_parent_dir
from core.feed.artifact_loader import load_current_feed_runtime
from core.market_context import derive_market_context
from core.freshness_policy import resolve_freshness_policy
from core.tick_store import init_ticks as _init_ticks_schema
from core.tick_store import get_last_tick as _get_last_tick
from core.tick_store import last_tick_epoch as _last_tick_epoch
from core.tick_store import get_latest_tick_rows_db_no_flush as _get_latest_tick_rows_db
from core.tick_store import get_max_tick_epoch_db_no_flush as _get_max_tick_epoch_db
from core.time_utils import (
    compute_age_sec,
    is_market_open_ist,
    normalize_epoch_seconds,
    now_ist,
    now_utc_epoch,
)
from core.paths import logs_dir

LOG_PATH = logs_dir() / "freshness_sla.jsonl"
TOKEN_MAP_PATH = logs_dir() / "token_resolution.json"

_CACHE: Dict[str, Any] = {}


def _log_event(payload: Dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _load_token_map() -> Dict[str, List[int]]:
    if not TOKEN_MAP_PATH.exists():
        return {}
    try:
        data = json.loads(TOKEN_MAP_PATH.read_text())
    except Exception:
        return {}
    if isinstance(data, dict):
        return {k: list(v or []) for k, v in data.items()}
    if isinstance(data, list):
        out: Dict[str, List[int]] = {}
        for row in data:
            symbol = row.get("symbol")
            tokens = row.get("tokens") or []
            if symbol:
                out[symbol] = list(tokens)
        return out
    return {}


def _conn(db_path: Path) -> sqlite3.Connection:
    safe_path = ensure_parent_dir(Path(db_path))
    return sqlite3.connect(str(safe_path))


def _query_max_epoch(conn: sqlite3.Connection, table: str) -> Optional[float]:
    try:
        row = conn.execute(f"SELECT MAX(timestamp_epoch) FROM {table}").fetchone()
        if not row:
            return None
        return normalize_epoch_seconds(row[0])
    except Exception:
        return None


def _latest_depth_epoch_from_store() -> Optional[float]:
    latest = None
    for book in depth_store.books.values():
        ts = book.get("ts_epoch") or book.get("ts")
        ts_norm = normalize_epoch_seconds(ts)
        if ts_norm is None:
            continue
        if latest is None or ts_norm > latest:
            latest = ts_norm
    return latest


def _runtime_snapshot_epochs(symbol: str | None) -> dict[str, Any]:
    if not bool(getattr(cfg, "FEED_FRESHNESS_RUNTIME_SNAPSHOT_ENABLE", True)):
        return {}
    try:
        loaded = load_current_feed_runtime()
        snapshot = dict(loaded.get("payload") or {}) if loaded.get("valid") else None
    except Exception:
        snapshot = None
    if not isinstance(snapshot, dict):
        return {}
    symbol_norm = str(symbol).upper() if symbol else None
    ltp_epoch = normalize_epoch_seconds(snapshot.get("last_ws_tick_epoch"))
    depth_epoch = normalize_epoch_seconds(snapshot.get("last_depth_epoch"))
    if symbol_norm:
        by_symbol = snapshot.get("last_option_tick_ts_by_symbol")
        if isinstance(by_symbol, dict):
            symbol_epoch = normalize_epoch_seconds(by_symbol.get(symbol_norm))
            if symbol_epoch is not None:
                ltp_epoch = symbol_epoch
    # Pass through additional runtime feed evidence for callers that want to prefer
    # runtime freshness over SQLite lag (must never make execution less safe).
    opt_age_by_symbol = snapshot.get("option_last_tick_age_by_symbol")
    if not isinstance(opt_age_by_symbol, dict):
        opt_age_by_symbol = snapshot.get("last_option_tick_age_by_symbol")
    opt_reason_by_symbol = snapshot.get("option_feed_block_reason_by_symbol")
    return {
        "ltp_epoch": ltp_epoch,
        "depth_epoch": depth_epoch,
        "source": str(snapshot.get("source") or "feed_runtime_latest"),
        "runtime_state": str(snapshot.get("runtime_state") or "").strip().upper() or None,
        "ws_connected": snapshot.get("ws_connected"),
        "subscribed_tokens_count": snapshot.get("subscribed_tokens_count"),
        "last_option_tick_ts_by_symbol": snapshot.get("last_option_tick_ts_by_symbol"),
        "option_last_tick_age_by_symbol": opt_age_by_symbol,
        "option_feed_block_reason_by_symbol": opt_reason_by_symbol,
    }


def _depth_store_tokens() -> List[int]:
    tokens: List[int] = []
    for key in depth_store.books.keys():
        try:
            tokens.append(int(key))
        except Exception:
            continue
    return tokens


def _fallback_index_tokens() -> List[int]:
    tokens: List[int] = []
    try:
        mapping = getattr(cfg, "INDEX_TOKEN_BY_SYMBOL", {}) or {}
        for tok in mapping.values():
            try:
                tok_val = int(tok)
            except Exception:
                continue
            if tok_val > 0:
                tokens.append(tok_val)
    except Exception:
        return tokens
    return tokens


def _normalize_tokens(tokens: Sequence[int] | None) -> list[int]:
    out: list[int] = []
    for token in list(tokens or []):
        try:
            out.append(int(token))
        except Exception:
            continue
    return out


def _resolve_ltp_tokens(symbol: str | None, tokens: Sequence[int] | None) -> list[int]:
    explicit = _normalize_tokens(tokens)
    if explicit:
        return explicit

    # Global/unscoped freshness should never key off option subscription sets.
    # Options can be sparse even when the feed is healthy; use index tokens instead.
    if not symbol and bool(getattr(cfg, "FEED_FRESHNESS_UNSCOPED_INDEX_ONLY", True)):
        idx = _fallback_index_tokens()
        if idx:
            return idx

    token_map = _load_token_map()
    if symbol:
        mapped = _normalize_tokens(token_map.get(str(symbol).upper()) or [])
        if mapped:
            return mapped

    store_tokens = _depth_store_tokens()
    if store_tokens:
        return store_tokens

    if token_map:
        merged: list[int] = []
        seen: set[int] = set()
        for vals in token_map.values():
            for token in _normalize_tokens(vals):
                if token in seen:
                    continue
                seen.add(token)
                merged.append(token)
        if merged:
            return merged

    return _fallback_index_tokens()


def _ltp_metrics_from_db(
    *,
    tokens_for_ltp: Sequence[int],
    now_epoch: float,
    sla_threshold_sec: float,
) -> dict[str, Any]:
    prefer_memory = bool(getattr(cfg, "FEED_FRESHNESS_PREFER_TICKSTORE_MEMORY", True))
    token_list = _normalize_tokens(tokens_for_ltp)
    if token_list:
        latest_epoch = None
        token_ages: dict[int, float] = {}
        stale_tokens: list[int] = []

        # First choice: in-memory tick cache (never blocks on SQLite contention).
        if prefer_memory:
            for token in token_list:
                tick = _get_last_tick(token, allow_db=False)
                ts_epoch = normalize_epoch_seconds((tick or {}).get("ts_epoch")) if isinstance(tick, dict) else None
                age_sec = compute_age_sec(ts_epoch, now_epoch) if ts_epoch is not None else None
                if age_sec is not None:
                    token_ages[token] = age_sec
                if ts_epoch is not None and (latest_epoch is None or ts_epoch > latest_epoch):
                    latest_epoch = ts_epoch
                if age_sec is None or age_sec > sla_threshold_sec:
                    stale_tokens.append(token)

            # If we observed any memory evidence, do not touch SQLite at all.
            if token_ages or latest_epoch is not None:
                max_tick_age_sec = max(token_ages.values()) if token_ages else (
                    compute_age_sec(latest_epoch, now_epoch) if latest_epoch is not None else None
                )
                return {
                    "last_epoch": latest_epoch,
                    "source": "ticks_memory",
                    "stale_tokens": stale_tokens,
                    "max_tick_age_sec": max_tick_age_sec,
                    "tracked_tokens": token_list,
                }

        # Fallback: SQLite, but never force a flush boundary (avoid blocking).
        rows = _get_latest_tick_rows_db(token_list)
        for token in token_list:
            row = rows.get(token) or {}
            ts_epoch = normalize_epoch_seconds((row or {}).get("ts_epoch"))
            age_sec = compute_age_sec(ts_epoch, now_epoch) if ts_epoch is not None else None
            if age_sec is not None:
                token_ages[token] = age_sec
            if ts_epoch is not None and (latest_epoch is None or ts_epoch > latest_epoch):
                latest_epoch = ts_epoch
            if age_sec is None or age_sec > sla_threshold_sec:
                stale_tokens.append(token)
        if latest_epoch is None:
            latest_epoch = _get_max_tick_epoch_db()
        max_tick_age_sec = (
            max(token_ages.values())
            if token_ages
            else (compute_age_sec(latest_epoch, now_epoch) if latest_epoch is not None else None)
        )
        return {
            "last_epoch": latest_epoch,
            "source": "ticks_db_filtered_no_flush" if rows else ("ticks_db_any_no_flush" if latest_epoch is not None else "none"),
            "stale_tokens": stale_tokens,
            "max_tick_age_sec": max_tick_age_sec,
            "tracked_tokens": token_list,
        }

    latest_epoch = None
    if prefer_memory:
        latest_epoch = normalize_epoch_seconds(_last_tick_epoch())
    if latest_epoch is None:
        latest_epoch = _get_max_tick_epoch_db()
    max_tick_age_sec = compute_age_sec(latest_epoch, now_epoch) if latest_epoch is not None else None
    return {
        "last_epoch": latest_epoch,
        "source": ("ticks_memory" if prefer_memory else "ticks_db_any_no_flush") if latest_epoch is not None else "none",
        "stale_tokens": [],
        "max_tick_age_sec": max_tick_age_sec,
        "tracked_tokens": [],
    }


def get_freshness_status(
    symbol: str | None = None,
    tokens: Sequence[int] | None = None,
    force: bool = False,
) -> Dict[str, Any]:
    if isinstance(symbol, bool) and tokens is None and force is False:
        # Backward compatibility for accidental positional usage: get_freshness_status(True)
        force = bool(symbol)
        symbol = None

    now_epoch = float(now_utc_epoch())
    symbol_norm = str(symbol).upper() if symbol else None
    scoped = symbol_norm is not None or bool(tokens)
    ttl_sec = float(getattr(cfg, "FEED_FRESHNESS_TTL_SEC", 5.0))
    if (not scoped) and (not force) and _CACHE.get("ts_epoch") and (now_epoch - float(_CACHE["ts_epoch"])) <= ttl_sec:
        return dict(_CACHE["payload"])

    market_ctx = derive_market_context(
        {
            "execution_mode": str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
            "market_open": bool(is_market_open_ist()),
        }
    )
    market_open = bool(market_ctx.is_market_open)
    offhours_mode = bool(market_ctx.mode == "OFFHOURS")
    allow_stale_quotes = bool(market_ctx.allow_stale_quotes)
    exec_mode = str(market_ctx.mode)
    policy = resolve_freshness_policy(
        mode=exec_mode,
        market_open=bool(market_open),
        allow_stale_quotes=bool(allow_stale_quotes),
        live_ltp_sec=float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5)),
        live_depth_sec=float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 6.0)),
        planning_ltp_sec=float(getattr(cfg, "OFFHOURS_SLA_MAX_LTP_AGE_SEC", 900.0)),
        planning_depth_sec=float(getattr(cfg, "OFFHOURS_SLA_MAX_DEPTH_AGE_SEC", 900.0)),
        option_ok_live_sec=float(getattr(cfg, "FEED_HEALTH_OPTION_OK_AGE_SEC", 2.5)),
        option_ok_planning_sec=float(getattr(cfg, "OFFHOURS_SLA_MAX_LTP_AGE_SEC", 900.0)),
        expiry_lotto_mode=bool(getattr(cfg, "EXPIRY_LOTTO_MODE", False)),
    )
    max_ltp_age = float(policy.ltp_max_age_sec)
    max_depth_age = float(policy.depth_max_age_sec)
    depth_required = bool(policy.depth_required and getattr(cfg, "SLA_REQUIRE_OPTIONS_DEPTH_LIVE", True))

    ltp_last_epoch = None
    depth_last_epoch = None
    ltp_source = "none"
    depth_source = "none"
    data_available = False
    stale_tokens: list[int] = []
    max_tick_age_sec = None

    tokens_for_ltp = _resolve_ltp_tokens(symbol_norm, tokens)

    # Index LTP ticks can be bursty (especially around open/halts). Treat index freshness
    # separately from option-token freshness so we don't trip FEED_LTP_STALE on normal gaps.
    #
    # Apply this only when we are effectively evaluating index freshness:
    # - symbol-scoped checks (symbol provided, tokens not provided), or
    # - unscoped checks where token resolution falls back to a tiny index-token set (not an option universe)
    try:
        idx_sla = getattr(cfg, "SLA_MAX_INDEX_LTP_AGE_SEC", None)
        if idx_sla is not None:
            is_symbol_scoped_index = bool(symbol_norm and not tokens)
            is_unscoped_index_fallback = bool(
                symbol_norm is None
                and tokens is None
                and tokens_for_ltp
                and len(tokens_for_ltp) <= int(getattr(cfg, "FEED_FRESHNESS_INDEX_TOKEN_MAX_COUNT", 5))
            )
            if is_symbol_scoped_index or is_unscoped_index_fallback:
                max_ltp_age = max(max_ltp_age, float(idx_sla))
    except Exception:
        pass

    ltp_metrics = _ltp_metrics_from_db(
        tokens_for_ltp=tokens_for_ltp,
        now_epoch=now_epoch,
        sla_threshold_sec=max_ltp_age,
    )
    ltp_last_epoch = normalize_epoch_seconds(ltp_metrics.get("last_epoch"))
    ltp_source = str(ltp_metrics.get("source") or "none")
    stale_tokens = [int(t) for t in list(ltp_metrics.get("stale_tokens") or [])]
    max_tick_age_sec = (
        float(ltp_metrics.get("max_tick_age_sec"))
    if ltp_metrics.get("max_tick_age_sec") is not None
        else None
    )

    db_path = Path(cfg.TRADE_DB_PATH)
    if db_path.exists():
        try:
            _init_ticks_schema()
        except Exception:
            pass
        try:
            with _conn(db_path) as conn:
                depth_last_epoch = _query_max_epoch(conn, "depth_snapshots")
                if depth_last_epoch is not None:
                    depth_source = "depth_snapshots"
        except Exception:
            depth_last_epoch = None

    depth_store_epoch = _latest_depth_epoch_from_store()
    if depth_store_epoch is not None:
        depth_last_epoch = max(depth_last_epoch or 0.0, depth_store_epoch)
        depth_source = "depth_store"

    runtime_snapshot = _runtime_snapshot_epochs(symbol_norm)
    runtime_ltp_epoch = normalize_epoch_seconds(runtime_snapshot.get("ltp_epoch"))
    runtime_depth_epoch = normalize_epoch_seconds(runtime_snapshot.get("depth_epoch"))
    runtime_snapshot_used = False
    runtime_ltp_used = False
    if runtime_ltp_epoch is not None and (ltp_last_epoch is None or runtime_ltp_epoch > ltp_last_epoch):
        ltp_last_epoch = runtime_ltp_epoch
        ltp_source = str(runtime_snapshot.get("source") or "feed_runtime_latest")
        runtime_snapshot_used = True
        runtime_ltp_used = True
    if runtime_depth_epoch is not None and (depth_last_epoch is None or runtime_depth_epoch > depth_last_epoch):
        depth_last_epoch = runtime_depth_epoch
        depth_source = str(runtime_snapshot.get("source") or "feed_runtime_latest")
        runtime_snapshot_used = True

    if ltp_last_epoch is not None:
        data_available = True

    ltp_age = compute_age_sec(ltp_last_epoch, now_epoch) if ltp_last_epoch is not None else None
    depth_age = compute_age_sec(depth_last_epoch, now_epoch) if depth_last_epoch is not None else None

    reasons: List[str] = []
    runtime_option_freshness_applied = False
    runtime_option_stale_symbols: list[str] = []

    ltp_ok = ltp_age is not None and ltp_age <= max_ltp_age
    depth_ok = depth_age is not None and depth_age <= max_depth_age

    no_ticks_yet = ltp_last_epoch is None
    stale_ratio = (
        (float(len(stale_tokens)) / float(len(tokens_for_ltp)))
        if stale_tokens and tokens_for_ltp
        else 0.0
    )
    # Preserve the DB-derived ratio for observability even if we later prefer runtime freshness.
    db_stale_ratio = float(stale_ratio)
    stale_ratio_source = "db"
    max_stale_ratio = float(getattr(cfg, "FEED_FRESHNESS_MAX_STALE_TOKEN_RATIO", 0.5))
    stale_min_count = int(getattr(cfg, "FEED_FRESHNESS_STALE_TOKEN_MIN_COUNT", 5))
    stale_tokens_violation = bool(
        stale_tokens
        and tokens_for_ltp
        and len(stale_tokens) >= stale_min_count
        and stale_ratio > max_stale_ratio
    )

    if market_open and (not allow_stale_quotes):
        # Prefer runtime option freshness evidence over SQLite stale-token ratios when:
        # - we are doing a global/unscoped check (no symbol and no explicit token list)
        # - runtime says per-symbol option feed is OK and fresh
        #
        # This avoids false halts when SQLite lags in-memory ticks, while still failing closed if runtime
        # itself reports staleness/block reasons.
        try:
            opt_age_by_symbol = runtime_snapshot.get("option_last_tick_age_by_symbol")
            opt_reason_by_symbol = runtime_snapshot.get("option_feed_block_reason_by_symbol")
            if (
                symbol_norm is None
                and tokens is None
                and isinstance(opt_age_by_symbol, dict)
                and isinstance(opt_reason_by_symbol, dict)
                and opt_age_by_symbol
            ):
                option_ok_age = float(getattr(policy, "option_ok_age_sec", getattr(cfg, "FEED_HEALTH_OPTION_OK_AGE_SEC", 2.5)))
                for sym, age in opt_age_by_symbol.items():
                    sym_u = str(sym or "").upper() or "UNKNOWN"
                    reason = str((opt_reason_by_symbol or {}).get(sym_u) or "").upper() or "UNKNOWN"
                    age_val = float(age) if age is not None else float("inf")
                    if reason not in {"OK"} or age_val > option_ok_age:
                        runtime_option_stale_symbols.append(sym_u)
                if not runtime_option_stale_symbols:
                    stale_tokens_violation = False
                    runtime_option_freshness_applied = True
                    # SQLite lag is not actionable when runtime says option ticks are fresh.
                    stale_tokens = []
                    stale_ratio = 0.0
                    stale_ratio_source = "runtime_option_ages"
        except Exception:
            pass

        if no_ticks_yet:
            reasons.append("no_ticks_yet")
        elif stale_tokens_violation:
            reasons.append(
                f"ltp_stale_tokens:{len(stale_tokens)}/{len(tokens_for_ltp)}"
            )
        elif ltp_age > max_ltp_age:
            # When symbol is None (unscoped checks), token resolution typically falls back to the
            # primary index token; keep the reason stable and human-readable.
            reasons.append(f"ltp_stale:{symbol_norm or 'NIFTY'} age={ltp_age:.2f} max={max_ltp_age:.2f}")

        if depth_required:
            if depth_age is None:
                reasons.append("depth_missing")
            elif depth_age > max_depth_age:
                reasons.append(f"depth_stale age={depth_age:.2f} max={max_depth_age:.2f}")

    if runtime_ltp_used:
        stale_tokens = []

    if allow_stale_quotes:
        if market_open and no_ticks_yet:
            state = "IDLE"
        else:
            state = "OFFHOURS" if offhours_mode else "PLANNING"
        ok = True
    elif not market_open:
        state = "MARKET_CLOSED"
        ok = True
    else:
        if no_ticks_yet:
            state = "STALE"
            ok = False
        elif depth_required:
            if ltp_ok and depth_ok:
                state = "OK"
            elif ltp_ok or depth_ok:
                state = "DEGRADED"
            else:
                state = "STALE"
            ok = state == "OK"
        else:
            if ltp_ok:
                state = "OK"
                # Optional depth signal still visible without blocking.
                if depth_age is not None and depth_age > max_depth_age:
                    state = "DEGRADED"
            else:
                state = "STALE"
            ok = ltp_ok

    payload = {
        "ok": ok,
        "state": state,
        "mode": exec_mode,
        "policy_profile": policy.name,
        "symbol": symbol_norm,
        "market_open": market_open,
        "offhours_mode": bool(offhours_mode),
        "allow_stale_quotes": bool(allow_stale_quotes),
        "data_available": bool(data_available),
        "ts_epoch": now_epoch,
        "sla_threshold_sec": max_ltp_age,
        "max_tick_age_sec": max_tick_age_sec,
        "stale_tokens": stale_tokens,
        "tracked_tokens": tokens_for_ltp,
        "stale_token_ratio": stale_ratio,
        "db_stale_token_ratio": db_stale_ratio,
        "stale_token_ratio_source": stale_ratio_source,
        "max_stale_token_ratio": max_stale_ratio,
        "stale_token_min_count": stale_min_count,
        "runtime_option_freshness_applied": bool(runtime_option_freshness_applied),
        "runtime_option_stale_symbols": list(runtime_option_stale_symbols),
        "ltp": {
            "ok": ltp_ok if market_open else True,
            "age_sec": ltp_age,
            "max_age_sec": max_ltp_age,
            "required": bool(policy.ltp_required),
            "symbol": symbol_norm or "NIFTY",
            "source": ltp_source,
            "stale_tokens_count": len(stale_tokens),
        },
        "depth": {
            "ok": depth_ok if (market_open and depth_required) else True,
            "age_sec": depth_age,
            "max_age_sec": max_depth_age,
            "scope": "options",
            "source": depth_source,
            "required": bool(market_open and depth_required),
        },
        "reasons": reasons,
    }
    if runtime_snapshot_used and ltp_last_epoch is not None:
        payload["ltp"]["source"] = ltp_source
        if runtime_depth_epoch is not None:
            payload["depth"]["source"] = depth_source
    # Do not fail closed just because some tracked tokens are sparse; fail only when staleness is widespread.
    if market_open and (not allow_stale_quotes) and stale_tokens_violation:
        payload["ok"] = False
        if payload.get("state") == "OK":
            payload["state"] = "DEGRADED"
    payload["ok"] = bool(payload.get("ok"))

    if not scoped:
        _CACHE["ts_epoch"] = now_epoch
        _CACHE["payload"] = payload

    _log_event(
        {
            "ts_epoch": now_epoch,
            "ts_ist": now_ist().isoformat(),
            "state": state,
            "ok": ok,
            "market_open": market_open,
            "offhours_mode": bool(offhours_mode),
            "reasons": reasons,
            "ltp_age_sec": ltp_age,
            "depth_age_sec": depth_age,
            "ltp_source": ltp_source,
            "depth_source": depth_source,
            "runtime_snapshot_used": runtime_snapshot_used,
            "stale_tokens_count": len(stale_tokens),
            "tracked_tokens_count": len(tokens_for_ltp),
        }
    )

    return payload


def _reset_cache_for_tests() -> None:
    _CACHE.clear()
    from core import tick_store
    tick_store._LAST_TICK_BY_TOKEN.clear()
    tick_store._tick_window.clear()
