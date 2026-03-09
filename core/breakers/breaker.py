from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from time import time
from typing import Callable, Deque


class BreakerState(str, Enum):
    HEALTHY = "HEALTHY"
    TRIPPED = "TRIPPED"
    RECOVERING = "RECOVERING"


@dataclass(frozen=True)
class BreakerConfig:
    name: str
    window_sec: float = 60.0
    min_samples: int = 10
    trip_error_rate: float = 0.5
    cooldown_sec: float = 30.0
    recovery_healthy_ticks: int = 5
    block_approvals_when_recovering: bool = False


class RollingErrorRateBreaker:
    """
    Rolling-window circuit breaker with deterministic transitions:
    HEALTHY -> TRIPPED -> RECOVERING -> HEALTHY
    """

    def __init__(self, config: BreakerConfig, *, now_fn: Callable[[], float] | None = None):
        self.config = config
        self._now_fn = now_fn or time
        self._samples: Deque[tuple[float, int]] = deque()
        self.state: BreakerState = BreakerState.HEALTHY
        self.tripped_at: float | None = None
        self.recovering_since: float | None = None
        self.healthy_ticks: int = 0
        self.reason: str | None = None

    def _purge_old(self, now_ts: float) -> None:
        cutoff = now_ts - max(float(self.config.window_sec), 0.0)
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def _window_stats(self, now_ts: float) -> tuple[int, float]:
        self._purge_old(now_ts)
        total = len(self._samples)
        if total <= 0:
            return 0, 0.0
        err = sum(flag for _ts, flag in self._samples)
        return total, float(err) / float(total)

    def _should_trip(self, sample_count: int, error_rate: float) -> bool:
        if sample_count < int(self.config.min_samples):
            return False
        return error_rate >= float(self.config.trip_error_rate)

    @property
    def approvals_blocked(self) -> bool:
        if self.state == BreakerState.TRIPPED:
            return True
        if self.state == BreakerState.RECOVERING and bool(self.config.block_approvals_when_recovering):
            return True
        return False

    def observe(self, is_error: bool, *, now_ts: float | None = None) -> dict:
        ts_now = float(now_ts) if now_ts is not None else float(self._now_fn())
        self._samples.append((ts_now, 1 if bool(is_error) else 0))
        sample_count, error_rate = self._window_stats(ts_now)

        previous_state = self.state
        action = "NOOP"

        if self.state == BreakerState.HEALTHY:
            if self._should_trip(sample_count, error_rate):
                self.state = BreakerState.TRIPPED
                self.tripped_at = ts_now
                self.recovering_since = None
                self.healthy_ticks = 0
                self.reason = (
                    f"{self.config.name}:error_rate={error_rate:.3f}"
                    f",samples={sample_count},threshold={self.config.trip_error_rate:.3f}"
                )
                action = "TRIPPED"
        elif self.state == BreakerState.TRIPPED:
            elapsed = ts_now - float(self.tripped_at or ts_now)
            if (not bool(is_error)) and elapsed >= float(self.config.cooldown_sec):
                self.state = BreakerState.RECOVERING
                self.recovering_since = ts_now
                self.healthy_ticks = 1
                action = "RECOVERING"
        elif self.state == BreakerState.RECOVERING:
            if bool(is_error):
                self.state = BreakerState.TRIPPED
                self.tripped_at = ts_now
                self.recovering_since = None
                self.healthy_ticks = 0
                self.reason = f"{self.config.name}:recovery_error"
                action = "RETRIPPED"
            else:
                self.healthy_ticks += 1
                if self.healthy_ticks >= int(self.config.recovery_healthy_ticks):
                    self.state = BreakerState.HEALTHY
                    self.tripped_at = None
                    self.recovering_since = None
                    self.healthy_ticks = 0
                    self.reason = None
                    action = "CLEARED"

        return {
            "breaker": self.config.name,
            "prev_state": previous_state.value,
            "state": self.state.value,
            "action": action,
            "approvals_blocked": bool(self.approvals_blocked),
            "sample_count": int(sample_count),
            "error_rate": float(error_rate),
            "ts_epoch": ts_now,
            "reason": self.reason,
        }

    def snapshot(self, *, now_ts: float | None = None) -> dict:
        ts_now = float(now_ts) if now_ts is not None else float(self._now_fn())
        sample_count, error_rate = self._window_stats(ts_now)
        return {
            "name": self.config.name,
            "state": self.state.value,
            "approvals_blocked": bool(self.approvals_blocked),
            "sample_count": int(sample_count),
            "error_rate": float(error_rate),
            "tripped_at": self.tripped_at,
            "recovering_since": self.recovering_since,
            "healthy_ticks": int(self.healthy_ticks),
            "reason": self.reason,
            "ts_epoch": ts_now,
            "config": {
                "window_sec": float(self.config.window_sec),
                "min_samples": int(self.config.min_samples),
                "trip_error_rate": float(self.config.trip_error_rate),
                "cooldown_sec": float(self.config.cooldown_sec),
                "recovery_healthy_ticks": int(self.config.recovery_healthy_ticks),
                "block_approvals_when_recovering": bool(self.config.block_approvals_when_recovering),
            },
        }


class BreakerSuite:
    """
    Three breaker streams with shared "block new approvals" decision.
    """

    def __init__(
        self,
        *,
        now_fn: Callable[[], float] | None = None,
        stale_feed_config: BreakerConfig | None = None,
        price_mismatch_config: BreakerConfig | None = None,
        broker_failure_config: BreakerConfig | None = None,
    ):
        clock = now_fn or time
        self.stale_feed_breaker = RollingErrorRateBreaker(
            stale_feed_config
            or BreakerConfig(
                name="stale_feed_breaker",
                window_sec=60.0,
                min_samples=6,
                trip_error_rate=0.50,
                cooldown_sec=15.0,
                recovery_healthy_ticks=4,
            ),
            now_fn=clock,
        )
        self.price_mismatch_breaker = RollingErrorRateBreaker(
            price_mismatch_config
            or BreakerConfig(
                name="price_mismatch_breaker",
                window_sec=120.0,
                min_samples=8,
                trip_error_rate=0.60,
                cooldown_sec=20.0,
                recovery_healthy_ticks=5,
            ),
            now_fn=clock,
        )
        self.broker_failure_breaker = RollingErrorRateBreaker(
            broker_failure_config
            or BreakerConfig(
                name="broker_failure_breaker",
                window_sec=180.0,
                min_samples=4,
                trip_error_rate=0.50,
                cooldown_sec=30.0,
                recovery_healthy_ticks=3,
            ),
            now_fn=clock,
        )

    def observe_stale_feed(self, is_error: bool, *, now_ts: float | None = None) -> dict:
        return self.stale_feed_breaker.observe(is_error, now_ts=now_ts)

    def observe_price_mismatch(self, is_error: bool, *, now_ts: float | None = None) -> dict:
        return self.price_mismatch_breaker.observe(is_error, now_ts=now_ts)

    def observe_broker_failure(self, is_error: bool, *, now_ts: float | None = None) -> dict:
        return self.broker_failure_breaker.observe(is_error, now_ts=now_ts)

    def should_block_new_trade_approvals(self, *, now_ts: float | None = None) -> tuple[bool, list[str]]:
        blockers: list[str] = []
        for breaker in (
            self.stale_feed_breaker,
            self.price_mismatch_breaker,
            self.broker_failure_breaker,
        ):
            # Refresh aging/purge side effects before reporting state.
            breaker.snapshot(now_ts=now_ts)
            if breaker.approvals_blocked:
                blockers.append(breaker.config.name)
        return bool(blockers), blockers

    def snapshot(self, *, now_ts: float | None = None) -> dict:
        blocked, blockers = self.should_block_new_trade_approvals(now_ts=now_ts)
        return {
            "ok_for_new_approvals": not blocked,
            "blockers": blockers,
            "breakers": {
                "stale_feed_breaker": self.stale_feed_breaker.snapshot(now_ts=now_ts),
                "price_mismatch_breaker": self.price_mismatch_breaker.snapshot(now_ts=now_ts),
                "broker_failure_breaker": self.broker_failure_breaker.snapshot(now_ts=now_ts),
            },
        }
