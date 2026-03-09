from __future__ import annotations

import time
from dataclasses import dataclass

from config import config as cfg


ACTION_OK = "OK"
ACTION_DEGRADE_EXIT_ONLY = "DEGRADE_EXIT_ONLY"
ACTION_HALT_ALL = "HALT_ALL"
ACTION_COOLDOWN = "COOLDOWN"


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
        self.cooldown_sec = max(
            0.0, float(getattr(cfg, "EXIT_ONLY_COOLDOWN_S", 30.0) if cooldown_sec is None else cooldown_sec)
        )
        self.halt_on_breach = bool(
            getattr(cfg, "HALT_ON_BREACH", True) if halt_on_breach is None else halt_on_breach
        )
        self.severe_multiplier = max(1.0, float(severe_multiplier))
        self._cooldown_until_ts = 0.0

    def evaluate(self, monitor_stats: dict, market_open: bool, now_ts: float | None = None) -> LatencyGuardResult:
        now_epoch = float(now_ts if now_ts is not None else time.time())
        stages = dict((monitor_stats or {}).get("stages") or {})
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

        if now_epoch < self._cooldown_until_ts:
            return LatencyGuardResult(
                action=ACTION_COOLDOWN,
                reason="latency_cooldown_active",
                blocks_new_entries=True,
                blocks_non_emergency_exits=False,
                cooldown_until_ts=self._cooldown_until_ts,
                stats=monitor_stats or {},
            )

        if not bool(market_open):
            return LatencyGuardResult(
                action=ACTION_OK,
                reason="market_closed",
                blocks_new_entries=False,
                blocks_non_emergency_exits=False,
                cooldown_until_ts=self._cooldown_until_ts,
                stats=monitor_stats or {},
            )

        if sustained_total or sustained_decision:
            if self.cooldown_sec > 0:
                self._cooldown_until_ts = now_epoch + self.cooldown_sec
            if severe and self.halt_on_breach:
                return LatencyGuardResult(
                    action=ACTION_HALT_ALL,
                    reason="latency_sustained_severe_breach",
                    blocks_new_entries=True,
                    blocks_non_emergency_exits=True,
                    cooldown_until_ts=self._cooldown_until_ts,
                    stats=monitor_stats or {},
                )
            return LatencyGuardResult(
                action=ACTION_DEGRADE_EXIT_ONLY,
                reason="latency_sustained_breach",
                blocks_new_entries=True,
                blocks_non_emergency_exits=False,
                cooldown_until_ts=self._cooldown_until_ts,
                stats=monitor_stats or {},
            )

        if immediate_total or immediate_decision:
            if self.cooldown_sec > 0:
                self._cooldown_until_ts = now_epoch + self.cooldown_sec
                return LatencyGuardResult(
                    action=ACTION_COOLDOWN,
                    reason="latency_transient_breach",
                    blocks_new_entries=True,
                    blocks_non_emergency_exits=False,
                    cooldown_until_ts=self._cooldown_until_ts,
                    stats=monitor_stats or {},
                )

        return LatencyGuardResult(
            action=ACTION_OK,
            reason="latency_within_budget",
            blocks_new_entries=False,
            blocks_non_emergency_exits=False,
            cooldown_until_ts=self._cooldown_until_ts,
            stats=monitor_stats or {},
        )
