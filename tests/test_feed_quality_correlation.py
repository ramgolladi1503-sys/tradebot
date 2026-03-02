from __future__ import annotations

from datetime import datetime
import json

from core.analytics.feed_quality_correlation import build_feed_quality_correlation_report
from core.analytics.schema import TradeIntentEvent, TradeOutcome


def _ts_ms_ist(day: str, hh: int, mm: int, ss: int = 0) -> int:
    dt = datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:{ss:02d}+05:30")
    return int(dt.timestamp() * 1000.0)


def _event(*, event_id: str, trade_key: str, ts_ms: int, quote_age: float, spread: float, feed_state: str) -> TradeIntentEvent:
    return TradeIntentEvent(
        trade_key=trade_key,
        event_id=event_id,
        intent="advisory",
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25000.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        metrics_snapshot={
            "quote_age_sec": quote_age,
            "spread_pct": spread,
            "feed_state": feed_state,
            "data_source": "kite",
        },
    )


def _outcome(*, event_ref_id: str, trade_key: str, ts_ms: int, outcome: str) -> dict:
    row = TradeOutcome(
        trade_key=trade_key,
        event_id=f"out_{event_ref_id}",
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
    return {
        "event_ref_id": event_ref_id,
        "trade_outcome": row.to_dict(),
    }


def test_feed_quality_correlation_bucket_outcomes_and_suggestions(tmp_path):
    date_key = "2026-02-28"
    ts_1 = _ts_ms_ist(date_key, 10, 0)
    ts_2 = _ts_ms_ist(date_key, 10, 5)
    ts_3 = _ts_ms_ist(date_key, 10, 10)
    ts_4 = _ts_ms_ist(date_key, 10, 15)

    events = [
        _event(
            event_id="evt_1",
            trade_key="tk_1",
            ts_ms=ts_1,
            quote_age=0.4,
            spread=0.005,
            feed_state="OK",
        ),
        _event(
            event_id="evt_2",
            trade_key="tk_2",
            ts_ms=ts_2,
            quote_age=0.6,
            spread=0.015,
            feed_state="DEGRADED",
        ),
        _event(
            event_id="evt_3",
            trade_key="tk_3",
            ts_ms=ts_3,
            quote_age=3.2,
            spread=0.03,
            feed_state="DOWN",
        ),
        _event(
            event_id="evt_4",
            trade_key="tk_4",
            ts_ms=ts_4,
            quote_age=1.2,
            spread=0.008,
            feed_state="OK",
        ),
    ]

    outcomes = [
        _outcome(event_ref_id="evt_1", trade_key="tk_1", ts_ms=ts_1 + 60_000, outcome="hit_target"),
        _outcome(event_ref_id="evt_2", trade_key="tk_2", ts_ms=ts_2 + 60_000, outcome="hit_sl"),
        _outcome(event_ref_id="evt_3", trade_key="tk_3", ts_ms=ts_3 + 60_000, outcome="hit_sl"),
        _outcome(event_ref_id="evt_4", trade_key="tk_4", ts_ms=ts_4 + 60_000, outcome="no_hit"),
    ]

    output_path = tmp_path / "runtime" / "analytics" / "reports" / date_key / "feed_quality_correlation.json"
    payload = build_feed_quality_correlation_report(
        date_key,
        events=events,
        outcomes=outcomes,
        quote_age_buckets_sec=[0.5, 1.0, 2.0],
        spread_buckets=[0.01, 0.02],
        min_samples=1,
        min_inflection_drop=0.2,
        output_path=output_path,
    )

    assert payload["counts"]["scanned_events"] == 4
    assert payload["counts"]["matched_outcomes"] == 4
    assert payload["counts"]["rows"] == 4

    quote_buckets = {row["bucket"]: row for row in payload["bucketed_outcomes"]["quote_age_sec"]}
    assert quote_buckets["<= 0.5"]["count"] == 1
    assert quote_buckets["<= 0.5"]["wins"] == 1
    assert quote_buckets["<= 0.5"]["win_rate"] == 1.0
    assert quote_buckets["(0.5, 1]"]["count"] == 1
    assert quote_buckets["(1, 2]"]["count"] == 1
    assert quote_buckets["> 2"]["count"] == 1

    spread_buckets = {row["bucket"]: row for row in payload["bucketed_outcomes"]["spread_pct"]}
    assert spread_buckets["<= 0.01"]["count"] == 2
    assert spread_buckets["<= 0.01"]["wins"] == 1
    assert spread_buckets["<= 0.01"]["win_rate"] == 0.5
    assert spread_buckets["(0.01, 0.02]"]["count"] == 1
    assert spread_buckets["> 0.02"]["count"] == 1

    feed_states = {row["feed_state"]: row for row in payload["bucketed_outcomes"]["feed_state"]}
    assert feed_states["OK"]["count"] == 2
    assert feed_states["OK"]["wins"] == 1
    assert feed_states["OK"]["no_hit"] == 1
    assert feed_states["DEGRADED"]["losses"] == 1
    assert feed_states["DOWN"]["losses"] == 1

    assert payload["correlations"]["quote_age_sec_vs_win"] < 0.0
    assert payload["correlations"]["spread_pct_vs_win"] < 0.0

    quote_suggestion = payload["threshold_suggestions"]["quote_age_sec"]
    assert quote_suggestion is not None
    assert quote_suggestion["threshold"] == 0.5
    assert quote_suggestion["drop"] >= 0.2

    spread_suggestion = payload["threshold_suggestions"]["spread_pct"]
    assert spread_suggestion is not None
    assert spread_suggestion["threshold"] == 0.01

    assert output_path.exists()
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["counts"] == payload["counts"]


def test_feed_quality_correlation_uses_quote_rows_when_event_metrics_missing(tmp_path):
    date_key = "2026-02-28"
    ts_ms = _ts_ms_ist(date_key, 11, 0)

    event = TradeIntentEvent(
        trade_key="tk_quote_fallback",
        event_id="evt_quote_fallback",
        intent="advisory",
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25100.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        metrics_snapshot={},
    )
    outcomes = [
        _outcome(
            event_ref_id="evt_quote_fallback",
            trade_key="tk_quote_fallback",
            ts_ms=ts_ms + 30_000,
            outcome="hit_target",
        )
    ]
    quote_rows = [
        {
            "event_id": "evt_quote_fallback",
            "trade_key": "tk_quote_fallback",
            "symbol": "NIFTY",
            "timestamp_epoch_ms": ts_ms,
            "quote_age_sec": 0.9,
            "spread_pct": 0.011,
            "feed_state": "DEGRADED",
            "source": "kite_snapshot",
        }
    ]

    payload = build_feed_quality_correlation_report(
        date_key,
        events=[event],
        outcomes=outcomes,
        quote_rows=quote_rows,
        quote_age_buckets_sec=[1.0],
        spread_buckets=[0.02],
        min_samples=1,
        min_inflection_drop=0.0,
        output_path=tmp_path / "feed_quality_correlation.json",
    )

    assert payload["counts"]["rows"] == 1
    row = payload["rows"][0]
    assert row["quote_age_sec"] == 0.9
    assert row["spread_pct"] == 0.011
    assert row["feed_state"] == "DEGRADED"
    assert row["source"] == "kite_snapshot"
