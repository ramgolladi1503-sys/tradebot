from __future__ import annotations

from collections import deque
from statistics import mean
from typing import Dict

from config import config as cfg


LATENCY_STAGES = ("feature_build", "decision_build", "execution_route", "total_loop")


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(float(v) for v in values)
    idx = int(round((len(ordered) - 1) * float(pct)))
    idx = max(0, min(idx, len(ordered) - 1))
    return float(ordered[idx])


class LatencyMonitor:
    """
    Rolling latency monitor for orchestrator stages.
    """

    def __init__(
        self,
        *,
        window_size: int | None = None,
        max_p95_total_ms: float | None = None,
        max_p95_decision_ms: float | None = None,
        sustained_windows: int | None = None,
    ) -> None:
        self.window_size = max(
            5,
            int(getattr(cfg, "LATENCY_MONITOR_WINDOW_SIZE", 120) if window_size is None else window_size),
        )
        self.max_p95_total_ms = _to_float(
            getattr(cfg, "MAX_P95_TOTAL_MS", 120.0) if max_p95_total_ms is None else max_p95_total_ms,
            120.0,
        )
        self.max_p95_decision_ms = _to_float(
            getattr(cfg, "MAX_P95_DECISION_MS", self.max_p95_total_ms * 0.75)
            if max_p95_decision_ms is None
            else max_p95_decision_ms,
            self.max_p95_total_ms * 0.75,
        )
        self.sustained_windows = max(
            1,
            int(getattr(cfg, "SUSTAINED_WINDOWS", 3) if sustained_windows is None else sustained_windows),
        )
        self._samples: Dict[str, deque[float]] = {
            stage: deque(maxlen=self.window_size) for stage in LATENCY_STAGES
        }
        self._consecutive_total_breach_windows = 0
        self._consecutive_decision_breach_windows = 0

    def record(self, stage: str, dt_ms: float) -> None:
        key = str(stage or "").strip()
        if key not in self._samples:
            raise ValueError(f"unknown_latency_stage:{key}")
        self._samples[key].append(max(0.0, _to_float(dt_ms)))

    def tick_end(self, total_ms: float) -> dict:
        self.record("total_loop", total_ms)
        stats = self.snapshot_stats()
        total_p95 = _to_float((stats.get("stages", {}).get("total_loop") or {}).get("p95_ms"), 0.0)
        decision_p95 = _to_float((stats.get("stages", {}).get("decision_build") or {}).get("p95_ms"), 0.0)
        if total_p95 > self.max_p95_total_ms:
            self._consecutive_total_breach_windows += 1
        else:
            self._consecutive_total_breach_windows = 0
        if decision_p95 > self.max_p95_decision_ms:
            self._consecutive_decision_breach_windows += 1
        else:
            self._consecutive_decision_breach_windows = 0
        return self.snapshot_stats()

    def snapshot_stats(self) -> dict:
        stage_stats: dict[str, dict] = {}
        for stage, bucket in self._samples.items():
            vals = list(bucket)
            stage_stats[stage] = {
                "count": int(len(vals)),
                "p50_ms": _percentile(vals, 0.50),
                "p95_ms": _percentile(vals, 0.95),
                "mean_ms": float(mean(vals)) if vals else 0.0,
            }
        total_p95 = _to_float(stage_stats.get("total_loop", {}).get("p95_ms"), 0.0)
        decision_p95 = _to_float(stage_stats.get("decision_build", {}).get("p95_ms"), 0.0)
        return {
            "window_size": int(self.window_size),
            "thresholds": {
                "max_p95_total_ms": float(self.max_p95_total_ms),
                "max_p95_decision_ms": float(self.max_p95_decision_ms),
                "sustained_windows": int(self.sustained_windows),
            },
            "stages": stage_stats,
            "breach": {
                "p95_total_breach": bool(total_p95 > self.max_p95_total_ms),
                "p95_decision_breach": bool(decision_p95 > self.max_p95_decision_ms),
                "consecutive_total_windows": int(self._consecutive_total_breach_windows),
                "consecutive_decision_windows": int(self._consecutive_decision_breach_windows),
                "sustained_total_breach": bool(
                    self._consecutive_total_breach_windows >= int(self.sustained_windows)
                ),
                "sustained_decision_breach": bool(
                    self._consecutive_decision_breach_windows >= int(self.sustained_windows)
                ),
            },
        }
