import json
import time
from pathlib import Path
from typing import Any, Dict

from config import config as cfg
from core.kite_client import kite_client
from core import risk_halt
from core.security_guard import resolve_kite_access_token
from core.paths import logs_dir

LOG_PATH = logs_dir() / "auth_health.jsonl"

_CACHE: Dict[str, Any] = {}


def _log_event(payload: Dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _tail4(value: str) -> str:
    if not value:
        return ""
    return value[-4:] if len(value) >= 4 else value


def _kite_profile_payload() -> Dict[str, Any]:
    kite_client.ensure()
    if not kite_client.kite:
        return {
            "ok": False,
            "auth_state": "FAILED",
            "error": f"kite_client_unavailable:{kite_client.last_init_error}",
            "user_id": "",
            "user_name": "",
        }
    try:
        profile = kite_client.kite.profile()
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
        return cached

    api_key = str(getattr(cfg, "KITE_API_KEY", "") or "").strip()
    api_key_tail4 = _tail4(api_key)

    raw_token = ""
    token_has_ws = False
    try:
        repo_root = Path(__file__).resolve().parents[1]
        raw_token = resolve_kite_access_token(repo_root=repo_root, require_token=True)
    except Exception as exc:
        payload = {
            "ok": False,
            "auth_state": "FAILED",
            "ts_epoch": now_epoch,
            "source": "live",
            "ttl_sec": ttl_sec,
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

    token_has_ws = any(ch.isspace() for ch in (raw_token or ""))
    token = (raw_token or "").strip()
    cfg.KITE_ACCESS_TOKEN = token
    access_token_tail4 = _tail4(token)

    if not api_key:
        payload = {
            "ok": False,
            "auth_state": "FAILED",
            "ts_epoch": now_epoch,
            "source": "live",
            "ttl_sec": ttl_sec,
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
    for attempt in range(attempts):
        profile_payload = _kite_profile_payload()
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
    return payload


def _reset_cache_for_tests() -> None:
    _CACHE.clear()
