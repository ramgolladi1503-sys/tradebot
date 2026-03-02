from __future__ import annotations

from datetime import datetime
import json

from core.analytics.execution_feasibility import build_execution_feasibility_report
from core.analytics.schema import TradeIntentEvent, TradeOutcome


def _ts_ms_ist(day: str, hh: int, mm: int, ss: int = 0) -> int:
    dt = datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:{ss:02d}+05:30")
    return int(dt.timestamp() * 1000.0)


def _event(*, event_id: str, trade_key: str, symbol: str, side: str, ts_ms: int) -> TradeIntentEvent:
    return TradeIntentEvent(
        trade_key=trade_key,
        event_id=event_id,
        intent="rejected",
        ts_epoch_ms=ts_ms,
        symbol=symbol,
        expiry="2026-03-05",
        strike=25000.0,
        option_type="CE",
        side=side,
        source="unit_test",
        reject_reason="unit_reject",
        gate_decisions=(),
        metrics_snapshot={},
    )


def _outcome(*, trade_key: str, ts_ms: int, outcome: str) -> TradeOutcome:
    return TradeOutcome(
        trade_key=trade_key,
        event_id=f"out_{trade_key}",
        outcome=outcome,
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        mfe_points=5.0,
        mae_points=-2.0,
        exec_feasible=True,
        exec_feasible_flags={"has_candle_data": True},
        source="unit_test",
        reject_reason=None,
    )


def test_execution_feasibility_buy_snapshot_flags(tmp_path):
    date_key = "2026-02-28"
    ts_ms = _ts_ms_ist(date_key, 10, 0)
    event = _event(event_id="evt_buy", trade_key="tk_buy", symbol="NIFTY", side="BUY", ts_ms=ts_ms)
    outcome = _outcome(trade_key="tk_buy", ts_ms=ts_ms + 60_000, outcome="hit_target")

    payload = build_execution_feasibility_report(
        date_key,
        events=[event],
        outcomes=[{"event_ref_id": "evt_buy", "trade_outcome": outcome.to_dict()}],
        quote_rows=[
            {
                "event_id": "evt_buy",
                "trade_key": "tk_buy",
                "symbol": "NIFTY",
                "timestamp_epoch_ms": ts_ms,
                "side": "BUY",
                "intended_entry": 104.8,
                "target": 105.0,
                "bid": 104.8,
                "ask": 105.0,
                "ltp": 104.9,
                "quote_age_sec": 0.8,
            }
        ],
        max_spread_pct=0.02,
        max_quote_age_sec=2.0,
        slippage_allowance=0.3,
        output_path=tmp_path / "runtime" / "analytics" / "reports" / date_key / "execution_feasibility.json",
    )

    assert payload["evaluated_outcomes"] == 1
    row = payload["rows"][0]
    assert row["exec_entry_feasible"] is True
    assert row["exec_target_feasible"] is True
    assert row["exec_quality_label"] == "FEASIBLE"

    out = row["trade_outcome"]
    assert out["exec_feasible"] is True
    assert out["exec_feasible_flags"]["exec_entry_feasible"] is True
    assert out["exec_feasible_flags"]["exec_target_feasible"] is True
    assert out["exec_feasible_flags"]["exec_spread_ok"] is True
    assert out["exec_feasible_flags"]["exec_quote_age_ok"] is True


def test_execution_feasibility_wide_stale_snapshot(tmp_path):
    date_key = "2026-02-28"
    ts_ms = _ts_ms_ist(date_key, 11, 0)
    event = _event(event_id="evt_sell", trade_key="tk_sell", symbol="NIFTY", side="SELL", ts_ms=ts_ms)
    outcome = _outcome(trade_key="tk_sell", ts_ms=ts_ms + 60_000, outcome="hit_sl")

    out_path = tmp_path / "runtime" / "analytics" / "reports" / date_key / "execution_feasibility.json"
    payload = build_execution_feasibility_report(
        date_key,
        events=[event],
        outcomes=[{"event_ref_id": "evt_sell", "trade_outcome": outcome.to_dict()}],
        quote_rows=[
            {
                "event_id": "evt_sell",
                "trade_key": "tk_sell",
                "symbol": "NIFTY",
                "timestamp_epoch_ms": ts_ms,
                "side": "SELL",
                "intended_entry": 100.0,
                "target": 98.0,
                "bid": 95.0,
                "ask": 105.0,
                "ltp": 100.0,
                "quote_age_sec": 5.0,
            }
        ],
        max_spread_pct=0.02,
        max_quote_age_sec=2.0,
        slippage_allowance=0.5,
        output_path=out_path,
    )

    assert payload["evaluated_outcomes"] == 1
    assert payload["exec_quality_counts"]["WIDE_AND_STALE"] == 1
    row = payload["rows"][0]
    assert row["exec_entry_feasible"] is False
    assert row["exec_target_feasible"] is False
    assert row["exec_quality_label"] == "WIDE_AND_STALE"
    assert row["trade_outcome"]["exec_feasible"] is False
    assert row["trade_outcome"]["exec_feasible_flags"]["exec_entry_feasible"] is False
    assert row["trade_outcome"]["exec_feasible_flags"]["exec_spread_ok"] is False
    assert row["trade_outcome"]["exec_feasible_flags"]["exec_quote_age_ok"] is False

    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["evaluated_outcomes"] == 1
    assert written["exec_quality_counts"]["WIDE_AND_STALE"] == 1
