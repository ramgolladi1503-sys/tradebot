from __future__ import annotations

from datetime import datetime
import json

from core.analytics.schema import TradeIntentEvent, TradeOutcome
from core.analytics.strategy_drift import build_strategy_drift_report


def _ts_ms_ist(day: str, hh: int = 10, mm: int = 0) -> int:
    dt = datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:00+05:30")
    return int(dt.timestamp() * 1000.0)


def _event(
    *,
    event_id: str,
    trade_key: str,
    day: str,
    strategy_id: str,
    regime: str,
) -> TradeIntentEvent:
    return TradeIntentEvent(
        trade_key=trade_key,
        event_id=event_id,
        intent="advisory",
        ts_epoch_ms=_ts_ms_ist(day),
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25000.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        metrics_snapshot={
            "strategy_id": strategy_id,
            "regime": regime,
        },
    )


def _outcome(*, event_ref_id: str, trade_key: str, day: str, outcome: str, mfe: float, mae: float) -> dict:
    row = TradeOutcome(
        trade_key=trade_key,
        event_id=f"out_{event_ref_id}",
        outcome=outcome,
        ts_epoch_ms=_ts_ms_ist(day, 10, 5),
        symbol="NIFTY",
        mfe_points=mfe,
        mae_points=mae,
        exec_feasible=True,
        exec_feasible_flags={"has_candle_data": True},
        source="unit_test",
        reject_reason=None,
    )
    return {"event_ref_id": event_ref_id, "trade_outcome": row.to_dict()}


def test_strategy_drift_flags_deterioration_and_preserves_stable_group(tmp_path):
    # baseline days (3): 24/25/26; recent days (2): 27/28
    base_days = ["2026-02-24", "2026-02-25", "2026-02-26"]
    recent_days = ["2026-02-27", "2026-02-28"]

    events = []
    outcomes = []

    # alpha TREND: baseline strong, recent poor -> should alert
    for idx, day in enumerate(base_days, start=1):
        eid = f"alpha_base_{idx}"
        trade_key = f"NIFTY|2026-03-05|25000|CE|BUY|alpha"
        events.append(
            _event(
                event_id=eid,
                trade_key=trade_key,
                day=day,
                strategy_id="alpha",
                regime="TREND",
            )
        )
        outcomes.append(
            _outcome(
                event_ref_id=eid,
                trade_key=trade_key,
                day=day,
                outcome="hit_target",
                mfe=12.0,
                mae=-2.0,
            )
        )

    for idx, day in enumerate(recent_days, start=1):
        eid = f"alpha_recent_{idx}"
        trade_key = f"NIFTY|2026-03-05|25000|CE|BUY|alpha"
        events.append(
            _event(
                event_id=eid,
                trade_key=trade_key,
                day=day,
                strategy_id="alpha",
                regime="TREND",
            )
        )
        outcomes.append(
            _outcome(
                event_ref_id=eid,
                trade_key=trade_key,
                day=day,
                outcome="hit_sl",
                mfe=2.0,
                mae=-8.0,
            )
        )

    # beta RANGE: baseline and recent stable -> should not alert
    for idx, day in enumerate(base_days + recent_days, start=1):
        eid = f"beta_{idx}"
        trade_key = f"NIFTY|2026-03-05|25100|CE|BUY|beta"
        events.append(
            _event(
                event_id=eid,
                trade_key=trade_key,
                day=day,
                strategy_id="beta",
                regime="RANGE",
            )
        )
        outcomes.append(
            _outcome(
                event_ref_id=eid,
                trade_key=trade_key,
                day=day,
                outcome=("hit_target" if idx % 2 == 0 else "no_hit"),
                mfe=6.0,
                mae=-3.0,
            )
        )

    out_path = tmp_path / "runtime" / "analytics" / "reports" / "2026-02-28" / "strategy_drift.json"
    payload = build_strategy_drift_report(
        "2026-02-28",
        events=events,
        outcomes=outcomes,
        recent_days=2,
        baseline_days=3,
        min_group_trades=2,
        win_rate_abs_threshold=0.25,
        mfe_pct_threshold=0.25,
        mae_pct_threshold=0.25,
        output_path=out_path,
    )

    assert payload["windows"]["recent_days"] == recent_days
    assert payload["windows"]["baseline_days"] == base_days
    assert payload["counts"]["drift_alerts"] == 1

    alerts = payload["drift_alerts"]
    assert len(alerts) == 1
    assert alerts[0]["strategy_id"] == "alpha"
    assert alerts[0]["regime"] == "TREND"
    assert alerts[0]["deterioration"] is True
    assert "win_rate_delta" in alerts[0]["reasons"]

    group_map = {(row["strategy_id"], row["regime"]): row for row in payload["groups"]}

    alpha_group = group_map[("alpha", "TREND")]
    assert alpha_group["recent"]["trade_count"] == 2
    assert alpha_group["baseline"]["trade_count"] == 3
    assert alpha_group["recent"]["win_rate"] == 0.0
    assert alpha_group["baseline"]["win_rate"] == 1.0
    assert alpha_group["drift"]["significant"] is True

    beta_group = group_map[("beta", "RANGE")]
    assert beta_group["drift"]["significant"] is False

    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["counts"]["drift_alerts"] == 1


def test_strategy_drift_handles_insufficient_baseline_without_alerts(tmp_path):
    event = _event(
        event_id="solo_event",
        trade_key="NIFTY|2026-03-05|25200|CE|BUY|solo",
        day="2026-02-28",
        strategy_id="solo",
        regime="TREND",
    )
    outcome = _outcome(
        event_ref_id="solo_event",
        trade_key="NIFTY|2026-03-05|25200|CE|BUY|solo",
        day="2026-02-28",
        outcome="hit_target",
        mfe=5.0,
        mae=-1.0,
    )

    payload = build_strategy_drift_report(
        "2026-02-28",
        events=[event],
        outcomes=[outcome],
        recent_days=2,
        baseline_days=3,
        min_group_trades=2,
        output_path=tmp_path / "strategy_drift.json",
    )

    assert payload["windows"]["recent_days"] == ["2026-02-28"]
    assert payload["windows"]["baseline_days"] == []
    assert payload["counts"]["drift_alerts"] == 0
    assert payload["groups"][0]["drift"]["enough_samples"] is False
    assert payload["groups"][0]["drift"]["significant"] is False
