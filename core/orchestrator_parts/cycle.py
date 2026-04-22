import time

from config import config as cfg
from core.feed_debug import get_feed_debug


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _fast_loop_enabled() -> bool:
    return bool(getattr(cfg, "ORCHESTRATOR_FAST_LOOP_ENABLE", True))


def _idle_sleep_sec(orch) -> float:
    configured = getattr(cfg, "ORCHESTRATOR_FAST_LOOP_IDLE_SLEEP_SEC", None)
    if configured not in (None, "", 0, 0.0):
        try:
            return max(0.01, float(configured))
        except Exception:
            pass
    poll_interval = _safe_float(getattr(orch, "poll_interval", None), 0.25)
    return max(0.01, min(0.05, poll_interval / 2.0))


def _max_cycle_interval_sec(orch) -> float:
    configured = getattr(cfg, "ORCHESTRATOR_FAST_LOOP_MAX_CYCLE_SEC", None)
    if configured not in (None, "", 0, 0.0):
        try:
            return max(0.05, float(configured))
        except Exception:
            pass
    return max(0.05, _safe_float(getattr(orch, "poll_interval", None), 0.25))


def _latest_feed_epoch() -> float:
    try:
        debug = dict(get_feed_debug() or {})
    except Exception:
        return 0.0
    candidates = [
        debug.get("last_ws_tick_epoch"),
        debug.get("last_tick_epoch"),
        debug.get("last_depth_epoch"),
    ]
    latest = 0.0
    for candidate in candidates:
        latest = max(latest, _safe_float(candidate, 0.0))
    return float(latest)


def _run_fast_live_monitoring(orch, time_module=None):
    clock = time_module or time
    idle_sleep_sec = _idle_sleep_sec(orch)
    max_cycle_interval_sec = _max_cycle_interval_sec(orch)
    last_cycle_mono = 0.0
    last_feed_epoch = 0.0

    while True:
        now_mono = float(clock.monotonic())
        feed_epoch = _latest_feed_epoch()
        feed_changed = bool(feed_epoch > 0.0 and feed_epoch > last_feed_epoch)
        cycle_due = bool((now_mono - last_cycle_mono) >= max_cycle_interval_sec)

        if not feed_changed and not cycle_due:
            clock.sleep(idle_sleep_sec)
            continue

        result = orch._legacy_live_monitoring(run_once=True)
        last_cycle_mono = float(clock.monotonic())
        if feed_epoch > 0.0:
            last_feed_epoch = float(feed_epoch)

        if result in {"STOP", "HALT", False}:
            return result

        clock.sleep(idle_sleep_sec)


def run_live_monitoring(orch, run_once=False, time_module=None):
    """
    Feed-aware cycle coordinator.

    - run_once=True preserves legacy one-shot behavior.
    - Continuous mode uses a fast wrapper that only triggers a new legacy cycle
      when feed state changes or the max cycle interval elapses.
    """
    if run_once or not _fast_loop_enabled():
        return orch._legacy_live_monitoring(run_once=run_once)
    return _run_fast_live_monitoring(orch, time_module=time_module)
