from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque

from config import config as cfg

BREAKER_STALE_FEED = "STALE_FEED"
BREAKER_PRICE_MISMATCH_RATE = "PRICE_MISMATCH_RATE"
BREAKER_BROKER_FAILURE = "BROKER_FAILURE"


@dataclass(frozen=True)
class BreakerPolicy:
    name: str
    cooldown_seconds: float
    window_seconds: float
    min_samples: int
    trip_ratio: float
    clear_ratio: float


@dataclass
class BreakerState:
    tripped: bool = False
    tripped_at: float | None = None
    reason: str | None = None
    last_transition_at: float | None = None
    last_evidence: dict[str, Any] = field(default_factory=dict)
    samples: Deque[tuple[float, int]] = field(default_factory=deque)

    def prune(self, cutoff_epoch: float) -> None:
        while self.samples and self.samples[0][0] < cutoff_epoch:
            self.samples.popleft()

    def sample_count(self) -> int:
        return int(len(self.samples))

    def unhealthy_count(self) -> int:
        return int(sum(v for _, v in self.samples))

    def unhealthy_ratio(self) -> float:
        count = self.sample_count()
        if count <= 0:
            return 0.0
        return float(self.unhealthy_count()) / float(count)


class DecisionCircuitBreakers:
    """
    Auto-recovering runtime breakers for entry/decision flows.
    These breakers pause new trading decisions while keeping runtime loops alive.
    """

    def __init__(self, *, now_fn=None) -> None:
        self.enabled = bool(getattr(cfg, "DECISION_BREAKERS_ENABLE", True))
        self._now_fn = now_fn or time.time
        self._policies: dict[str, BreakerPolicy] = {
            BREAKER_STALE_FEED: BreakerPolicy(
                name=BREAKER_STALE_FEED,
                cooldown_seconds=float(getattr(cfg, "BREAKER_STALE_FEED_COOLDOWN_SEC", 45.0)),
                window_seconds=float(getattr(cfg, "BREAKER_STALE_FEED_WINDOW_SEC", 90.0)),
                min_samples=max(1, int(getattr(cfg, "BREAKER_STALE_FEED_MIN_SAMPLES", 3))),
                trip_ratio=float(getattr(cfg, "BREAKER_STALE_FEED_TRIP_RATIO", 0.6)),
                clear_ratio=float(getattr(cfg, "BREAKER_STALE_FEED_CLEAR_RATIO", 0.2)),
            ),
            BREAKER_PRICE_MISMATCH_RATE: BreakerPolicy(
                name=BREAKER_PRICE_MISMATCH_RATE,
                cooldown_seconds=float(getattr(cfg, "BREAKER_PRICE_MISMATCH_COOLDOWN_SEC", 60.0)),
                window_seconds=float(getattr(cfg, "BREAKER_PRICE_MISMATCH_WINDOW_SEC", 120.0)),
                min_samples=max(1, int(getattr(cfg, "BREAKER_PRICE_MISMATCH_MIN_SAMPLES", 5))),
                trip_ratio=float(getattr(cfg, "BREAKER_PRICE_MISMATCH_TRIP_RATIO", 0.7)),
                clear_ratio=float(getattr(cfg, "BREAKER_PRICE_MISMATCH_CLEAR_RATIO", 0.25)),
            ),
            BREAKER_BROKER_FAILURE: BreakerPolicy(
                name=BREAKER_BROKER_FAILURE,
                cooldown_seconds=float(getattr(cfg, "BREAKER_BROKER_FAILURE_COOLDOWN_SEC", 120.0)),
                window_seconds=float(getattr(cfg, "BREAKER_BROKER_FAILURE_WINDOW_SEC", 180.0)),
                min_samples=max(1, int(getattr(cfg, "BREAKER_BROKER_FAILURE_MIN_SAMPLES", 3))),
                trip_ratio=float(getattr(cfg, "BREAKER_BROKER_FAILURE_TRIP_RATIO", 0.5)),
                clear_ratio=float(getattr(cfg, "BREAKER_BROKER_FAILURE_CLEAR_RATIO", 0.1)),
            ),
        }
        self._states: dict[str, BreakerState] = {
            name: BreakerState() for name in self._policies.keys()
        }

    def _now(self, now_ts: float | None = None) -> float:
        return float(self._now_fn() if now_ts is None else now_ts)

    def _record(self, breaker_name: str, unhealthy: bool, *, evidence: dict[str, Any] | None = None, now_ts: float | None = None) -> list[dict[str, Any]]:
        if breaker_name not in self._policies:
            return []
        policy = self._policies[breaker_name]
        state = self._states[breaker_name]
        ts_epoch = self._now(now_ts)
        state.samples.append((ts_epoch, 1 if bool(unhealthy) else 0))
        state.prune(ts_epoch - float(policy.window_seconds))
        transitions: list[dict[str, Any]] = []

        ratio = state.unhealthy_ratio()
        count = state.sample_count()
        unhealthy_count = state.unhealthy_count()
        if (not state.tripped) and count >= int(policy.min_samples) and ratio >= float(policy.trip_ratio):
            state.tripped = True
            state.tripped_at = ts_epoch
            state.last_transition_at = ts_epoch
            state.reason = f"{breaker_name}_RATIO_{ratio:.2f}"
            state.last_evidence = dict(evidence or {})
            transitions.append(
                {
                    "breaker": breaker_name,
                    "action": "TRIPPED",
                    "tripped_at": ts_epoch,
                    "reason": state.reason,
                    "window_samples": count,
                    "window_unhealthy": unhealthy_count,
                    "window_unhealthy_ratio": ratio,
                }
            )
        elif state.tripped:
            cooldown_elapsed = bool(
                state.tripped_at is not None
                and (ts_epoch - float(state.tripped_at)) >= float(policy.cooldown_seconds)
            )
            healthy_enough = bool(count >= int(policy.min_samples) and ratio <= float(policy.clear_ratio))
            if cooldown_elapsed and healthy_enough:
                prev_reason = state.reason
                state.tripped = False
                state.reason = None
                state.tripped_at = None
                state.last_transition_at = ts_epoch
                state.last_evidence = dict(evidence or {})
                transitions.append(
                    {
                        "breaker": breaker_name,
                        "action": "CLEARED",
                        "cleared_at": ts_epoch,
                        "previous_reason": prev_reason,
                        "window_samples": count,
                        "window_unhealthy": unhealthy_count,
                        "window_unhealthy_ratio": ratio,
                    }
                )
        return transitions

    def observe_stale_feed(self, unhealthy: bool, *, evidence: dict[str, Any] | None = None, now_ts: float | None = None) -> list[dict[str, Any]]:
        return self._record(BREAKER_STALE_FEED, unhealthy, evidence=evidence, now_ts=now_ts)

    def observe_price_mismatch(self, unhealthy: bool, *, evidence: dict[str, Any] | None = None, now_ts: float | None = None) -> list[dict[str, Any]]:
        return self._record(BREAKER_PRICE_MISMATCH_RATE, unhealthy, evidence=evidence, now_ts=now_ts)

    def observe_broker_failure(self, unhealthy: bool, *, evidence: dict[str, Any] | None = None, now_ts: float | None = None) -> list[dict[str, Any]]:
        return self._record(BREAKER_BROKER_FAILURE, unhealthy, evidence=evidence, now_ts=now_ts)

    def should_block_decisions(self, *, now_ts: float | None = None) -> tuple[bool, list[str]]:
        now_epoch = self._now(now_ts)
        if not self.enabled:
            return False, []
        reasons: list[str] = []
        for breaker_name, policy in self._policies.items():
            state = self._states[breaker_name]
            state.prune(now_epoch - float(policy.window_seconds))
            if state.tripped:
                reasons.append(breaker_name)
        return bool(reasons), reasons

    def snapshot(self, *, now_ts: float | None = None) -> dict[str, Any]:
        now_epoch = self._now(now_ts)
        payload: dict[str, Any] = {"enabled": bool(self.enabled), "ts_epoch": now_epoch, "breakers": {}}
        blocked, blocked_reasons = self.should_block_decisions(now_ts=now_epoch)
        payload["blocked"] = bool(blocked)
        payload["blocked_reasons"] = list(blocked_reasons)
        for breaker_name, policy in self._policies.items():
            state = self._states[breaker_name]
            state.prune(now_epoch - float(policy.window_seconds))
            ratio = state.unhealthy_ratio()
            count = state.sample_count()
            cooldown_elapsed = bool(
                (not state.tripped)
                or (
                    state.tripped_at is not None
                    and (now_epoch - float(state.tripped_at)) >= float(policy.cooldown_seconds)
                )
            )
            payload["breakers"][breaker_name] = {
                "tripped": bool(state.tripped),
                "tripped_at": state.tripped_at,
                "reason": state.reason,
                "last_transition_at": state.last_transition_at,
                "cooldown_seconds": float(policy.cooldown_seconds),
                "window_seconds": float(policy.window_seconds),
                "min_samples": int(policy.min_samples),
                "trip_ratio": float(policy.trip_ratio),
                "clear_ratio": float(policy.clear_ratio),
                "window_samples": count,
                "window_unhealthy": state.unhealthy_count(),
                "window_unhealthy_ratio": ratio,
                "clear_conditions": {
                    "cooldown_elapsed": cooldown_elapsed,
                    "window_healthy_enough": bool(
                        count >= int(policy.min_samples) and ratio <= float(policy.clear_ratio)
                    ),
                },
                "last_evidence": dict(state.last_evidence or {}),
            }
        return payload
