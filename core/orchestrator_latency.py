from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from config import config as cfg


def count_jsonl_rows(path: Path) -> int:
    try:
        if not path.exists():
            return 0
        return sum(1 for _ in path.open("r", encoding="utf-8"))
    except Exception:
        return 0


def build_cycle_latency_snapshot(*, cycle_started_at: float | None = None, cycle_completed_at: float | None = None, feed_epoch: float | None = None) -> dict:
    return {
        "cycle_started_at": cycle_started_at,
        "cycle_completed_at": cycle_completed_at,
        "cycle_elapsed_ms": None if cycle_started_at is None or cycle_completed_at is None else max(0.0, (cycle_completed_at - cycle_started_at) * 1000.0),
        "feed_epoch": feed_epoch,
    }


def latency_budget_config(*, execution_mode: str | None) -> dict[str, float | int | bool | str]:
    mode = str(execution_mode or getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    return {"execution_mode": mode, "max_cycle_ms": 1000.0 if mode == "SIM" else 500.0, "skip_trade_builder": False, "skip_maintenance": False}


def should_skip_trade_builder_for_latency_guard(latency_state: Mapping[str, Any] | None, latency_stats: Mapping[str, Any] | None) -> bool:
    return bool((latency_state or {}).get("skip_trade_builder") or (latency_stats or {}).get("skip_trade_builder"))


def should_skip_background_maintenance_for_latency_guard(latency_state: Mapping[str, Any] | None, latency_stats: Mapping[str, Any] | None) -> bool:
    return bool((latency_state or {}).get("skip_maintenance") or (latency_stats or {}).get("skip_maintenance"))


def latency_guard_metric_context(latency_state: Mapping[str, Any] | None, latency_stats: Mapping[str, Any] | None) -> dict[str, Any]:
    return {"latency_state": dict(latency_state or {}), "latency_stats": dict(latency_stats or {})}


def min_breadth_target(execution_mode: str | None) -> int:
    mode = str(execution_mode or getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    return 3 if mode == "LIVE" else 1


def build_min_breadth_backfill(*, market_data: list[dict] | None = None) -> list[dict]:
    return list(market_data or [])


def is_recoverable_depth_ws_startup_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}:{exc}".lower()
    return any(token in text for token in ("timeout", "tempor", "connection"))


def top_blockers_payload(blocker_counts: Counter, limit: int = 5) -> list[dict]:
    return [{"reason": reason, "count": count} for reason, count in blocker_counts.most_common(limit)]


