from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.analytics.gate_scorecard import build_gate_scorecard
from core.analytics.schema import GateDecision, TradeIntentEvent, TradeOutcome


def _ts_ms() -> int:
    dt = datetime.fromisoformat("2026-02-27T09:30:00+05:30").astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def test_build_gate_scorecard_counts_blocked_would_win(tmp_path: Path):
    ts_ms = _ts_ms()
    trade_key = "NIFTY|2026-03-05|22500|CE|BUY|unit"
    event = TradeIntentEvent(
        trade_key=trade_key,
        event_id="evt_gate_1",
        intent="rejected",
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=22500.0,
        option_type="CE",
        side="BUY",
        source="unit",
        reject_reason="spread_guard",
        gate_decisions=(GateDecision(gate_name="spread_guard", passed=False, reason="spread_guard"),),
        metrics_snapshot={},
    )
    outcome = TradeOutcome(
        trade_key=trade_key,
        event_id=event.event_id,
        outcome="hit_target",
        ts_epoch_ms=ts_ms + 60_000,
        symbol="NIFTY",
        mfe_points=8.0,
        mae_points=1.0,
        exec_feasible=True,
        source="unit",
    )

    report = build_gate_scorecard(
        "2026-02-27",
        events=[event],
        outcomes=[outcome],
        output_path=tmp_path / "gate_scorecard.json",
    )

    assert report["total_events"] == 1
    assert report["by_gate_reject_reason"][0]["blocked_would_win"] == 1
    assert (tmp_path / "gate_scorecard.json").exists()
