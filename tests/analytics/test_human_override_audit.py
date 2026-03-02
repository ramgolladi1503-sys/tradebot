from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.analytics.human_override_audit import build_human_override_audit
from core.analytics.schema import TradeIntentEvent, TradeOutcome


def _ts_ms() -> int:
    dt = datetime.fromisoformat("2026-02-27T12:30:00+05:30").astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def test_build_human_override_audit_smoke(tmp_path: Path):
    ts_ms = _ts_ms()
    trade_key = "SENSEX|2026-03-05|78000|CE|BUY|unit"
    event = TradeIntentEvent(
        trade_key=trade_key,
        event_id="evt_override_1",
        intent="accepted",
        ts_epoch_ms=ts_ms,
        symbol="SENSEX",
        side="BUY",
        source="unit",
        metrics_snapshot={"manual_override_used": True, "strategy_id": "orb"},
    )
    outcome = TradeOutcome(
        trade_key=trade_key,
        event_id=event.event_id,
        outcome="hit_target",
        ts_epoch_ms=ts_ms + 180_000,
        symbol="SENSEX",
        mfe_points=8.0,
        mae_points=1.0,
        exec_feasible=True,
        source="unit",
    )

    report = build_human_override_audit(
        "2026-02-27",
        events=[event],
        outcomes=[outcome],
        output_path=tmp_path / "human_override_audit.json",
    )

    assert report["counts"]["matched_events"] == 1
    assert report["counts"]["manual_overrides"] == 1
