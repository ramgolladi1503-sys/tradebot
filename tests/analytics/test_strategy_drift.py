from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.analytics.schema import TradeIntentEvent, TradeOutcome
from core.analytics.strategy_drift import build_strategy_drift_report


def _ts_ms() -> int:
    dt = datetime.fromisoformat("2026-02-27T11:00:00+05:30").astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def test_build_strategy_drift_report_smoke(tmp_path: Path):
    ts_ms = _ts_ms()
    trade_key = "SENSEX|2026-03-05|78000|PE|SELL|unit"
    event = TradeIntentEvent(
        trade_key=trade_key,
        event_id="evt_drift_1",
        intent="accepted",
        ts_epoch_ms=ts_ms,
        symbol="SENSEX",
        side="SELL",
        source="unit",
        metrics_snapshot={"strategy_id": "orb", "regime": "RANGE"},
    )
    outcome = TradeOutcome(
        trade_key=trade_key,
        event_id=event.event_id,
        outcome="hit_sl",
        ts_epoch_ms=ts_ms + 180_000,
        symbol="SENSEX",
        mfe_points=2.0,
        mae_points=6.0,
        exec_feasible=True,
        source="unit",
    )

    report = build_strategy_drift_report(
        "2026-02-27",
        events=[event],
        outcomes=[outcome],
        recent_days=1,
        baseline_days=1,
        baseline_excludes_recent=False,
        min_group_trades=1,
        output_path=tmp_path / "strategy_drift.json",
    )

    assert report["counts"]["matched_rows"] == 1
    assert report["counts"]["groups"] == 1
    assert (tmp_path / "strategy_drift.json").exists()
