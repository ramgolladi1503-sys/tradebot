from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.analytics.feed_quality_correlation import build_feed_quality_correlation_report
from core.analytics.schema import TradeIntentEvent, TradeOutcome


def _ts_ms() -> int:
    dt = datetime.fromisoformat("2026-02-27T12:00:00+05:30").astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def test_build_feed_quality_correlation_report_smoke(tmp_path: Path):
    ts_ms = _ts_ms()
    trade_key = "BANKNIFTY|2026-03-05|49000|CE|BUY|unit"
    event = TradeIntentEvent(
        trade_key=trade_key,
        event_id="evt_feed_1",
        intent="rejected",
        ts_epoch_ms=ts_ms,
        symbol="BANKNIFTY",
        source="unit",
        reject_reason="spread_guard",
        feed_state="DEGRADED",
        metrics_snapshot={"quote_age_sec": 2.4, "spread_pct": 0.02},
    )
    outcome = TradeOutcome(
        trade_key=trade_key,
        event_id=event.event_id,
        outcome="hit_sl",
        ts_epoch_ms=ts_ms + 120_000,
        symbol="BANKNIFTY",
        mfe_points=2.0,
        mae_points=6.0,
        exec_feasible=True,
        source="unit",
    )
    quote_rows = [
        {
            "event_id": event.event_id,
            "trade_key": trade_key,
            "symbol": "BANKNIFTY",
            "timestamp_epoch_ms": ts_ms,
            "quote_age_sec": 2.4,
            "spread_pct": 0.02,
            "feed_state": "DEGRADED",
            "source": "snapshot",
        }
    ]

    report = build_feed_quality_correlation_report(
        "2026-02-27",
        events=[event],
        outcomes=[outcome],
        quote_rows=quote_rows,
        output_path=tmp_path / "feed_quality_correlation.json",
    )

    assert report["counts"]["rows"] == 1
    assert report["bucketed_outcomes"]["feed_state"][0]["feed_state"] == "DEGRADED"
