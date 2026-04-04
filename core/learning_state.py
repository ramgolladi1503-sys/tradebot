from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from core.events import write_json_atomic
from core.paths import runtime_dir


_STATE_VERSION = 1
_STATE_CACHE: dict[str, tuple[float | None, dict[str, Any]]] = {}


def learning_state_path() -> Path:
    return runtime_dir() / "analytics" / "learning_state.json"


def _default_state() -> dict[str, Any]:
    return {
        "version": _STATE_VERSION,
        "generated_at": None,
        "threshold_summary": {},
        "threshold_impact": {},
        "aggressiveness_mode": "NORMAL",
        "aggressiveness_adjustment": 0.0,
        "aggressiveness_adjustment_applied": False,
    }


def save_learning_state(state: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path is not None else learning_state_path()
    payload = {
        **_default_state(),
        **dict(state or {}),
        "version": _STATE_VERSION,
        "generated_at": str((state or {}).get("generated_at") or datetime.now(timezone.utc).isoformat()),
    }
    write_json_atomic(target, payload)
    try:
        mtime = target.stat().st_mtime if target.exists() else None
    except Exception:
        mtime = None
    _STATE_CACHE[str(target)] = (mtime, dict(payload))
    return target


def load_learning_state(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else learning_state_path()
    if not target.exists():
        return _default_state()
    try:
        mtime = target.stat().st_mtime
    except Exception:
        mtime = None
    cache_key = str(target)
    cached = _STATE_CACHE.get(cache_key)
    if cached is not None and cached[0] == mtime:
        return dict(cached[1])
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return _default_state()
    state = {
        **_default_state(),
        **dict(payload or {}),
    }
    _STATE_CACHE[cache_key] = (mtime, dict(state))
    return state
