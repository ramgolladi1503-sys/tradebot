from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.analytics.schema import TradeOutcome
from core.analytics.target_sl_calibration import build_target_sl_calibration_report


def _ts_ms() -> int:
    dt = datetime.fromisoformat("2026-02-27T11:15:00+05:30").astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def test_build_target_sl_calibration_report_smoke(tmp_path: Path):
    ts_ms = _ts_ms()
    trade_key = "NIFTY|2026-03-05|22500|CE|BUY|unit"
    event = {
        "trade_key": trade_key,
        "event_id": "evt_cal_1",
        "intent": "accepted",
        "ts_epoch_ms": ts_ms,
        "symbol": "NIFTY",
        "source": "unit",
        "entry": 100.0,
        "target": 105.0,
        "stop": 96.0,
    }
    outcome = TradeOutcome(
        trade_key=trade_key,
        event_id="evt_cal_1",
        outcome="hit_target",
        ts_epoch_ms=ts_ms + 120_000,
        symbol="NIFTY",
        mfe_points=7.0,
        mae_points=2.0,
        exec_feasible=True,
        source="unit",
    )

    report = build_target_sl_calibration_report(
        "2026-02-27",
        events=[event],
        outcomes=[outcome],
        output_path=tmp_path / "target_sl_calibration.json",
    )

    assert report["matched_outcomes"] == 1
    assert report["target_metrics"]["samples"] == 1
