from __future__ import annotations

import time
from typing import Any

from config import config as cfg
from core.feed_debug import get_feed_debug


class FastExecutionCore:
    """
    Thin fast-path coordinator around the existing legacy orchestrator.

    It does not replace decision logic yet. It makes cycle triggering feed-aware and
    keeps the legacy engine isolated behind a single-step execution method.
    """

    def __init__(self, orch: Any):
        self.orch = orch
        self.last_feed_epoch: float = 0.0
        self.last_cycle_mono: float = 0.0
        self.last_result: Any = None

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return float(default)
            return float(value)
        except Exception:
            return float(default)

    def idle_sleep_sec(self) -> float:
        configured = getattr(cfg, "ORCHESTRATOR_FAST_LOOP_IDLE_SLEEP_SEC", None)
        if configured not in (None, "", 0, 0.0):
            try:
                return max(0.01, float(configured))
            except Exception:
                pass
        poll_interval = self._safe_float(getattr(self.orch, "poll_interval", None), 0.25)
        return max(0.01, min(0.05, poll_interval / 2.0))

    def max_cycle_interval_sec(self) -> float:
        configured = getattr(cfg, "ORCHESTRATOR_FAST_LOOP_MAX_CYCLE_SEC", None)
        if configured not in (None, "", 0, 0.0):
            try:
                return max(0.05, float(configured))
            except Exception:
                pass
        return max(0.05, self._safe_float(getattr(self.orch, "poll_interval", None), 0.25))

    def latest_feed_epoch(self) -> float:
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
            latest = max(latest, self._safe_float(candidate, 0.0))
        return float(latest)

    def should_run_cycle(self, now_mono: float) -> tuple[bool, float]:
        cycle_due = bool((now_mono - self.last_cycle_mono) >= self.max_cycle_interval_sec())
        if cycle_due:
            return True, float(self.last_feed_epoch)

        feed_epoch = self.latest_feed_epoch()
        feed_changed = bool(feed_epoch > 0.0 and feed_epoch > self.last_feed_epoch)
        return bool(feed_changed), float(feed_epoch)

    def run_one_cycle(self, *, feed_epoch: float | None = None) -> Any:
        result = self.orch._legacy_live_monitoring(run_once=True)
        self.last_cycle_mono = float(time.monotonic())
        if feed_epoch is not None and float(feed_epoch) > 0.0:
            self.last_feed_epoch = float(feed_epoch)
        self.last_result = result
        return result

    def should_stop(self, result: Any) -> bool:
        return result in {"STOP", "HALT", False}
