from __future__ import annotations

import inspect
import logging
import threading
from pathlib import Path
from typing import Tuple

from config import config as cfg
from core.auth_manager import resolve_access_token

logger = logging.getLogger(__name__)

_CREDENTIAL_LOCK = threading.Lock()
_ACTIVE_API_KEY = ""
_ACTIVE_ACCESS_TOKEN = ""


def record_feed_startup_event(*args, **kwargs):
    """Load feed evidence only when ticker lifecycle work actually occurs."""
    from core.feed_startup_lifecycle import record_feed_startup_event as recorder

    return recorder(*args, **kwargs)


def _record_feed_startup_event(*args, **kwargs):
    """Backward-compatible private delegate for focused boundary tests."""
    return record_feed_startup_event(*args, **kwargs)


# Redaction and caller attribution are observability helpers, not authority logic.
# pragma: no mutate block
def _tail4(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    return text[-4:] if len(text) >= 4 else text


def _caller_module_name() -> str:
    frame = inspect.currentframe()
    if frame is None:
        return "unknown"
    frame = frame.f_back
    while frame is not None:
        module_name = str(frame.f_globals.get("__name__", "") or "").strip()
        if module_name and module_name not in {__name__, "logging"}:
            return module_name
        frame = frame.f_back
    return "unknown"
# pragma: mutate block


def reset_kite_runtime_credentials_guard() -> None:
    global _ACTIVE_API_KEY, _ACTIVE_ACCESS_TOKEN
    with _CREDENTIAL_LOCK:
        _ACTIVE_API_KEY = ""
        _ACTIVE_ACCESS_TOKEN = ""


def _register_runtime_credentials(api_key: str, access_token: str) -> None:
    credential_api_key = str(api_key or "").strip()
    credential_access_token = str(access_token or "").strip()
    caller_module = _caller_module_name()
    with _CREDENTIAL_LOCK:
        global _ACTIVE_API_KEY, _ACTIVE_ACCESS_TOKEN
        if not _ACTIVE_API_KEY and not _ACTIVE_ACCESS_TOKEN:
            _ACTIVE_API_KEY = credential_api_key
            _ACTIVE_ACCESS_TOKEN = credential_access_token
        elif _ACTIVE_API_KEY != credential_api_key or _ACTIVE_ACCESS_TOKEN != credential_access_token:
            # Observability only; the drift decision and exception remain mutated.
            # pragma: no mutate block
            logger.error(
                "credential_drift_detected api_key_tail4_prev=%s api_key_tail4_new=%s access_token_tail4_prev=%s access_token_tail4_new=%s caller_module=%s",
                _tail4(_ACTIVE_API_KEY),
                _tail4(credential_api_key),
                _tail4(_ACTIVE_ACCESS_TOKEN),
                _tail4(credential_access_token),
                caller_module,
            )
            # pragma: mutate block
            raise RuntimeError("CREDENTIAL_DRIFT_DETECTED")
        # Observability only.
        # pragma: no mutate block
        logger.info(
            "runtime_credential_guard api_key_tail4=%s access_token_tail4=%s caller_module=%s",
            _tail4(_ACTIVE_API_KEY),
            _tail4(_ACTIVE_ACCESS_TOKEN),
            caller_module,
        )
        # pragma: mutate block


def get_kite_credentials(*, repo_root_path: Path | str | None = None) -> Tuple[str, str]:
    api_key = str(getattr(cfg, "KITE_API_KEY", "") or "").strip()
    if not api_key:
        logger.error("kite_credentials_missing_api_key")  # pragma: no mutate
        raise RuntimeError("kite_api_key_missing")

    access_token = str(
        resolve_access_token(
            repo_root_path=repo_root_path,
            require_token=True,
        )
        or ""
    ).strip()
    if not access_token:
        logger.error("kite_credentials_missing_access_token")  # pragma: no mutate
        raise RuntimeError("kite_access_token_missing")

    _register_runtime_credentials(api_key, access_token)
    # Redacted credential telemetry only.
    # pragma: no mutate block
    logger.info(
        "kite_runtime_credentials api_key_tail4=%s access_token_tail4=%s",
        _tail4(api_key),
        _tail4(access_token),
    )
    # pragma: mutate block
    return api_key, access_token


def validate_kite_startup_credentials(
    *,
    repo_root_path: Path | str | None = None,
    require_access_token: bool = True,
    require_api_secret: bool = False,
    caller_module: str | None = None,
) -> dict[str, str]:
    caller = str(caller_module or _caller_module_name() or "unknown")
    access_token = ""
    if require_access_token:
        api_key, access_token = get_kite_credentials(repo_root_path=repo_root_path)
    else:
        api_key = str(getattr(cfg, "KITE_API_KEY", "") or "").strip()
        if not api_key:
            logger.error("kite_startup_credentials_missing_api_key caller_module=%s", caller)  # pragma: no mutate
            raise RuntimeError("kite_api_key_missing")
    api_secret = ""
    if require_api_secret:
        api_secret = str(getattr(cfg, "KITE_API_SECRET", "") or "").strip()
        if not api_secret:
            logger.error("kite_startup_credentials_missing_api_secret caller_module=%s", caller)  # pragma: no mutate
            raise RuntimeError("kite_api_secret_missing")
    # Redacted startup telemetry only.
    # pragma: no mutate block
    logger.info(
        "kite_startup_credentials_validated api_key_tail4=%s access_token_tail4=%s caller_module=%s require_access_token=%s require_api_secret=%s",
        _tail4(api_key),
        _tail4(access_token),
        caller,
        bool(require_access_token),
        bool(require_api_secret),
    )
    # pragma: mutate block
    return {
        "api_key": api_key,
        "access_token": access_token,
        "api_secret": api_secret,
    }


def _resolve_canonical_runtime_credentials(
    *,
    api_key: str | None = None,
    access_token: str | None = None,
    repo_root_path: Path | str | None = None,
) -> Tuple[str, str]:
    canonical_api_key, canonical_access_token = get_kite_credentials(repo_root_path=repo_root_path)
    requested_api_key = str(api_key or "").strip()
    requested_access_token = str(access_token or "").strip()
    caller_module = _caller_module_name()
    if requested_api_key and requested_api_key != canonical_api_key:
        # Observability only; the drift branch and exception remain mutated.
        # pragma: no mutate block
        logger.error(
            "credential_drift_detected api_key_tail4_prev=%s api_key_tail4_new=%s access_token_tail4_prev=%s access_token_tail4_new=%s caller_module=%s",
            _tail4(canonical_api_key),
            _tail4(requested_api_key),
            _tail4(canonical_access_token),
            _tail4(requested_access_token or canonical_access_token),
            caller_module,
        )
        # pragma: mutate block
        raise RuntimeError("CREDENTIAL_DRIFT_DETECTED")
    if requested_access_token and requested_access_token != canonical_access_token:
        # Observability only; the drift branch and exception remain mutated.
        # pragma: no mutate block
        logger.error(
            "credential_drift_detected api_key_tail4_prev=%s api_key_tail4_new=%s access_token_tail4_prev=%s access_token_tail4_new=%s caller_module=%s",
            _tail4(canonical_api_key),
            _tail4(requested_api_key or canonical_api_key),
            _tail4(canonical_access_token),
            _tail4(requested_access_token),
            caller_module,
        )
        # pragma: mutate block
        raise RuntimeError("CREDENTIAL_DRIFT_DETECTED")
    return canonical_api_key, canonical_access_token


def build_kite_auth_client(*, api_key: str):
    from core.kite_client import _RAW_KITECONNECT

    if _RAW_KITECONNECT is None:
        raise RuntimeError("kiteconnect_not_installed")
    return _RAW_KITECONNECT(api_key=api_key)


def get_kite_client(
    *,
    api_key: str | None = None,
    access_token: str | None = None,
    repo_root_path: Path | str | None = None,
):
    resolved_api_key, resolved_access_token = _resolve_canonical_runtime_credentials(
        api_key=api_key,
        access_token=access_token,
        repo_root_path=repo_root_path,
    )

    from core.kite_client import _RAW_KITECONNECT

    if _RAW_KITECONNECT is None:
        raise RuntimeError("kiteconnect_not_installed")
    kite = _RAW_KITECONNECT(api_key=resolved_api_key)
    kite.set_access_token(resolved_access_token)
    # Redacted client-initialization telemetry only.
    # pragma: no mutate block
    logger.info(
        "kite_client_initialized api_key_tail4=%s access_token_tail4=%s caller_module=%s",
        _tail4(resolved_api_key),
        _tail4(resolved_access_token),
        _caller_module_name(),
    )
    # pragma: mutate block
    return kite


def get_kite_ticker(
    *,
    api_key: str | None = None,
    access_token: str | None = None,
    debug: bool = True,
    repo_root_path: Path | str | None = None,
):
    resolved_api_key, resolved_access_token = _resolve_canonical_runtime_credentials(
        api_key=api_key,
        access_token=access_token,
        repo_root_path=repo_root_path,
    )

    import core.kite_depth_ws as ws

    record_feed_startup_event(
        "KITE_TICKER_CREATE_ATTEMPTED",
        source="core.auth.get_kite_ticker",
        details={
            "api_key_present": bool(resolved_api_key),
            "api_key_tail4": _tail4(resolved_api_key),
            "access_token_present": bool(resolved_access_token),
            "access_token_len": len(str(resolved_access_token or "")),
            "access_token_tail4": _tail4(resolved_access_token),
            "debug": bool(debug),
        },
    )
    ticker_cls = getattr(ws, "KiteTicker", None)
    if ticker_cls is None:
        record_feed_startup_event(
            "KITE_TICKER_CREATE_FAILED",
            source="core.auth.get_kite_ticker",
            error="kiteconnect_not_installed",
        )
        raise RuntimeError("kiteconnect_not_installed")
    # Redacted ticker-initialization telemetry only.
    # pragma: no mutate block
    logger.info(
        "kite_ticker_initialized api_key_tail4=%s access_token_tail4=%s caller_module=%s",
        _tail4(resolved_api_key),
        _tail4(resolved_access_token),
        _caller_module_name(),
    )
    # pragma: mutate block
    try:
        ticker = ticker_cls(
            resolved_api_key,
            resolved_access_token,
            debug=debug,
            reconnect=True,
            reconnect_max_tries=300,
            reconnect_max_delay=60,
        )
    except Exception as exc:
        record_feed_startup_event(
            "KITE_TICKER_CREATE_FAILED",
            source="core.auth.get_kite_ticker",
            error=f"{type(exc).__name__}:{exc}",
        )
        raise
    record_feed_startup_event(
        "KITE_TICKER_CREATED",
        source="core.auth.get_kite_ticker",
        details={"kite_id": id(ticker)},
    )
    return ticker
