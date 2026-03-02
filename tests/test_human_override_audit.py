from __future__ import annotations

from datetime import datetime
import json

from core.analytics.human_override_audit import build_human_override_audit
from core.analytics.schema import TradeIntentEvent, TradeOutcome


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
    manual_flag: bool = False,
) -> TradeIntentEvent:
    return TradeIntentEvent(
        trade_key=trade_key,
        event_id=event_id,
        intent="accepted",
        ts_epoch_ms=_ts_ms_ist(day),
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25000.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        reject_reason=None,
        gate_decisions=(),
        metrics_snapshot={
            "strategy_id": strategy_id,
            "regime": regime,
            "manual_override_used": manual_flag,
        },
    )


def _outcome(
    *,
    event_ref_id: str,
    trade_key: str,
    day: str,
    outcome: str,
    pnl_points: float,
    mfe_points: float,
    mae_points: float,
) -> dict:
    row = TradeOutcome(
        trade_key=trade_key,
        event_id=f"out_{event_ref_id}",
        outcome=outcome,
        ts_epoch_ms=_ts_ms_ist(day, 10, 5),
        symbol="NIFTY",
        mfe_points=mfe_points,
        mae_points=mae_points,
        exec_feasible=True,
        exec_feasible_flags={"has_candle_data": True},
        source="unit_test",
        reject_reason=None,
    )
    return {
        "event_ref_id": event_ref_id,
        "trade_outcome": row.to_dict(),
        "pnl_points": pnl_points,
    }


def test_human_override_audit_manual_vs_auto_split_and_value_metrics(tmp_path):
    day = "2026-02-28"

    events = [
        _event(
            event_id="evt_manual_flag",
            trade_key="NIFTY|2026-03-05|25000|CE|BUY|alpha",
            day=day,
            strategy_id="alpha",
            regime="TREND",
            manual_flag=True,
        ),
        _event(
            event_id="evt_manual_approved_log",
            trade_key="NIFTY|2026-03-05|25100|CE|BUY|beta",
            day=day,
            strategy_id="beta",
            regime="RANGE",
            manual_flag=False,
        ),
        _event(
            event_id="evt_auto_win",
            trade_key="NIFTY|2026-03-05|25200|CE|BUY|gamma",
            day=day,
            strategy_id="gamma",
            regime="RANGE",
            manual_flag=False,
        ),
        _event(
            event_id="evt_auto_no_hit",
            trade_key="NIFTY|2026-03-05|25300|CE|BUY|delta",
            day=day,
            strategy_id="delta",
            regime="UNKNOWN",
            manual_flag=False,
        ),
    ]

    outcomes = [
        _outcome(
            event_ref_id="evt_manual_flag",
            trade_key="NIFTY|2026-03-05|25000|CE|BUY|alpha",
            day=day,
            outcome="hit_target",
            pnl_points=10.0,
            mfe_points=12.0,
            mae_points=-2.0,
        ),
        _outcome(
            event_ref_id="evt_manual_approved_log",
            trade_key="NIFTY|2026-03-05|25100|CE|BUY|beta",
            day=day,
            outcome="hit_sl",
            pnl_points=-6.0,
            mfe_points=3.0,
            mae_points=-7.0,
        ),
        _outcome(
            event_ref_id="evt_auto_win",
            trade_key="NIFTY|2026-03-05|25200|CE|BUY|gamma",
            day=day,
            outcome="hit_target",
            pnl_points=4.0,
            mfe_points=5.0,
            mae_points=-1.0,
        ),
        _outcome(
            event_ref_id="evt_auto_no_hit",
            trade_key="NIFTY|2026-03-05|25300|CE|BUY|delta",
            day=day,
            outcome="no_hit",
            pnl_points=0.0,
            mfe_points=1.0,
            mae_points=-2.0,
        ),
    ]

    queue_rows = [
        {
            "trade_key": "NIFTY|2026-03-05|25100|CE|BUY|beta",
            "trade_id": "trade_beta_manual",
        }
    ]
    approved_records = {
        "trade_beta_manual": {
            "status": "APPROVED",
            "approved_by": "operator_1",
        }
    }

    out_path = tmp_path / "runtime" / "analytics" / "reports" / day / "human_override_audit.json"
    payload = build_human_override_audit(
        day,
        events=events,
        outcomes=outcomes,
        queue_rows=queue_rows,
        approved_records=approved_records,
        examples_limit=2,
        output_path=out_path,
    )

    assert payload["counts"]["matched_events"] == 4
    assert payload["counts"]["manual_overrides"] == 2
    assert payload["counts"]["auto_trades"] == 2

    manual = payload["cohorts"]["manual"]
    auto = payload["cohorts"]["auto"]
    assert manual["trade_count"] == 2
    assert manual["wins"] == 1
    assert manual["losses"] == 1
    assert manual["win_rate"] == 0.5
    assert manual["avg_pnl_points"] == 2.0
    assert manual["avg_mfe_points"] == 7.5
    assert manual["avg_mae_points"] == -4.5

    assert auto["trade_count"] == 2
    assert auto["wins"] == 1
    assert auto["no_hit"] == 1
    assert auto["avg_pnl_points"] == 2.0

    override_value = payload["override_value"]
    assert override_value["manual_minus_auto_win_rate"] == 0.0
    assert override_value["manual_minus_auto_avg_pnl_points"] == 0.0

    best = payload["examples"]["best_overrides"]
    worst = payload["examples"]["worst_overrides"]
    assert len(best) == 2
    assert len(worst) == 2
    assert best[0]["event_id"] == "evt_manual_flag"
    assert worst[0]["event_id"] == "evt_manual_approved_log"

    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["counts"]["manual_overrides"] == 2


def test_human_override_audit_no_manual_overrides(tmp_path):
    day = "2026-02-28"
    events = [
        _event(
            event_id="evt_auto_only",
            trade_key="NIFTY|2026-03-05|25400|CE|BUY|solo",
            day=day,
            strategy_id="solo",
            regime="TREND",
            manual_flag=False,
        )
    ]
    outcomes = [
        _outcome(
            event_ref_id="evt_auto_only",
            trade_key="NIFTY|2026-03-05|25400|CE|BUY|solo",
            day=day,
            outcome="hit_target",
            pnl_points=3.0,
            mfe_points=4.0,
            mae_points=-1.0,
        )
    ]

    payload = build_human_override_audit(
        day,
        events=events,
        outcomes=outcomes,
        queue_rows=[],
        approved_records={},
        output_path=tmp_path / "human_override_audit.json",
    )

    assert payload["counts"]["manual_overrides"] == 0
    assert payload["cohorts"]["manual"]["trade_count"] == 0
    assert payload["cohorts"]["auto"]["trade_count"] == 1
    assert payload["examples"]["best_overrides"] == []
    assert payload["examples"]["worst_overrides"] == []
