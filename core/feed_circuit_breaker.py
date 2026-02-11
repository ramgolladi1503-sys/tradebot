import json
import time
from pathlib import Path
from typing import Any, Dict

from core.paths import logs_dir

STATE_PATH = logs_dir() / "feed_circuit_breaker.json"


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


def is_tripped() -> bool:
    state = _load_state()
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


def _reset_for_tests() -> None:
    if STATE_PATH.exists():
        STATE_PATH.unlink()
