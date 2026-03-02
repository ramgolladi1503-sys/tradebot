from __future__ import annotations

from datetime import date, datetime
import json

from core.analytics.schema import TradeIntentEvent, TradeOutcome
from core.analytics.time_of_day import bucket_for_timestamp_ms, build_time_of_day_report


def _ts_ms_ist(day: str, hh: int, mm: int, ss: int = 0) -> int:
    dt = datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:{ss:02d}+05:30")
    return int(dt.timestamp() * 1000.0)


def _event(*, event_id: str, trade_key: str, symbol: str, ts_ms: int) -> TradeIntentEvent:
    return TradeIntentEvent(
        trade_key=trade_key,
        event_id=event_id,
        intent="rejected",
        ts_epoch_ms=ts_ms,
        symbol=symbol,
        expiry="2026-03-05",
        strike=25000.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        reject_reason="unit_reject",
        gate_decisions=(),
        metrics_snapshot={},
    )


def _outcome(*, event_ref_id: str, trade_key: str, ts_ms: int, outcome: str, mfe: float, mae: float) -> dict:
    row = TradeOutcome(
        trade_key=trade_key,
        event_id=f"out_{event_ref_id}",
        outcome=outcome,
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        mfe_points=mfe,
        mae_points=mae,
        exec_feasible=True,
        exec_feasible_flags={"has_candle_data": True},
        source="unit_test",
        reject_reason=None,
    )
    return {"event_ref_id": event_ref_id, "trade_outcome": row.to_dict()}


def test_bucket_for_timestamp_ms_ranges_and_expiry_special(monkeypatch):
    def _fake_next_expiry_after(start_date, expiry_type="WEEKLY", symbol=None):
        if str(symbol or "").upper() == "BANKNIFTY":
            # bucket_for_timestamp_ms checks with (event_day - 1),
            # so return the event day for BANKNIFTY to mark expiry special.
            return start_date + date.resolution
        return start_date + date.resolution * 10

    monkeypatch.setattr("core.analytics.time_of_day.market_calendar.next_expiry_after", _fake_next_expiry_after)

    open_ts = _ts_ms_ist("2026-02-28", 9, 20)
    mid_ts = _ts_ms_ist("2026-02-28", 10, 0)
    late_ts = _ts_ms_ist("2026-02-28", 14, 45)

    assert bucket_for_timestamp_ms(open_ts, "NIFTY") == "OPEN"
    assert bucket_for_timestamp_ms(mid_ts, "NIFTY") == "MID"
    assert bucket_for_timestamp_ms(late_ts, "NIFTY") == "LATE"
    assert bucket_for_timestamp_ms(mid_ts, "BANKNIFTY") == "EXPIRY_SPECIAL"


def test_build_time_of_day_report_aggregates(tmp_path, monkeypatch):
    def _fake_next_expiry_after(start_date, expiry_type="WEEKLY", symbol=None):
        if str(symbol or "").upper() == "BANKNIFTY":
            return start_date + date.resolution
        return start_date + date.resolution * 10

    monkeypatch.setattr("core.analytics.time_of_day.market_calendar.next_expiry_after", _fake_next_expiry_after)

    date_key = "2026-02-28"
    open_ts = _ts_ms_ist(date_key, 9, 20)
    mid_ts = _ts_ms_ist(date_key, 10, 0)
    late_ts = _ts_ms_ist(date_key, 14, 45)
    exp_ts = _ts_ms_ist(date_key, 11, 0)

    events = [
        _event(event_id="evt_open", trade_key="tk_open", symbol="NIFTY", ts_ms=open_ts),
        _event(event_id="evt_mid", trade_key="tk_mid", symbol="NIFTY", ts_ms=mid_ts),
        _event(event_id="evt_late", trade_key="tk_late", symbol="NIFTY", ts_ms=late_ts),
        _event(event_id="evt_exp", trade_key="tk_exp", symbol="BANKNIFTY", ts_ms=exp_ts),
    ]
    outcomes = [
        _outcome(event_ref_id="evt_open", trade_key="tk_open", ts_ms=open_ts + 1_000, outcome="hit_target", mfe=10.0, mae=-1.0),
        _outcome(event_ref_id="evt_mid", trade_key="tk_mid", ts_ms=mid_ts + 1_000, outcome="hit_sl", mfe=3.0, mae=-8.0),
        _outcome(event_ref_id="evt_late", trade_key="tk_late", ts_ms=late_ts + 1_000, outcome="no_hit", mfe=2.0, mae=-2.5),
        _outcome(event_ref_id="evt_exp", trade_key="tk_exp", ts_ms=exp_ts + 1_000, outcome="hit_target", mfe=9.0, mae=-1.5),
    ]

    out_path = tmp_path / "runtime" / "analytics" / "reports" / date_key / "time_of_day.json"
    payload = build_time_of_day_report(date_key, events=events, outcomes=outcomes, output_path=out_path)

    assert payload["total_events"] == 4
    assert payload["matched_outcomes"] == 4

    by_bucket = {row["bucket"]: row for row in payload["buckets"]}
    assert by_bucket["OPEN"]["count"] == 1
    assert by_bucket["OPEN"]["wins"] == 1
    assert by_bucket["OPEN"]["win_rate"] == 1.0
    assert by_bucket["OPEN"]["avg_mfe"] == 10.0
    assert by_bucket["OPEN"]["avg_mae"] == -1.0

    assert by_bucket["MID"]["count"] == 1
    assert by_bucket["MID"]["losses"] == 1
    assert by_bucket["MID"]["loss_rate"] == 1.0

    assert by_bucket["LATE"]["count"] == 1
    assert by_bucket["LATE"]["no_hit"] == 1
    assert by_bucket["LATE"]["no_hit_rate"] == 1.0

    assert by_bucket["EXPIRY_SPECIAL"]["count"] == 1
    assert by_bucket["EXPIRY_SPECIAL"]["wins"] == 1

    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["date"] == date_key
    assert written["total_events"] == 4
