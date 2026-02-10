import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Tuple

from config import config as cfg


@dataclass
class CircuitBreaker:
    error_threshold: int = int(getattr(cfg, "CB_ERROR_STORM_N", 5))
    error_window_sec: float = float(getattr(cfg, "CB_ERROR_STORM_MINS", 5) * 60)
    halt_sec: float = float(getattr(cfg, "CB_HALT_MINS", 15) * 60)
    feed_unhealthy_sec: float = float(getattr(cfg, "CB_FEED_UNHEALTHY_SEC", 120))
    error_events: Deque[float] = field(default_factory=deque)
    feed_unhealthy_since_epoch: float | None = None
    halted_until_epoch: float = 0.0
    halt_reason: str | None = None

    def _prune(self, now: float) -> None:
        while self.error_events and (now - self.error_events[0]) > self.error_window_sec:
            self.error_events.popleft()

    def is_halted(self, now: float | None = None) -> bool:
        now_epoch = float(now if now is not None else time.time())
        return now_epoch < float(self.halted_until_epoch)

    def trip(self, reason: str, now: float | None = None) -> Tuple[bool, str]:
        now_epoch = float(now if now is not None else time.time())
        new_until = now_epoch + self.halt_sec
        if new_until > self.halted_until_epoch:
            self.halted_until_epoch = new_until
        self.halt_reason = reason
        return True, reason

    def record_error(self, reason_code: str, now: float | None = None) -> Tuple[bool, str | None]:
        _ = reason_code
        now_epoch = float(now if now is not None else time.time())
        self.error_events.append(now_epoch)
        self._prune(now_epoch)
        if len(self.error_events) >= int(self.error_threshold):
            return self.trip("CB_ERROR_STORM", now=now_epoch)
        return False, None

    def observe_feed_health(self, healthy: bool, now: float | None = None) -> Tuple[bool, str | None]:
        now_epoch = float(now if now is not None else time.time())
        if healthy:
            self.feed_unhealthy_since_epoch = None
            return False, None
        if self.feed_unhealthy_since_epoch is None:
            self.feed_unhealthy_since_epoch = now_epoch
            return False, None
        if (now_epoch - self.feed_unhealthy_since_epoch) >= float(self.feed_unhealthy_sec):
            return self.trip("CB_FEED_UNHEALTHY", now=now_epoch)
        return False, None

    def state_dict(self, now: float | None = None) -> dict:
        now_epoch = float(now if now is not None else time.time())
        self._prune(now_epoch)
        remaining_sec = max(0.0, float(self.halted_until_epoch) - now_epoch)
        return {
            "halted": self.is_halted(now_epoch),
            "halt_reason": self.halt_reason,
            "halted_until_epoch": self.halted_until_epoch,
            "remaining_sec": remaining_sec,
            "error_count_window": len(self.error_events),
            "error_threshold": int(self.error_threshold),
            "error_window_sec": float(self.error_window_sec),
            "feed_unhealthy_since_epoch": self.feed_unhealthy_since_epoch,
            "feed_unhealthy_sec": float(self.feed_unhealthy_sec),
        }
