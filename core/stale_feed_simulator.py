from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class FeedTick:
    symbol: str
    ltp: float | None
    timestamp_epoch: float


def classify_feed_freshness(
    *,
    now_epoch: float,
    tick_timestamp_epoch: float | None,
    sla_threshold_sec: float,
) -> dict:
    if tick_timestamp_epoch is None:
        return {
            "status": "stale",
            "blocker": "MISSING_TICK_TIMESTAMP",
            "age_sec": None,
            "sla_threshold_sec": float(sla_threshold_sec),
        }

    age_sec = float(now_epoch) - float(tick_timestamp_epoch)
    if age_sec < 0:
        return {
            "status": "invalid",
            "blocker": "TICK_FROM_FUTURE",
            "age_sec": age_sec,
            "sla_threshold_sec": float(sla_threshold_sec),
        }

    if age_sec > float(sla_threshold_sec):
        return {
            "status": "stale",
            "blocker": "STALE_TICK",
            "age_sec": age_sec,
            "sla_threshold_sec": float(sla_threshold_sec),
        }

    return {
        "status": "fresh",
        "blocker": None,
        "age_sec": age_sec,
        "sla_threshold_sec": float(sla_threshold_sec),
    }


def simulate_stale_feed(
    ticks: Iterable[FeedTick],
    *,
    now_epoch: float,
    sla_threshold_sec: float,
) -> dict:
    rows = []
    stale_symbols = []
    invalid_symbols = []
    missing_ltp_symbols = []

    for tick in ticks:
        freshness = classify_feed_freshness(
            now_epoch=now_epoch,
            tick_timestamp_epoch=tick.timestamp_epoch,
            sla_threshold_sec=sla_threshold_sec,
        )
        row = {
            "symbol": tick.symbol,
            "ltp": tick.ltp,
            **freshness,
        }
        rows.append(row)

        if tick.ltp is None:
            missing_ltp_symbols.append(tick.symbol)
        if freshness["status"] == "stale":
            stale_symbols.append(tick.symbol)
        if freshness["status"] == "invalid":
            invalid_symbols.append(tick.symbol)

    blocked = bool(stale_symbols or invalid_symbols or missing_ltp_symbols)
    blockers = []
    if stale_symbols:
        blockers.append("STALE_TICK")
    if invalid_symbols:
        blockers.append("TICK_FROM_FUTURE")
    if missing_ltp_symbols:
        blockers.append("MISSING_LTP")

    return {
        "ok": not blocked,
        "blocked": blocked,
        "blockers": blockers,
        "stale_symbols": stale_symbols,
        "invalid_symbols": invalid_symbols,
        "missing_ltp_symbols": missing_ltp_symbols,
        "rows": rows,
    }
