import json
import logging
import os
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict

from config import config as cfg
from core.paths import logs_dir

STATE_PATH = logs_dir() / "feed_circuit_breaker.json"
logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "None"):
            return default
        return float(value)
    except Exception:
        return default


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"tripped": False}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"tripped": False}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def is_tripped(*, session_date: str | None = None) -> bool:
    state = _load_state()
    if state.get("tripped") and session_date and state.get("session_date") != session_date:
        return False
    return bool(state.get("tripped"))


def trip(reason: str, meta: Dict[str, Any] | None = None) -> None:
    now = time.time()
    state = _load_state()
    if state.get("tripped"):
        return
    state = {
        "tripped": True,
        "reason": reason,
        "ts_epoch": now,
        "session_date": date.today().isoformat(),
        "source_sha": str(os.environ.get("TRADEBOT_COMMIT_SHA") or ""),
        "meta": meta or {},
    }
    _save_state(state)


def clear(reason: str) -> None:
    now = time.time()
    state = {
        "tripped": False,
        "reason": reason,
        "ts_epoch": now,
        "meta": {},
    }
    _save_state(state)


def should_clear_breaker(state: Dict[str, Any] | None) -> bool:
    payload = dict(state or {})
    ws_tick_age_sec = _safe_float(
        payload.get("last_ws_tick_age_sec"),
        _safe_float(payload.get("last_tick_age_sec"), 999.0),
    )
    tick_age_sec = _safe_float(
        payload.get("last_tick_age_sec"),
        _safe_float(payload.get("last_ws_tick_age_sec"), 999.0),
    )
    return (
        payload.get("ws_connected") is True
        and float(ws_tick_age_sec or 999.0) < 2.0
        and float(tick_age_sec or 999.0) < 2.0
    )


def maybe_auto_clear(feed_state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    state = _load_state()
    if not bool(state.get("tripped")):
        return {"tripped": False, "cleared": False, "reason": None}

    now = time.time()
    tripped_epoch = _safe_float(state.get("ts_epoch"), now)
    time_since_trip = max(0.0, float(now - float(tripped_epoch or now)))

    if should_clear_breaker(feed_state):
        logger.info("AUTO_CLEAR_FEED_BREAKER")
        clear(reason="auto_recovered")
        return {
            "tripped": False,
            "cleared": True,
            "clear_reason": "auto_recovered",
            "time_since_trip_sec": time_since_trip,
        }

    max_block_time = float(getattr(cfg, "FEED_BREAKER_MAX_BLOCK_TIME_SEC", 30.0) or 30.0)
    if bool(state.get("tripped")) and time_since_trip > max_block_time:
        logger.warning("FORCED_BREAKER_CLEAR_TIMEOUT")
        clear(reason="timeout_auto_clear")
        return {
            "tripped": False,
            "cleared": True,
            "clear_reason": "timeout_auto_clear",
            "time_since_trip_sec": time_since_trip,
        }

    return {
        "tripped": True,
        "cleared": False,
        "reason": state.get("reason"),
        "time_since_trip_sec": time_since_trip,
    }


def _reset_for_tests() -> None:
    if STATE_PATH.exists():
        STATE_PATH.unlink()
