from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.analytics.regime_analysis import build_regime_analysis
from core.analytics.schema import GateDecision, TradeIntentEvent, TradeOutcome


def _ts_ms() -> int:
    dt = datetime.fromisoformat("2026-02-27T10:00:00+05:30").astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def test_build_regime_analysis_groups_by_regime(tmp_path: Path):
    ts_ms = _ts_ms()
    trade_key = "BANKNIFTY|2026-03-05|49000|CE|BUY|unit"
    event = TradeIntentEvent(
        trade_key=trade_key,
        event_id="evt_regime_1",
        intent="rejected",
        ts_epoch_ms=ts_ms,
        symbol="BANKNIFTY",
        source="unit",
        reject_reason="premium_band_fail",
        gate_decisions=(GateDecision(gate_name="premium_band", passed=False, reason="premium_band_fail"),),
        metrics_snapshot={"regime": "TREND"},
    )
    outcome = TradeOutcome(
        trade_key=trade_key,
        event_id=event.event_id,
        outcome="hit_target",
        ts_epoch_ms=ts_ms + 120_000,
        symbol="BANKNIFTY",
        mfe_points=10.0,
        mae_points=2.0,
        exec_feasible=True,
        source="unit",
    )

    report = build_regime_analysis(
        "2026-02-27",
        events=[event],
        outcomes=[outcome],
        output_path=tmp_path / "regime_analysis.json",
    )

    assert report["total_events"] == 1
    assert report["matched_outcomes"] == 1
    assert report["regime_splits"][0]["regime"] == "TREND"
