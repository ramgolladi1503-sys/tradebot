from __future__ import annotations

import time
from collections.abc import Callable, MutableMapping


def should_run_state_engine(
    *,
    auto_refresh_enabled: bool,
    now_ts: float,
    last_ts: float,
    refresh_sec: float,
) -> bool:
    if not auto_refresh_enabled:
        return False
    safe_refresh = max(1.0, float(refresh_sec))
    return (float(now_ts) - float(last_ts)) >= safe_refresh


def run_state_engine_if_due(
    *,
    session_state: MutableMapping,
    desk_id: str,
    run_once: Callable[..., object],
    refresh_sec: float,
    now_fn: Callable[[], float] = time.time,
) -> bool:
    now_ts = float(now_fn())
    last_ts = float(session_state.get("last_state_engine_ts", 0.0) or 0.0)
    enabled = bool(session_state.get("auto_refresh_enabled", True))
    if not should_run_state_engine(
        auto_refresh_enabled=enabled,
        now_ts=now_ts,
        last_ts=last_ts,
        refresh_sec=refresh_sec,
    ):
        return False
    run_once(desk_id=desk_id)
    session_state["last_state_engine_ts"] = now_ts
    return True
