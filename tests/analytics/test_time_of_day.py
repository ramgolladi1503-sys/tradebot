from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.analytics.schema import TradeIntentEvent, TradeOutcome
from core.analytics.time_of_day import bucket_for_timestamp_ms, build_time_of_day_report


def _ts_ms(local_iso: str) -> int:
    dt = datetime.fromisoformat(local_iso).astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def test_bucket_for_timestamp_ms_open_window():
    assert bucket_for_timestamp_ms(_ts_ms("2026-02-27T09:20:00+05:30"), None) == "OPEN"


def test_build_time_of_day_report_smoke(tmp_path: Path):
    ts_ms = _ts_ms("2026-02-27T09:35:00+05:30")
    trade_key = "NIFTY|2026-03-05|22500|CE|BUY|unit"
    event = TradeIntentEvent(
        trade_key=trade_key,
        event_id="evt_tod_1",
        intent="accepted",
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        source="unit",
    )
    outcome = TradeOutcome(
        trade_key=trade_key,
        event_id=event.event_id,
        outcome="hit_target",
        ts_epoch_ms=ts_ms + 60_000,
        symbol="NIFTY",
        exec_feasible=True,
        source="unit",
    )

    report = build_time_of_day_report(
        "2026-02-27",
        events=[event],
        outcomes=[outcome],
        output_path=tmp_path / "time_of_day.json",
    )

    assert report["total_events"] == 1
    assert report["buckets"][0]["bucket"] in {"MID", "OPEN", "LATE", "EXPIRY_SPECIAL"}
