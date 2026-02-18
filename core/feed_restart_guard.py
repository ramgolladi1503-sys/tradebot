import json
import threading
import time
from pathlib import Path
from typing import Dict, List

from config import config as cfg
from core.paths import logs_dir
from core.log_writer import get_jsonl_writer

STATE_PATH = logs_dir() / "feed_restart_guard_state.json"
LOG_PATH = logs_dir() / "feed_restart_guard.jsonl"
LOG_WRITER = get_jsonl_writer(LOG_PATH)


class FeedRestartGuard:
    def __init__(self):
        self._lock = threading.Lock()
        self._restart_epochs: List[float] = []
        self._breaker_open_until = 0.0

    def _log(self, payload: Dict) -> None:
        try:
            if not LOG_WRITER.write(payload):
                print(f"[FEED_RESTART_GUARD] failed to log path={LOG_PATH}")
        except Exception as exc:
            print(f"[FEED_RESTART_GUARD] failed to log path={LOG_PATH} err={type(exc).__name__}:{exc}")

    def _save_state(self) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps(
                {
                    "breaker_open_until": self._breaker_open_until,
                    "restart_epochs": self._restart_epochs,
                },
                indent=2,
            )
        )

    def allow_restart(self, now: float | None = None, reason: str = "unspecified") -> bool:
        now = now or time.time()
        window_sec = float(getattr(cfg, "FEED_RESTART_STORM_WINDOW_SEC", 3600))
        max_restarts = int(getattr(cfg, "FEED_RESTART_STORM_MAX", 6))
        cooldown_sec = float(getattr(cfg, "FEED_RESTART_STORM_COOLDOWN_SEC", 900))
        with self._lock:
            if now < self._breaker_open_until:
                self._log(
                    {
                        "ts_epoch": now,
                        "event": "FEED_RESTART_BREAKER_OPEN",
                        "reason": reason,
                        "breaker_open_until": self._breaker_open_until,
                    }
                )
                return False

            self._restart_epochs = [t for t in self._restart_epochs if now - t <= window_sec]
            if len(self._restart_epochs) >= max_restarts:
                self._breaker_open_until = now + cooldown_sec
                self._save_state()
                self._log(
                    {
                        "ts_epoch": now,
                        "event": "FEED_RESTART_BREAKER_TRIP",
                        "reason": reason,
                        "window_sec": window_sec,
                        "max_restarts": max_restarts,
                        "breaker_open_until": self._breaker_open_until,
                    }
                )
                return False

            self._restart_epochs.append(now)
            self._save_state()
            self._log(
                {
                    "ts_epoch": now,
                    "event": "FEED_RESTART_ALLOW",
                    "reason": reason,
                    "restart_count_window": len(self._restart_epochs),
                    "window_sec": window_sec,
                }
            )
            return True


feed_restart_guard = FeedRestartGuard()
