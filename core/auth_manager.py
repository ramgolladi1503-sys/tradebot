from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from config import config as cfg
from core.paths import logs_dir, repo_root


_CACHE: dict[str, Any] = {}


def _allow_env_token_for_ci() -> bool:
    return str(os.getenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", "")).strip().lower() in {"1", "true", "yes", "on"}


def access_token_path(repo_root_path: Path | str | None = None) -> Path:
    override = str(os.getenv("TRADING_BOT_TOKEN_PATH", "")).strip()
    if override:
        return Path(override).expanduser().resolve()
    root = Path(repo_root_path).resolve() if repo_root_path is not None else repo_root()
    return (root / ".runtime" / "kite_access_token").resolve()


def _read_repo_token(repo_root_path: Path | str | None = None) -> str:
    path = access_token_path(repo_root_path)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def resolve_access_token(
    *,
    repo_root_path: Path | str | None = None,
    require_token: bool = True,
    enforce_artifact_check: bool = True,
) -> str:
    if enforce_artifact_check:
        from core.security_guard import enforce_no_repo_token_artifacts

        enforce_no_repo_token_artifacts(repo_root_path or repo_root())
    repo_token = _read_repo_token(repo_root_path).strip()
    if repo_token:
        _CACHE["token"] = repo_token
        _CACHE["token_source"] = "repo_file"
        _CACHE["ts_epoch"] = time.time()
        return repo_token

    env_token = str(os.getenv("KITE_ACCESS_TOKEN", "")).strip()
    if env_token and _allow_env_token_for_ci():
        _CACHE["token"] = env_token
        _CACHE["token_source"] = "env_ci"
        _CACHE["ts_epoch"] = time.time()
        return env_token

    if require_token:
        raise RuntimeError(
            "[AUTH] missing_kite_access_token\n"
            f"Missing token at {access_token_path(repo_root_path)}\n"
            "Run scripts/kite_autologin_localhost.py to refresh token."
        )
    return ""


def _is_network_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "invalid session" in msg:
        return False
    if any(k in name for k in ("timeout", "connection", "network", "request")):
        return True
    return ("timed out" in msg) or ("connection" in msg) or ("network" in msg)


def is_auth_error(exc: Exception | None = None, *, code: int | None = None, reason_text: str | None = None) -> bool:
    text = str(reason_text or "")
    if exc is not None:
        text = f"{text} {exc}"
    lower = text.lower()
    if code == 403:
        return True
    if "invalid session" in lower:
        return True
    if "tokenexception" in lower:
        return True
    if "forbidden" in lower and "websocket" in lower:
        return True
    if "access token is invalid" in lower:
        return True
    if "unauthorized" in lower:
        return True
    if exc is not None:
        name = type(exc).__name__
        if name in {"TokenException", "PermissionException", "AuthenticationError"}:
            return True
    return False


def invalidate_cache(reason: str = "") -> None:
    _CACHE.clear()
    if reason:
        _append_auth_event({"event": "AUTH_CACHE_INVALIDATED", "reason": reason, "ts_epoch": time.time()})


def validate_token(
    *,
    repo_root_path: Path | str | None = None,
    force: bool = True,
) -> dict[str, Any]:
    _ = force  # kept for backwards compatibility with callers
    now_epoch = time.time()
    api_key = str(os.getenv("KITE_API_KEY", "") or getattr(cfg, "KITE_API_KEY", "") or "").strip()
    if not api_key:
        return {
            "ok": False,
            "auth_state": "FAILED",
            "error": "missing_api_key:KITE_API_KEY",
            "ts_epoch": now_epoch,
        }
    try:
        _ = resolve_access_token(repo_root_path=repo_root_path, require_token=True)
    except Exception as exc:
        return {
            "ok": False,
            "auth_state": "FAILED",
            "error": str(exc),
            "ts_epoch": now_epoch,
        }
    try:
        from core.kite_client import kite_client

        kite_client.ensure()
        if not kite_client.kite:
            return {
                "ok": False,
                "auth_state": "FAILED",
                "error": "kite_client_unavailable",
                "ts_epoch": now_epoch,
            }
        profile = kite_client.kite.profile() or {}
        user_id = str(profile.get("user_id") or "")
        user_name = str(profile.get("user_name") or "")
        if not user_id:
            return {
                "ok": False,
                "auth_state": "FAILED",
                "error": "profile_missing_user_id",
                "ts_epoch": now_epoch,
                "user_id": user_id,
                "user_name": user_name,
            }
        return {
            "ok": True,
            "auth_state": "OK",
            "error": "",
            "ts_epoch": now_epoch,
            "user_id": user_id,
            "user_name": user_name,
        }
    except Exception as exc:
        if is_auth_error(exc):
            invalidate_cache(reason=f"profile_auth_error:{type(exc).__name__}")
            return {
                "ok": False,
                "auth_state": "AUTH_REQUIRED",
                "error": f"profile_error:{type(exc).__name__}:{exc}",
                "ts_epoch": now_epoch,
            }
        if _is_network_error(exc):
            return {
                "ok": False,
                "auth_state": "UNKNOWN_NETWORK",
                "error": f"profile_error:{type(exc).__name__}",
                "ts_epoch": now_epoch,
            }
        return {
            "ok": False,
            "auth_state": "FAILED",
            "error": f"profile_error:{type(exc).__name__}:{exc}",
            "ts_epoch": now_epoch,
        }


def auth_state_path(repo_root_path: Path | str | None = None) -> Path:
    root = Path(repo_root_path).resolve() if repo_root_path is not None else repo_root()
    return (root / ".runtime" / "auth_state.json").resolve()


def load_auth_state(*, repo_root_path: Path | str | None = None) -> dict[str, Any]:
    path = auth_state_path(repo_root_path=repo_root_path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def runtime_auth_snapshot(*, repo_root_path: Path | str | None = None) -> dict[str, Any]:
    from core.runtime_auth_freshness import latest_auth_health, resolve_runtime_auth_snapshot

    return resolve_runtime_auth_snapshot(
        load_auth_state(repo_root_path=repo_root_path),
        latest_health_payload=latest_auth_health(),
    )


def set_auth_required_state(
    *,
    reason: str,
    source: str,
    code: int | None = None,
    repo_root_path: Path | str | None = None,
) -> dict[str, Any]:
    payload = {
        "status": "AUTH_REQUIRED",
        "reason": str(reason),
        "source": str(source),
        "code": code,
        "ts_epoch": time.time(),
    }
    _write_auth_state(payload, repo_root_path=repo_root_path)
    _append_auth_event({"event": "AUTH_REQUIRED", **payload})
    return payload


def clear_auth_required_state(*, source: str, repo_root_path: Path | str | None = None) -> dict[str, Any]:
    payload = {
        "status": "OK",
        "reason": "",
        "source": str(source),
        "ts_epoch": time.time(),
    }
    _write_auth_state(payload, repo_root_path=repo_root_path)
    _append_auth_event({"event": "AUTH_OK", **payload})
    return payload


def _write_auth_state(payload: dict[str, Any], *, repo_root_path: Path | str | None = None) -> None:
    path = auth_state_path(repo_root_path=repo_root_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_auth_event(payload: dict[str, Any]) -> None:
    path = logs_dir() / "auth_events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
    except Exception:
        pass
