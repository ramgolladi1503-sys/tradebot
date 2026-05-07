import json
import os
import time
from pathlib import Path
from typing import Any, Dict

from config import config as cfg
from core.auth import get_kite_credentials
from core.auth_manager import invalidate_cache
from core.kite_client import kite_client
from core.market_context import derive_market_context
from core import risk_halt
from core.paths import logs_dir

LOG_PATH = logs_dir() / "auth_health.jsonl"

_CACHE: Dict[str, Any] = {}
_PREOPEN_WARM_CACHE: Dict[str, Any] = {}
_PROACTIVE_REFRESH_INFLIGHT = False


def _env_flag_enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _skip_auth_probe_in_sim() -> bool:
    mode = str(
        getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM")) or "SIM"
    ).strip().upper()
    dry_run_enabled = bool(getattr(cfg, "DRY_RUN", False) or _env_flag_enabled("DRY_RUN"))
    return mode in {"SIM", "DRY_RUN"} or dry_run_enabled


def _log_event(payload: Dict[str, Any]) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _runtime_guard_path() -> Path:
    raw = str(getattr(cfg, "AUTH_RUNTIME_GUARD_PATH", str(logs_dir() / "auth_runtime_guard.json")) or "").strip()
    return Path(raw or str(logs_dir() / "auth_runtime_guard.json"))


def _write_runtime_guard(payload: Dict[str, Any]) -> None:
    path = _runtime_guard_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


def load_auth_runtime_guard() -> Dict[str, Any]:
    path = _runtime_guard_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _tail4(value: str) -> str:
    if not value:
        return ""
    return value[-4:] if len(value) >= 4 else value


def _kite_profile_payload() -> Dict[str, Any]:
    try:
        rest_client = kite_client.ensure()
    except Exception as exc:
        return {
            "ok": False,
            "auth_state": "FAILED",
            "error": f"kite_client_unavailable:{type(exc).__name__}:{exc}",
            "user_id": "",
            "user_name": "",
        }
    if not rest_client:
        return {
            "ok": False,
            "auth_state": "FAILED",
            "error": f"kite_client_unavailable:{kite_client.last_init_error}",
            "user_id": "",
            "user_name": "",
        }
    try:
        profile = rest_client.profile()
        user_id = (profile or {}).get("user_id") or ""
        user_name = (profile or {}).get("user_name") or ""
        if not user_id:
            return {
                "ok": False,
                "auth_state": "FAILED",
                "error": "profile_missing_user_id",
                "user_id": user_id,
                "user_name": user_name,
            }
        return {
            "ok": True,
            "auth_state": "OK",
            "error": "",
            "user_id": user_id,
            "user_name": user_name,
        }
    except Exception as exc:
        if _is_network_error(exc):
            return {
                "ok": True,
                "auth_state": "UNKNOWN_NETWORK",
                "error": f"profile_error:{type(exc).__name__}",
                "user_id": "",
                "user_name": "",
            }
        invalidate_cache(reason=f"auth_profile_error:{type(exc).__name__}")
        return {
            "ok": False,
            "auth_state": "FAILED",
            "error": f"profile_error:{type(exc).__name__}",
            "user_id": "",
            "user_name": "",
        }


def _is_network_error(exc: Exception) -> bool:
    name = type(exc).__name__
    if name in {"ConnectionError", "Timeout", "ReadTimeout", "ConnectTimeout", "RequestException"}:
        return True
    msg = str(exc).lower()
    if "connection" in msg or "timed out" in msg or "timeout" in msg:
        return True
    return False


def _maybe_proactive_refresh(payload: Dict[str, Any], *, force: bool, now_epoch: float) -> Dict[str, Any]:
    global _PROACTIVE_REFRESH_INFLIGHT
    if force:
        return payload
    if not bool(getattr(cfg, "AUTH_PROACTIVE_REFRESH_ENABLE", True)):
        return payload
    if _PROACTIVE_REFRESH_INFLIGHT:
        return payload

    ts_epoch = payload.get("ts_epoch")
    try:
        age_sec = max(0.0, float(now_epoch - float(ts_epoch))) if ts_epoch is not None else None
    except Exception:
        age_sec = None

    stale_limit = float(getattr(cfg, "AUTH_PROACTIVE_REFRESH_MAX_STALE_SEC", 150.0))
    unhealthy = not bool(payload.get("ok", False))
    stale_cached = age_sec is not None and age_sec >= stale_limit
    unknown_network = str(payload.get("auth_state") or "").upper() == "UNKNOWN_NETWORK"
    if not (unhealthy or stale_cached or unknown_network):
        return payload

    refresh_reason = (
        "auth_unhealthy"
        if unhealthy
        else ("cache_stale" if stale_cached else "unknown_network")
    )
    _PROACTIVE_REFRESH_INFLIGHT = True
    try:
        refreshed = dict(get_kite_auth_health(force=True) or {})
    except Exception:
        refreshed = dict(payload)
    finally:
        _PROACTIVE_REFRESH_INFLIGHT = False

    refreshed["proactive_refresh"] = {
        "triggered": True,
        "reason": refresh_reason,
        "previous_ok": bool(payload.get("ok", False)),
    }
    return refreshed


def get_kite_auth_health(force: bool = False) -> Dict[str, Any]:
    """
    Canonical Kite auth health check with caching. Returns ok=False on failures.
    """
    now_epoch = time.time()
    ttl_sec = float(getattr(cfg, "AUTH_HEALTH_TTL_SEC", 60))
    if not force and _CACHE.get("ts_epoch") and (now_epoch - float(_CACHE["ts_epoch"])) <= ttl_sec:
        cached = dict(_CACHE.get("payload") or {})
        cached["source"] = "cache"
        cached["ttl_sec"] = ttl_sec
        return _maybe_proactive_refresh(cached, force=False, now_epoch=now_epoch)
    if (not force) and _skip_auth_probe_in_sim():
        payload = {
            "ok": True,
            "auth_state": "SKIPPED_SIM_MODE",
            "ts_epoch": now_epoch,
            "source": "sim_skip",
            "ttl_sec": ttl_sec,
            "latency_sec": 0.0,
            "api_key_tail4": "",
            "access_token_tail4": "",
            "access_token_has_whitespace": False,
            "user_id": "",
            "user_name": "",
            "error": "",
        }
        _CACHE["ts_epoch"] = now_epoch
        _CACHE["payload"] = payload
        _log_event(payload)
        return payload

    api_key = str(getattr(cfg, "KITE_API_KEY", "") or "").strip()
    api_key_tail4 = _tail4(api_key)
    raw_token = ""
    token_has_ws = False
    try:
        repo_root = Path(__file__).resolve().parents[1]
        api_key, raw_token = get_kite_credentials(repo_root_path=repo_root)
    except Exception as exc:
        payload = {
            "ok": False,
            "auth_state": "FAILED",
            "ts_epoch": now_epoch,
            "source": "live",
            "ttl_sec": ttl_sec,
            "latency_sec": None,
            "api_key_tail4": api_key_tail4,
            "access_token_tail4": "",
            "access_token_has_whitespace": False,
            "user_id": "",
            "user_name": "",
            "error": f"missing_access_token:{exc}",
        }
        _CACHE["ts_epoch"] = now_epoch
        _CACHE["payload"] = payload
        _log_event(payload)
        return payload
    api_key_tail4 = _tail4(api_key)

    token_has_ws = any(ch.isspace() for ch in (raw_token or ""))
    token = (raw_token or "").strip()
    access_token_tail4 = _tail4(token)

    if not api_key:
        payload = {
            "ok": False,
            "auth_state": "FAILED",
            "ts_epoch": now_epoch,
            "source": "live",
            "ttl_sec": ttl_sec,
            "latency_sec": None,
            "api_key_tail4": api_key_tail4,
            "access_token_tail4": access_token_tail4,
            "access_token_has_whitespace": token_has_ws,
            "user_id": "",
            "user_name": "",
            "error": "missing_api_key:KITE_API_KEY",
        }
        _CACHE["ts_epoch"] = now_epoch
        _CACHE["payload"] = payload
        _log_event(payload)
        return payload

    if not token:
        payload = {
            "ok": False,
            "auth_state": "FAILED",
            "ts_epoch": now_epoch,
            "source": "live",
            "ttl_sec": ttl_sec,
            "latency_sec": None,
            "api_key_tail4": api_key_tail4,
            "access_token_tail4": access_token_tail4,
            "access_token_has_whitespace": token_has_ws,
            "user_id": "",
            "user_name": "",
            "error": "missing_access_token:empty",
        }
        _CACHE["ts_epoch"] = now_epoch
        _CACHE["payload"] = payload
        _log_event(payload)
        return payload

    attempts = max(1, int(getattr(cfg, "KITE_AUTH_RETRY_ATTEMPTS", 2)))
    backoff = float(getattr(cfg, "KITE_AUTH_RETRY_BACKOFF_SEC", 0.8))
    profile_payload = {}
    profile_latency_sec = None
    for attempt in range(attempts):
        started = time.time()
        profile_payload = _kite_profile_payload()
        try:
            profile_latency_sec = max(0.0, float(time.time() - started))
        except Exception:
            profile_latency_sec = None
        if profile_payload.get("ok"):
            break
        if profile_payload.get("auth_state") == "UNKNOWN_NETWORK":
            break
        if attempt < attempts - 1:
            time.sleep(backoff * (2 ** attempt))
    if profile_payload.get("ok") and profile_payload.get("auth_state") == "OK":
        try:
            state = risk_halt.load_halt()
            if state.get("halted") and state.get("reason") == "db_write_fail":
                risk_halt.clear_halt()
                _log_event({
                    "ts_epoch": now_epoch,
                    "event": "AUTH_HEALTH_HALT_CLEARED",
                    "reason": "db_write_fail",
                })
        except Exception:
            pass
    payload = {
        "ok": bool(profile_payload.get("ok")),
        "auth_state": str(profile_payload.get("auth_state") or ("OK" if profile_payload.get("ok") else "FAILED")),
        "ts_epoch": now_epoch,
        "source": "live",
        "ttl_sec": ttl_sec,
        "latency_sec": profile_latency_sec,
        "api_key_tail4": api_key_tail4,
        "access_token_tail4": access_token_tail4,
        "access_token_has_whitespace": token_has_ws,
        "user_id": profile_payload.get("user_id", ""),
        "user_name": profile_payload.get("user_name", ""),
        "error": profile_payload.get("error", "") if not profile_payload.get("ok") else "",
    }
    _CACHE["ts_epoch"] = now_epoch
    _CACHE["payload"] = payload
    _log_event(payload)
    return _maybe_proactive_refresh(payload, force=bool(force), now_epoch=now_epoch)


def run_preopen_auth_warm_check(
    *,
    force: bool = False,
    market_context: Dict[str, Any] | None = None,
    now_epoch: float | None = None,
) -> Dict[str, Any]:
    now_ts = float(now_epoch if now_epoch is not None else time.time())
    interval_sec = float(getattr(cfg, "AUTH_PREOPEN_WARM_INTERVAL_SEC", 45.0))
    if (
        (not force)
        and _PREOPEN_WARM_CACHE.get("ts_epoch") is not None
        and (now_ts - float(_PREOPEN_WARM_CACHE["ts_epoch"])) < interval_sec
    ):
        return dict(_PREOPEN_WARM_CACHE.get("payload") or {})

    enabled = bool(getattr(cfg, "AUTH_PREOPEN_WARM_CHECK_ENABLE", True))
    ctx = derive_market_context(
        market_context
        or {
            "execution_mode": str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
        }
    )
    preopen = bool(
        str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "LIVE"
        and (not bool(ctx.is_market_open))
    )
    payload = {
        "ts_epoch": now_ts,
        "enabled": enabled,
        "preopen": preopen,
        "mode": str(ctx.mode),
        "market_open": bool(ctx.is_market_open),
        "degrade_to_planning": False,
        "reason": "",
        "auth_ok": True,
    }
    if (not enabled) or (not preopen):
        payload["reason"] = "skipped_not_preopen" if enabled else "disabled"
        _write_runtime_guard(payload)
        _PREOPEN_WARM_CACHE["ts_epoch"] = now_ts
        _PREOPEN_WARM_CACHE["payload"] = payload
        return payload

    auth_force = bool(force or getattr(cfg, "AUTH_PREOPEN_FORCE_REFRESH", True))
    auth_payload = dict(get_kite_auth_health(force=auth_force) or {})
    auth_ok = bool(auth_payload.get("ok", False))
    auth_reason = str(auth_payload.get("error") or auth_payload.get("reason") or "")
    degrade = bool((not auth_ok) and getattr(cfg, "AUTH_PREOPEN_DEGRADE_TO_PLANNING", True))
    payload.update(
        {
            "auth_ok": auth_ok,
            "reason": auth_reason if auth_reason else ("ok" if auth_ok else "auth_unknown"),
            "degrade_to_planning": bool(degrade),
            "auth_state": str(auth_payload.get("auth_state") or ""),
            "auth_latency_sec": auth_payload.get("latency_sec"),
            "auth_ts_epoch": auth_payload.get("ts_epoch"),
        }
    )
    _write_runtime_guard(payload)
    _PREOPEN_WARM_CACHE["ts_epoch"] = now_ts
    _PREOPEN_WARM_CACHE["payload"] = payload
    if degrade:
        _log_event(
            {
                "event": "AUTH_PREOPEN_DEGRADED_TO_PLANNING",
                "ts_epoch": now_ts,
                "reason": payload.get("reason"),
            }
        )
    return payload


def _reset_cache_for_tests() -> None:
    _CACHE.clear()
    _PREOPEN_WARM_CACHE.clear()
