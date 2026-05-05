from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class FeedIntegrityResult:
    score: float
    status: str
    execution_allowed: bool
    primary_blocker: str
    reasons: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def evaluate_feed_integrity(
    *,
    ws_connected: bool | None,
    tick_age_sec: float | None,
    depth_age_sec: float | None,
    queue_pressure_pct: float | None = None,
    ingest_lag_sec: float | None = None,
    fallback_used: bool = False,
    market_open: bool = True,
    max_tick_age_sec: float = 2.0,
    max_depth_age_sec: float = 3.0,
    max_ingest_lag_sec: float = 0.5,
    max_queue_pressure_pct: float = 70.0,
) -> FeedIntegrityResult:
    """Return deterministic feed quality decision for live execution.

    This is intentionally fail-closed. Advisory output can still be shown elsewhere,
    but live execution should only pass when the data path is fresh and real.
    """
    reasons: list[str] = []
    score = 1.0

    if not market_open:
        return FeedIntegrityResult(
            score=0.0,
            status="MARKET_CLOSED",
            execution_allowed=False,
            primary_blocker="market_closed",
            reasons=["market_closed"],
        )

    if ws_connected is not True:
        reasons.append("ws_disconnected")
        score -= 0.35

    if fallback_used:
        reasons.append("fallback_used")
        score -= 0.45

    tick_age = _safe_float(tick_age_sec, 999999.0)
    if tick_age > float(max_tick_age_sec):
        reasons.append("tick_stale")
        score -= 0.30

    depth_age = _safe_float(depth_age_sec, 999999.0)
    if depth_age > float(max_depth_age_sec):
        reasons.append("depth_stale")
        score -= 0.20

    lag = _safe_float(ingest_lag_sec, 0.0)
    if lag > float(max_ingest_lag_sec):
        reasons.append("ingest_lag_high")
        score -= 0.15

    pressure = _safe_float(queue_pressure_pct, 0.0)
    if pressure > float(max_queue_pressure_pct):
        reasons.append("queue_pressure_high")
        score -= 0.15

    score = max(0.0, min(1.0, round(score, 4)))
    execution_allowed = not reasons and score >= 0.95
    status = "OK" if execution_allowed else ("BLOCKED" if score < 0.70 else "DEGRADED")
    primary_blocker = "ok" if execution_allowed else (reasons[0] if reasons else "score_below_live_threshold")

    return FeedIntegrityResult(
        score=score,
        status=status,
        execution_allowed=execution_allowed,
        primary_blocker=primary_blocker,
        reasons=reasons,
    )


def hard_block_live_execution(feed: dict[str, Any]) -> tuple[bool, str]:
    """Small adapter for execution gates.

    Returns (blocked, reason). Use this before order placement.
    """
    result = evaluate_feed_integrity(
        ws_connected=feed.get("ws_connected"),
        tick_age_sec=feed.get("tick_age_sec"),
        depth_age_sec=feed.get("depth_age_sec"),
        queue_pressure_pct=feed.get("queue_pressure_pct"),
        ingest_lag_sec=feed.get("ingest_lag_sec"),
        fallback_used=bool(feed.get("fallback_used", False)),
        market_open=bool(feed.get("market_open", True)),
    )
    return (not result.execution_allowed), result.primary_blocker
