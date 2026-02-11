import json
import time
from pathlib import Path
from typing import Any, Dict, List

from config import config as cfg
from core.time_utils import now_ist
from core.freshness_sla import get_freshness_status

STATE_PATH = Path("logs/feed_freshness_state.json")
LOG_PATH = Path("logs/feed_freshness.jsonl")
TOKEN_MAP_PATH = Path("logs/token_resolution.json")
SLA_PATH = Path("logs/sla_check.json")

_CACHE: Dict[str, Any] = {}


def _log_event(payload: Dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(exist_ok=True)
    try:
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _state_changed(prev: Dict[str, Any], curr: Dict[str, Any]) -> bool:
    return (
        prev.get("ok") != curr.get("ok")
        or prev.get("reasons") != curr.get("reasons")
        or prev.get("market_open") != curr.get("market_open")
    )


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


def get_feed_freshness(use_cache: bool = True, now_epoch: float | None = None) -> Dict[str, Any]:
    now_epoch = now_epoch or time.time()
    ttl_sec = float(getattr(cfg, "FEED_FRESHNESS_TTL_SEC", 5.0))
    if use_cache and _CACHE.get("ts_epoch") and (now_epoch - float(_CACHE["ts_epoch"])) <= ttl_sec:
        return dict(_CACHE["payload"])

    freshness = get_freshness_status(force=not use_cache)
    tick_lag = (freshness.get("ltp") or {}).get("age_sec")
    depth_lag = (freshness.get("depth") or {}).get("age_sec")

    payload = {
        "ok": bool(freshness.get("ok")),
        "reasons": freshness.get("reasons") or [],
        "market_open": bool(freshness.get("market_open")),
        "enforced": bool(freshness.get("market_open")),
        "data_available": True,
        "ts_epoch": now_epoch,
        "ts_ist": now_ist().isoformat(),
        "tick_last_epoch": None,
        "depth_last_epoch": None,
        "tick_lag_sec": tick_lag,
        "depth_lag_sec": depth_lag,
        "tick_msgs_last_min": None,
        "depth_msgs_last_min": None,
        "per_instrument": [],
    }

    _update_state(payload)
    _CACHE["ts_epoch"] = now_epoch
    _CACHE["payload"] = payload
    return payload


def _update_state(payload: Dict[str, Any]) -> None:
    prev = _load_state()
    curr = {
        "ok": payload.get("ok"),
        "reasons": payload.get("reasons"),
        "market_open": payload.get("market_open"),
    }
    if _state_changed(prev, curr):
        _save_state(curr)
        _log_event(
            {
                "event": "FEED_FRESHNESS_STATE",
                "ts_epoch": payload.get("ts_epoch"),
                "ts_ist": payload.get("ts_ist"),
                "ok": payload.get("ok"),
                "reasons": payload.get("reasons"),
                "market_open": payload.get("market_open"),
                "tick_lag_sec": payload.get("tick_lag_sec"),
                "depth_lag_sec": payload.get("depth_lag_sec"),
            }
        )


def _reset_cache_for_tests() -> None:
    _CACHE.clear()
