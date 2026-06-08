from __future__ import annotations

import time
from dataclasses import dataclass

from config import config as cfg


ACTION_OK = "OK"
ACTION_DEGRADE_EXIT_ONLY = "DEGRADE_EXIT_ONLY"
ACTION_HALT_ALL = "HALT_ALL"
ACTION_COOLDOWN = "COOLDOWN"
ACTION_FEED_BLOCKED = "FEED_BLOCKED"


@dataclass(frozen=True)
class LatencyGuardResult:
    action: str
    reason: str
    blocks_new_entries: bool
    blocks_non_emergency_exits: bool
    cooldown_until_ts: float
    stats: dict


class LatencyGuard:
    def __init__(
        self,
        *,
        max_p95_total_ms: float | None = None,
        max_p95_decision_ms: float | None = None,
        sustained_windows: int | None = None,
        recovery_windows: int | None = None,
        cooldown_sec: float | None = None,
        halt_on_breach: bool | None = None,
        severe_multiplier: float = 2.0,
    ) -> None:
        self.max_p95_total_ms = float(
            getattr(cfg, "MAX_P95_TOTAL_MS", 120.0) if max_p95_total_ms is None else max_p95_total_ms
        )
        self.max_p95_decision_ms = float(
            getattr(cfg, "MAX_P95_DECISION_MS", self.max_p95_total_ms * 0.75)
            if max_p95_decision_ms is None
            else max_p95_decision_ms
        )
        self.sustained_windows = max(
            1,
            int(getattr(cfg, "SUSTAINED_WINDOWS", 3) if sustained_windows is None else sustained_windows),
        )
        self.recovery_windows = max(
            1,
            int(
                getattr(cfg, "LATENCY_GUARD_RECOVERY_WINDOWS", self.sustained_windows)
                if recovery_windows is None
                else recovery_windows
            ),
        )
        self.cooldown_sec = max(
            0.0, float(getattr(cfg, "EXIT_ONLY_COOLDOWN_S", 30.0) if cooldown_sec is None else cooldown_sec)
        )
        self.halt_on_breach = bool(
            getattr(cfg, "HALT_ON_BREACH", True) if halt_on_breach is None else halt_on_breach
        )
        self.severe_multiplier = max(1.0, float(severe_multiplier))
        self._cooldown_until_ts = 0.0
        self._active_action = ACTION_OK
        self._active_reason = "latency_within_budget"
        self._healthy_recovery_windows = 0

    def _result(
        self,
        *,
        action: str,
        reason: str,
        monitor_stats: dict,
    ) -> LatencyGuardResult:
        action_upper = str(action or ACTION_OK).upper()
        blocks_new_entries = action_upper in {ACTION_COOLDOWN, ACTION_DEGRADE_EXIT_ONLY, ACTION_HALT_ALL, ACTION_FEED_BLOCKED}
        blocks_non_emergency_exits = action_upper == ACTION_HALT_ALL
        stats = dict(monitor_stats or {})
        stats["guard"] = {
            "active_action": str(self._active_action or ACTION_OK),
            "active_reason": str(self._active_reason or "latency_within_budget"),
            "healthy_recovery_windows": int(self._healthy_recovery_windows),
            "recovery_windows_required": int(self.recovery_windows),
            "cooldown_until_ts": float(self._cooldown_until_ts or 0.0),
        }
        return LatencyGuardResult(
            action=action_upper,
            reason=str(reason),
            blocks_new_entries=blocks_new_entries,
            blocks_non_emergency_exits=blocks_non_emergency_exits,
            cooldown_until_ts=self._cooldown_until_ts,
            stats=stats,
        )

    def evaluate(self, monitor_stats: dict, market_open: bool, now_ts: float | None = None, canonical_feed_truth: dict | None = None) -> LatencyGuardResult:
        now_epoch = float(now_ts if now_ts is not None else time.time())
        stages = dict((monitor_stats or {}).get("stages") or {})
        canonical_state = str((canonical_feed_truth or {}).get("state") or "").strip().upper()
        if canonical_state in {"DEGRADED", "RECOVERY_BLOCKED", "RESTART_REQUIRED"}:
            self._healthy_recovery_windows = 0
            self._active_action = ACTION_FEED_BLOCKED
            self._active_reason = "canonical_feed_truth_not_healthy"
            return self._result(
                action=ACTION_FEED_BLOCKED,
                reason="canonical_feed_truth_not_healthy",
                monitor_stats=monitor_stats or {},
            )

        breach = dict((monitor_stats or {}).get("breach") or {})
        p95_total = float((stages.get("total_loop") or {}).get("p95_ms") or 0.0)
        p95_decision = float((stages.get("decision_build") or {}).get("p95_ms") or 0.0)
        sustained_total = bool(
            breach.get("sustained_total_breach")
            or int(breach.get("consecutive_total_windows") or 0) >= int(self.sustained_windows)
        )
        sustained_decision = bool(
            breach.get("sustained_decision_breach")
            or int(breach.get("consecutive_decision_windows") or 0) >= int(self.sustained_windows)
        )
        immediate_total = bool(breach.get("p95_total_breach") or p95_total > self.max_p95_total_ms)
        immediate_decision = bool(
            breach.get("p95_decision_breach") or p95_decision > self.max_p95_decision_ms
        )
        severe = bool(
            p95_total >= (self.max_p95_total_ms * self.severe_multiplier)
            or p95_decision >= (self.max_p95_decision_ms * self.severe_multiplier)
        )
        healthy_window = not any((immediate_total, immediate_decision, sustained_total, sustained_decision))

        if not bool(market_open):
            self._cooldown_until_ts = 0.0
            self._active_action = ACTION_OK
            self._active_reason = "market_closed"
            self._healthy_recovery_windows = 0
            return self._result(
                action=ACTION_OK,
                reason="market_closed",
                monitor_stats=monitor_stats or {},
            )

        if self._active_action in {ACTION_DEGRADE_EXIT_ONLY, ACTION_HALT_ALL}:
            if healthy_window:
                self._healthy_recovery_windows += 1
                if self._healthy_recovery_windows >= int(self.recovery_windows):
                    self._active_action = ACTION_OK
                    self._active_reason = "latency_within_budget"
                    self._healthy_recovery_windows = 0
                    self._cooldown_until_ts = 0.0
                    return self._result(
                        action=ACTION_OK,
                        reason="latency_recovered",
                        monitor_stats=monitor_stats or {},
                    )
            else:
                self._healthy_recovery_windows = 0
            return self._result(
                action=self._active_action,
                reason=self._active_reason,
                monitor_stats=monitor_stats or {},
            )

        if now_epoch < self._cooldown_until_ts:
            return self._result(
                action=ACTION_COOLDOWN,
                reason="latency_cooldown_active",
                monitor_stats=monitor_stats or {},
            )

        if sustained_total or sustained_decision:
            if self.cooldown_sec > 0:
                self._cooldown_until_ts = now_epoch + self.cooldown_sec
            self._healthy_recovery_windows = 0
            if severe and self.halt_on_breach:
                self._active_action = ACTION_HALT_ALL
                self._active_reason = "latency_sustained_severe_breach"
                return self._result(
                    action=ACTION_HALT_ALL,
                    reason="latency_sustained_severe_breach",
                    monitor_stats=monitor_stats or {},
                )
            self._active_action = ACTION_DEGRADE_EXIT_ONLY
            self._active_reason = "latency_sustained_breach"
            return self._result(
                action=ACTION_DEGRADE_EXIT_ONLY,
                reason="latency_sustained_breach",
                monitor_stats=monitor_stats or {},
            )

        if immediate_total or immediate_decision:
            if self.cooldown_sec > 0:
                self._cooldown_until_ts = now_epoch + self.cooldown_sec
                self._healthy_recovery_windows = 0
                return self._result(
                    action=ACTION_COOLDOWN,
                    reason="latency_transient_breach",
                    monitor_stats=monitor_stats or {},
                )

        self._healthy_recovery_windows = 0
        return self._result(
            action=ACTION_OK,
            reason="latency_within_budget",
            monitor_stats=monitor_stats or {},
        )
