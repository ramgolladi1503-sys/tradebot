from config import config as cfg
import time
import threading
import json
import re
import atexit
import os
from pathlib import Path
from core.kite_client import kite_client
from core.depth_store import depth_store
from core.tick_store import insert_tick, record_tick_epoch
from core.time_utils import is_market_open_ist, now_utc_epoch, now_ist
from core.auth_health import get_kite_auth_health
from core.feed_restart_guard import feed_restart_guard
from core.feed_circuit_breaker import is_tripped as feed_breaker_tripped, trip as trip_feed_breaker
from core import risk_halt
from core.paths import repo_root, logs_dir
from core.log_writer import get_jsonl_writer
from core.run_lock import RunLock
from core.security_guard import resolve_kite_access_token

try:
    from kiteconnect import KiteTicker
except Exception:
    KiteTicker = None

_KITE_TICKER = None
_KITE_TICKER_LOCK = threading.Lock()
_WATCHDOG_THREAD = None
_WATCHDOG_STOP = None
_LAST_TOKENS = []
_UNDERLYING_TOKENS: set[int] = set()
_UNDERLYING_LOGGED_MISSING = False
_RESTART_LOCK = threading.Lock()
_LAST_FULL_RESTART_EPOCH = 0.0
_FULL_RESTARTS = []
_STALE_STRIKES = 0
_WARMUP_PENDING = False
_LOG_PATH = logs_dir() / "depth_ws_watchdog.log"
_LOG_WRITER = get_jsonl_writer(_LOG_PATH)
_DEPTH_WS_LOCK: RunLock | None = None
_DEPTH_WS_LOCK_ACQUIRED = False
_STOP_REQUESTED = False


def build_depth_subscription_tokens(symbols=None, max_tokens=None):
    """Return instrument tokens to subscribe on WS. Compatibility shim."""
    # try to reuse related helpers
    for name in ("build_subscription_tokens", "build_tokens", "select_tokens"):
        fn = globals().get(name)
        if callable(fn):
            try:
                return fn(symbols=symbols, max_tokens=max_tokens)
            except TypeError:
                return fn()
    return []


def _log_ws(event: str, extra: dict | None = None):
    try:
        payload = {
            "ts_epoch": now_utc_epoch(),
            "ts_ist": now_ist().isoformat(),
            "event": event,
        }
        if extra:
            payload.update(extra)
        if not _LOG_WRITER.write(payload):
            print(f"[DEPTH_WS_LOG_ERROR] failed to log path={_LOG_PATH} err=write_failed")
    except Exception as exc:
        print(f"[DEPTH_WS_LOG_ERROR] failed to log path={_LOG_PATH} err={type(exc).__name__}:{exc}")


def _masked_secret_stats(label: str, secret: str | None) -> dict:
    value = str(secret or "")
    return {
        f"{label}_len": len(value),
        f"{label}_tail4": value[-4:] if len(value) >= 4 else value,
        f"{label}_has_whitespace": bool(re.search(r"\s", value)),
    }


def _infer_atm_strike(ltp: float | None, step: float | None) -> int | None:
    if ltp is None or step is None or step <= 0:
        return None
    try:
        return int(round(float(ltp) / float(step)) * float(step))
    except Exception:
        return None


def _underlying_ltp(symbol: str) -> float | None:
    mapping = getattr(cfg, "PREMARKET_INDICES_LTP", {}) or {}
    ltp_symbol = mapping.get(symbol.upper())
    if not ltp_symbol:
        return None
    try:
        quotes = kite_client.ltp([ltp_symbol]) or {}
        val = quotes.get(ltp_symbol, {}).get("last_price")
        if val is not None:
            return float(val)
    except Exception:
        return None
    return None


def build_subscription_tokens(symbols: list[str], max_tokens: int | None = None) -> tuple[list[int], list[dict]]:
    global _UNDERLYING_TOKENS, _UNDERLYING_LOGGED_MISSING
    tokens: list[int] = []
    resolution: list[dict] = []
    underlying_tokens: list[int] = []
    if max_tokens is None:
        max_tokens = int(getattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", 150))
    strikes_around_default = int(getattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", 10))
    strikes_by_symbol = getattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL", {}) or {}
    step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {}) or {}
    validate_tokens = bool(getattr(cfg, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", True))

    for sym in symbols:
        sym_upper = str(sym).upper()
        exchange = "BFO" if sym_upper == "SENSEX" else "NFO"
        expiry = kite_client.next_available_expiry(sym, exchange=exchange)
        step = float(step_map.get(sym_upper, getattr(cfg, "STRIKE_STEP", 50)))
        strikes_around = int(strikes_by_symbol.get(sym_upper, strikes_around_default))
        ltp = _underlying_ltp(sym_upper)
        ltp_source = "live"
        if ltp is None:
            fallback = (getattr(cfg, "PREMARKET_INDICES_CLOSE", {}) or {}).get(sym_upper)
            if fallback:
                ltp = float(fallback)
                ltp_source = "fallback_close"
        atm = _infer_atm_strike(ltp, step)

        option_tokens: list[int] = []
        if expiry and atm is not None:
            option_tokens = kite_client.resolve_option_tokens_window(
                sym,
                expiry,
                atm,
                strikes_around,
                step,
                exchange=exchange,
            )

        index_token = kite_client.resolve_index_token(sym_upper)
        index_source = "instruments"
        if not index_token:
            mapping = getattr(cfg, "INDEX_TOKEN_BY_SYMBOL", {}) or {}
            fallback_token = int(mapping.get(sym_upper, 0) or 0)
            if fallback_token > 0:
                index_token = fallback_token
                index_source = "config"
        per_tokens = set(option_tokens)
        if index_token:
            per_tokens.add(index_token)
            underlying_tokens.append(int(index_token))

        tokens.extend(list(per_tokens))
        resolution.append(
            {
                "symbol": sym_upper,
                "exchange": exchange,
                "expiry": expiry,
                "ltp": ltp,
                "ltp_source": ltp_source,
                "atm": atm,
                "strikes_around": strikes_around,
                "step": step,
                "tokens": list(per_tokens),
                "count": len(per_tokens),
                "index_token": index_token,
                "index_token_source": index_source if index_token else "missing",
            }
        )

    tokens = list(dict.fromkeys(tokens))
    _UNDERLYING_TOKENS = set(int(t) for t in underlying_tokens if t is not None)
    _UNDERLYING_LOGGED_MISSING = False

    if validate_tokens:
        known_tokens: set[int] = set()
        try:
            for exch in ("NFO", "BFO", "NSE", "BSE"):
                for inst in kite_client.instruments_cached(exch, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600)):
                    tok = inst.get("instrument_token")
                    if tok is not None:
                        try:
                            known_tokens.add(int(tok))
                        except Exception:
                            continue
        except Exception:
            known_tokens = set()
        if known_tokens:
            before = len(tokens)
            tokens = [t for t in tokens if int(t) in known_tokens]
            dropped = before - len(tokens)
            if dropped > 0:
                _log_ws("FEED_TOKEN_FILTERED", {"dropped": dropped, "kept": len(tokens)})
    truncated = False
    if max_tokens and len(tokens) > max_tokens:
        tokens = tokens[:max_tokens]
        truncated = True

    try:
        out = logs_dir() / "token_resolution.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(resolution, indent=2, default=str))
    except Exception:
        pass

    _log_ws(
        "FEED_TOKEN_SELECTION",
        {
            "total_tokens": len(tokens),
            "max_tokens": max_tokens,
            "truncated": truncated,
            "per_symbol": {r["symbol"]: r.get("count", 0) for r in resolution},
            "underlying_tokens": list(_UNDERLYING_TOKENS),
            "sample_tokens": tokens[:10],
        },
    )
    return tokens, resolution


def _ensure_depth_ws_lock() -> bool:
    global _DEPTH_WS_LOCK, _DEPTH_WS_LOCK_ACQUIRED
    if _DEPTH_WS_LOCK_ACQUIRED:
        return True
    _DEPTH_WS_LOCK = RunLock(
        name=getattr(cfg, "DEPTH_WS_LOCK_NAME", "depth_ws.lock"),
        max_age_sec=getattr(cfg, "DEPTH_WS_LOCK_MAX_AGE_SEC", 3600),
    )
    ok, reason = _DEPTH_WS_LOCK.acquire()
    if not ok:
        state = _DEPTH_WS_LOCK.state_dict()
        _log_ws("FEED_LOCK_BLOCKED", {"reason": reason, "state": state})
        print(f"[DEPTH_WS_LOCK] {reason} state={state}")
        return False
    _DEPTH_WS_LOCK_ACQUIRED = True
    atexit.register(_DEPTH_WS_LOCK.release)
    return True


def _close_ticker_instance(instance):
    if instance is None:
        return
    for method_name in ("close", "stop", "disconnect"):
        method = getattr(instance, method_name, None)
        if callable(method):
            try:
                method()
            except Exception as exc:
                _log_ws("FEED_CLOSE_ERROR", {"method": method_name, "error": str(exc)})


def stop_depth_ws(reason: str = "manual_stop"):
    """
    Stop watchdog and close existing KiteTicker instance.
    """
    global _KITE_TICKER, _WATCHDOG_STOP, _WATCHDOG_THREAD, _STALE_STRIKES, _STOP_REQUESTED
    with _KITE_TICKER_LOCK:
        _STOP_REQUESTED = True
        _log_ws("FEED_STOP", {"reason": reason})
        if _WATCHDOG_STOP is not None:
            _WATCHDOG_STOP.set()
        _STALE_STRIKES = 0
        _close_ticker_instance(_KITE_TICKER)
        _KITE_TICKER = None
    _WATCHDOG_THREAD = None


def restart_depth_ws(reason: str = "unknown"):
    """
    Full restart: close existing ticker and recreate with last known tokens.
    Rate-limited to avoid restart storms.
    """
    global _LAST_FULL_RESTART_EPOCH, _FULL_RESTARTS, _STALE_STRIKES

    tokens = list(_LAST_TOKENS or [])
    if not tokens:
        _log_ws("FEED_RESTART_SKIPPED", {"reason": reason, "detail": "no_tokens_cached"})
        return False

    now = time.time()
    cooldown = float(getattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 120))
    max_per_hour = int(getattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6))
    storm_trip = int(getattr(cfg, "FEED_RESTART_STORM_TRIP", max_per_hour))

    with _RESTART_LOCK:
        if feed_breaker_tripped():
            _log_ws("FEED_RESTART_BLOCKED_BY_BREAKER", {"reason": reason})
            return False
        if not feed_restart_guard.allow_restart(now=now, reason=reason):
            _log_ws("FEED_RESTART_BREAKER_BLOCK", {"reason": reason})
            return False
        _FULL_RESTARTS = [ts for ts in _FULL_RESTARTS if (now - ts) <= 3600.0]

        if len(_FULL_RESTARTS) >= storm_trip:
            try:
                trip_feed_breaker(
                    reason="feed_restart_storm",
                    meta={"count": len(_FULL_RESTARTS), "window_sec": 3600.0, "reason": reason},
                )
            except Exception:
                pass
            try:
                risk_halt.trigger("feed_restart_storm")
            except Exception:
                pass
            _log_ws(
                "FEED_RESTART_STORM_TRIP",
                {"reason": reason, "count": len(_FULL_RESTARTS), "window_sec": 3600.0},
            )
            return False

        if (now - _LAST_FULL_RESTART_EPOCH) < cooldown:
            next_allowed = _LAST_FULL_RESTART_EPOCH + cooldown
            _log_ws(
                "FEED_RESTART_RATE_LIMIT_COOLDOWN",
                {"reason": reason, "cooldown_sec": cooldown, "next_allowed_epoch": next_allowed},
            )
            return False

        if len(_FULL_RESTARTS) >= max_per_hour:
            oldest = min(_FULL_RESTARTS)
            next_allowed = oldest + 3600.0
            _log_ws(
                "FEED_RESTART_RATE_LIMIT_HOURLY",
                {"reason": reason, "max_per_hour": max_per_hour, "next_allowed_epoch": next_allowed},
            )
            return False

        _log_ws("FEED_FULL_RESTART_BEGIN", {"reason": reason, "tokens": len(tokens)})
        stop_depth_ws(reason=f"restart:{reason}")
        try:
            start_depth_ws(tokens, profile_verified=False, skip_guard=True)
        except Exception as exc:
            _log_ws("FEED_FULL_RESTART_FAILED", {"reason": reason, "error": str(exc)})
            return False

        _LAST_FULL_RESTART_EPOCH = now
        _FULL_RESTARTS.append(now)
        _STALE_STRIKES = 0
        _log_ws("FEED_FULL_RESTART_OK", {"reason": reason, "tokens": len(tokens)})
        return True


def start_depth_ws(instrument_tokens, profile_verified=False, skip_lock: bool = False, skip_guard: bool = False):
    global _KITE_TICKER, _WATCHDOG_THREAD, _WATCHDOG_STOP, _LAST_TOKENS, _STALE_STRIKES, _WARMUP_PENDING, _STOP_REQUESTED
    if not skip_lock:
        if not _ensure_depth_ws_lock():
            return
    if not skip_guard and getattr(cfg, "DEPTH_WS_SINGLETON", True):
        with _KITE_TICKER_LOCK:
            if _KITE_TICKER is not None:
                _log_ws(
                    "FEED_START_SUPPRESSED",
                    {"reason": "already_running", "tokens": len(_LAST_TOKENS or [])},
                )
                return
    if not KiteTicker or not cfg.KITE_USE_DEPTH:
        print("Depth websocket not available.")
        return
    if not cfg.KITE_API_KEY:
        print("Missing Kite API key.")
        return
    try:
        cwd = Path.cwd()
        root = repo_root()
        log_dir = logs_dir()
        print(f"[KITE_WS][PATHS] cwd={cwd} repo_root={root} logs_dir={log_dir} log_path={_LOG_PATH}")
        _log_ws(
            "FEED_PATHS",
            {"cwd": str(cwd), "repo_root": str(root), "logs_dir": str(log_dir), "log_path": str(_LOG_PATH)},
        )
    except Exception as exc:
        print(f"[KITE_WS][PATHS_ERROR] {type(exc).__name__}:{exc}")
    auth_payload = get_kite_auth_health(force=True)
    if not auth_payload.get("ok"):
        err = auth_payload.get("error") or "unknown_auth_error"
        _log_ws("FEED_AUTH_BLOCKED", {"error": err})
        print(f"Missing/invalid Kite access token: {err}")
        return
    try:
        access_token = str(
            resolve_kite_access_token(repo_root=repo_root(), require_token=True)
            or ""
        ).strip()
    except Exception as exc:
        _log_ws("FEED_AUTH_BLOCKED", {"error": f"token_resolve_failed:{type(exc).__name__}:{exc}"})
        print(f"Missing/invalid Kite access token: token_resolve_failed:{exc}")
        return
    if not access_token:
        _log_ws("FEED_AUTH_BLOCKED", {"error": "missing_access_token:empty"})
        print("Missing/invalid Kite access token: empty")
        return
    os.environ["KITE_ACCESS_TOKEN"] = access_token

    tokens = list(dict.fromkeys(instrument_tokens or []))
    if not tokens:
        print("No instrument tokens provided for depth websocket.")
        return
    _LAST_TOKENS = list(tokens)
    _STALE_STRIKES = 0
    _WARMUP_PENDING = True
    _STOP_REQUESTED = False

    computed_profile_verified = False
    profile_error = ""
    try:
        ensure_fn = getattr(kite_client, "_ensure", None) or getattr(kite_client, "ensure", None)
        if callable(ensure_fn):
            ensure_fn()
        rest_client = getattr(kite_client, "kite", None)
        if rest_client is not None:
            try:
                rest_client.set_access_token(access_token)
            except Exception:
                pass
            profile = rest_client.profile() or {}
            user_id = str(profile.get("user_id") or "").strip()
            if user_id:
                computed_profile_verified = True
                _log_ws("FEED_AUTH_PROFILE_OK", {"user_last4": user_id[-4:]})
            else:
                profile_error = "missing_user_id"
        else:
            profile_error = "kite_client_unavailable"
    except Exception as exc:
        profile_error = f"{type(exc).__name__}:{exc}"
    if not computed_profile_verified:
        _log_ws("FEED_AUTH_PROFILE_FAIL", {"error": profile_error or "unknown"})

    stats_api = _masked_secret_stats("api_key", cfg.KITE_API_KEY)
    stats_token = _masked_secret_stats("access_token", access_token)
    print(
        "[KITE_WS] "
        f"api_key_len={stats_api['api_key_len']} api_key_tail4={stats_api['api_key_tail4']} "
        f"api_key_has_whitespace={stats_api['api_key_has_whitespace']} "
        f"access_token_len={stats_token['access_token_len']} access_token_tail4={stats_token['access_token_tail4']} "
        f"access_token_has_whitespace={stats_token['access_token_has_whitespace']}"
    )
    _log_ws("FEED_CREDENTIAL_STATS", {**stats_api, **stats_token, "tokens": len(tokens)})

    with _KITE_TICKER_LOCK:
        if _KITE_TICKER is not None:
            print("[KITE_WS] existing ticker instance detected, closing before recreate")
            _log_ws("FEED_RECREATE_CLOSE_OLD", {"tokens": len(tokens)})
            _close_ticker_instance(_KITE_TICKER)
            _KITE_TICKER = None
        if _WATCHDOG_STOP is not None:
            _WATCHDOG_STOP.set()
        _WATCHDOG_STOP = threading.Event()
        kws = KiteTicker(cfg.KITE_API_KEY, access_token, debug=True)
        if hasattr(kws, "auto_reconnect"):
            try:
                kws.auto_reconnect = False
            except Exception:
                pass
        print(
            f"KITE_WS api_key_tail4={cfg.KITE_API_KEY[-4:] if len(str(cfg.KITE_API_KEY or '')) >= 4 else cfg.KITE_API_KEY} "
            f"access_token_tail4={access_token[-4:] if len(str(access_token or '')) >= 4 else access_token} "
            f"kite_id={id(kws)}"
        )
        _KITE_TICKER = kws

    handshake_soft_reset_used = False

    def on_connect(ws, response):
        global _STALE_STRIKES, _WARMUP_PENDING
        try:
            _log_ws("FEED_CONNECT", {"tokens": len(tokens), "response": str(response)})
            # Reset stale tracker and invalidate pre-existing depth timestamps so
            # watchdog waits for fresh post-connect ticks.
            _STALE_STRIKES = 0
            _WARMUP_PENDING = True
            for book in list(depth_store.books.values()):
                if isinstance(book, dict):
                    book["ts_epoch"] = None
                    book["ts"] = None
            ws.subscribe(tokens)
            ws.set_mode(ws.MODE_FULL, tokens)
        except Exception as exc:
            _log_ws("FEED_CONNECT_ERROR", {"error": str(exc)})

    def on_reconnect(ws, attempts):
        try:
            ws.subscribe(tokens)
            ws.set_mode(ws.MODE_FULL, tokens)
            _log_ws("FEED_RECONNECT", {"attempts": attempts})
        except Exception as exc:
            _log_ws("FEED_RECONNECT_ERROR", {"error": str(exc), "attempts": attempts})

    def on_error(ws, code, reason):
        nonlocal handshake_soft_reset_used
        reason_text = str(reason)
        _log_ws("FEED_ERROR", {"code": code, "reason": reason_text, "profile_verified": bool(computed_profile_verified)})
        print(f"[KITE_WS][ERROR] code={code} reason={reason}")
        if computed_profile_verified and ("403" in reason_text or "Forbidden" in reason_text):
            hint = "Profile auth succeeded but websocket is 403. Check Kite app websocket entitlement/access."
            _log_ws("FEED_ERROR_HINT", {"hint": hint})
            print(f"[KITE_WS][HINT] {hint}")
        if ("403" in reason_text or "Forbidden" in reason_text) and getattr(cfg, "FEED_TRIP_ON_WS_403", True):
            _log_ws("FEED_WS_403_TRIP", {"code": code, "reason": reason_text})
            try:
                trip_feed_breaker(
                    reason="ws_403_forbidden",
                    meta={"code": code, "reason": reason_text},
                )
            except Exception:
                pass
            try:
                risk_halt.trigger("ws_403_forbidden")
            except Exception:
                pass
            stop_depth_ws(reason="ws_403_forbidden")
            return
        reason_lower = reason_text.lower()
        handshake_error = (str(code) == "1006" or code == 1006) and "opening handshake" in reason_lower
        if handshake_error:
            if not handshake_soft_reset_used:
                handshake_soft_reset_used = True
                try:
                    ws.subscribe(tokens)
                    ws.set_mode(ws.MODE_FULL, tokens)
                    _log_ws("FEED_HANDSHAKE_SOFT_RESET", {"code": code, "reason": reason_text})
                except Exception as exc:
                    _log_ws("FEED_HANDSHAKE_SOFT_RESET_ERROR", {"code": code, "reason": reason_text, "error": str(exc)})
            _log_ws("FEED_HANDSHAKE_SUPPRESS_RESTART", {"code": code, "reason": reason_text})
            return
        fatal = False
        if code in (1006, 1011, 1012):
            fatal = True
        if "connection" in reason_lower and "closed" in reason_lower:
            fatal = True
        if "403" in reason_text or "Forbidden" in reason_text:
            fatal = True
        stop_set = bool(_WATCHDOG_STOP is not None and _WATCHDOG_STOP.is_set())
        if fatal and is_market_open_ist() and not _STOP_REQUESTED and not stop_set:
            restart_depth_ws(reason=f"ws_error:{code}")

    def on_close(ws, code, reason):
        if (_WATCHDOG_STOP is not None and _WATCHDOG_STOP.is_set()) or _STOP_REQUESTED:
            _log_ws("FEED_CLOSE_STOP_REQUESTED", {"code": code, "reason": str(reason)})
            return
        _log_ws("FEED_CLOSE", {"code": code, "reason": str(reason)})
        print(f"[KITE_WS][CLOSE] code={code} reason={reason}")
        if is_market_open_ist():
            restart_depth_ws(reason=f"ws_close:{code}")

    def on_ticks(ws, ticks):
        global _UNDERLYING_LOGGED_MISSING
        for t in ticks:
            token = t.get("instrument_token")
            depth = t.get("depth")
            last_price = t.get("last_price")
            if token and depth:
                depth_store.update(token, depth)
            ts = t.get("exchange_timestamp") or t.get("last_trade_time") or t.get("timestamp")
            tick_epoch = None
            if ts is not None:
                try:
                    if hasattr(ts, "timestamp"):
                        tick_epoch = float(ts.timestamp())
                    else:
                        tick_epoch = float(ts)
                except Exception:
                    tick_epoch = None
            if tick_epoch is not None and tick_epoch > 1e12:
                tick_epoch = tick_epoch / 1000.0
            if last_price is not None or depth is not None:
                if tick_epoch is None:
                    tick_epoch = time.time()
                record_tick_epoch(tick_epoch)
                if not _UNDERLYING_TOKENS and not _UNDERLYING_LOGGED_MISSING:
                    _log_ws("FEED_UNDERLYING_TOKENS_MISSING", {})
                    _UNDERLYING_LOGGED_MISSING = True
            if cfg.KITE_STORE_TICKS:
                try:
                    ok = insert_tick(
                        ts,
                        token,
                        last_price,
                        t.get("volume"),
                        t.get("oi")
                    )
                    if not ok:
                        _log_ws(
                            "FEED_TICK_STORE_ERROR",
                            {
                                "instrument_token": token,
                                "error": "insert_failed",
                                "has_ltp": last_price is not None,
                                "has_depth": depth is not None,
                                "ts_present": ts is not None,
                                "keys": list(t.keys())[:20],
                            },
                        )
                except Exception as exc:
                    _log_ws(
                        "FEED_TICK_STORE_ERROR",
                        {
                            "instrument_token": token,
                            "error": f"{type(exc).__name__}:{exc}",
                            "has_ltp": last_price is not None,
                            "has_depth": depth is not None,
                            "ts_present": ts is not None,
                            "keys": list(t.keys())[:20],
                        },
                    )

    def _watchdog():
        global _STALE_STRIKES, _WARMUP_PENDING
        max_age = float(getattr(cfg, "MAX_DEPTH_AGE_SEC", getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0)))
        soft_cooldown = float(getattr(cfg, "FEED_RECONNECT_COOLDOWN_SEC", 30))
        strikes_to_restart = int(getattr(cfg, "FEED_RESTART_STRIKES", 3))
        last_soft = 0.0
        last_warmup_log = 0.0
        while not _WATCHDOG_STOP.is_set():
            time.sleep(5)
            if not is_market_open_ist():
                _STALE_STRIKES = 0
                continue
            latest = None
            try:
                # find latest depth ts in store
                for v in depth_store.books.values():
                    ts = v.get("ts_epoch") or v.get("ts")
                    if ts is not None:
                        latest = max(latest or 0.0, float(ts))
            except Exception:
                latest = None
            if latest is None:
                now = time.time()
                # Warm-up wait until first fresh tick arrives after connect/reconnect.
                if now - last_warmup_log >= 30.0:
                    _log_ws("FEED_WARMUP_WAIT", {})
                    last_warmup_log = now
                continue
            age = time.time() - latest
            if _WARMUP_PENDING:
                _log_ws("FEED_WARMUP_DONE", {"first_age_sec": age})
                _WARMUP_PENDING = False
            if age <= max_age:
                if _STALE_STRIKES:
                    _log_ws("FEED_RECOVERED", {"age_sec": age, "strikes": _STALE_STRIKES})
                _STALE_STRIKES = 0
                continue

            _STALE_STRIKES += 1
            _log_ws(
                "FEED_STALE_DETECTED",
                {"age_sec": age, "strikes": _STALE_STRIKES, "max_age": max_age},
            )

            if _STALE_STRIKES >= 2:
                backoff = soft_cooldown * (2 ** min(_STALE_STRIKES - 2, 3))
                if time.time() - last_soft >= backoff:
                    last_soft = time.time()
                    try:
                        kws.subscribe(tokens)
                        kws.set_mode(kws.MODE_FULL, tokens)
                        _log_ws("FEED_SOFT_RESET_OK", {"tokens": len(tokens), "backoff_sec": backoff})
                    except Exception as exc:
                        _log_ws("FEED_SOFT_RESET_ERROR", {"error": str(exc), "backoff_sec": backoff})

            if _STALE_STRIKES >= strikes_to_restart:
                restart_depth_ws(reason=f"depth_stale_age={age:.1f}s")

    kws.on_connect = on_connect
    kws.on_reconnect = on_reconnect
    kws.on_error = on_error
    kws.on_close = on_close
    kws.on_ticks = on_ticks
    _WATCHDOG_THREAD = threading.Thread(target=_watchdog, daemon=True)
    _WATCHDOG_THREAD.start()
    kws.connect(threaded=True)
