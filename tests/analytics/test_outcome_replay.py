from __future__ import annotations

import json
from pathlib import Path

from core.analytics import outcome_replay as replay_module
from core.analytics.outcome_replay import analyze_event_outcome, build_outcomes_for_date, default_outcomes_path
from core.analytics.schema import TradeIntentEvent


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_session_outcome_paths_are_isolated(tmp_path):
    first = tmp_path / "sessions" / "run-a"
    second = tmp_path / "sessions" / "run-b"
    first.mkdir(parents=True)
    second.mkdir()
    default = default_outcomes_path("2026-10-01")
    first_path = default_outcomes_path("2026-10-01", session_dir=first)
    second_path = default_outcomes_path("2026-10-01", session_dir=second)
    assert first_path != default
    assert second_path != default
    assert first_path != second_path
    journal = first / "candidate_journal.jsonl"
    journal.write_text('{"candidate_id":"one"}\n', encoding="utf-8")
    before_append = default_outcomes_path("2026-10-01", session_dir=first)
    journal.write_text('{"candidate_id":"one"}\n{"candidate_id":"two"}\n', encoding="utf-8")
    after_append = default_outcomes_path("2026-10-01", session_dir=first)
    assert after_append != before_append


def test_session_replay_uses_session_candidates_without_workspace_events(tmp_path, monkeypatch):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    event = TradeIntentEvent(
        trade_key="NIFTY|2026-10-08|25000|CE|BUY",
        event_id="evt_session_candidate",
        intent="rejected",
        ts_epoch_ms=1790841500000,
        symbol="NIFTY",
        side="BUY",
        source="session_candidate_journal:test",
        reject_reason="FEED_STALE",
        metrics_snapshot={"entry": 100, "target": 110, "stop": 95},
    )
    monkeypatch.setattr(replay_module, "discover_session_paths", lambda **_kwargs: [session_dir])
    monkeypatch.setattr(replay_module, "load_session_events", lambda **_kwargs: [event])
    monkeypatch.setattr(
        replay_module,
        "load_trade_intent_events",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("workspace intents must not enter session replay")),
    )
    monkeypatch.setattr(
        replay_module,
        "analyze_event_outcome",
        lambda candidate, **_kwargs: {"event_ref_id": candidate.event_id, "trade_outcome": {"outcome": "no_hit"}},
    )

    result = build_outcomes_for_date(
        "2026-10-01", session_dir=session_dir, output_path=tmp_path / "session-outcomes.jsonl"
    )
    assert result["count"] == 1
    assert json.loads((tmp_path / "session-outcomes.jsonl").read_text().splitlines()[0])["event_ref_id"] == event.event_id


def _load_json(name: str):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _loader_from_candles(candles):
    rows = [
        {
            "time_ms": row["time_ms"],
            "high": row["high"],
            "low": row["low"],
            "ref_price": row.get("close"),
            "source": "mock_candle",
        }
        for row in candles
    ]

    def _loader(event_row, start_ms, end_ms, interval):
        del event_row, interval
        in_window = [r for r in rows if int(r["time_ms"]) >= int(start_ms) and int(r["time_ms"]) <= int(end_ms)]
        return in_window, "mock_candle_series"

    return _loader


def test_outcome_replay_target_hit_first():
    candles = _load_json("candles_target_then_sl.json")
    event = {
        "event_id": "evt_target_first",
        "trade_key": "NIFTY|2026-03-05|22500|CE|BUY",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry": 100.0,
        "target": 105.0,
        "stop": 95.0,
        "reject_ts_epoch": 1740723900000,
        "reject_reason": "quote_stale",
    }
    row = analyze_event_outcome(
        event,
        lookahead_minutes=30,
        candle_interval="1minute",
        series_loader=_loader_from_candles(candles),
    )
    assert row["trade_outcome"]["outcome"] == "hit_target"
    assert row["outcome_reason"] == "TARGET_FIRST"
    assert row["trade_outcome"]["ts_epoch_ms"] == row["resolution_ts_epoch_ms"]


def test_outcome_replay_stop_hit_first():
    candles = _load_json("candles_sl_then_target.json")
    event = {
        "event_id": "evt_stop_first",
        "trade_key": "NIFTY|2026-03-05|22500|CE|BUY",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry": 100.0,
        "target": 105.0,
        "stop": 95.0,
        "reject_ts_epoch": 1740723900000,
        "reject_reason": "spread_wide",
    }
    row = analyze_event_outcome(
        event,
        lookahead_minutes=30,
        candle_interval="1minute",
        series_loader=_loader_from_candles(candles),
    )
    assert row["trade_outcome"]["outcome"] == "hit_sl"
    assert row["outcome_reason"] == "SL_FIRST"
    assert row["trade_outcome"]["ts_epoch_ms"] == row["resolution_ts_epoch_ms"]


def test_outcome_replay_no_hit():
    candles = _load_json("candles_simple_uptrend.json")
    event = {
        "event_id": "evt_no_hit",
        "trade_key": "NIFTY|2026-03-05|22500|CE|BUY",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry": 100.0,
        "target": 120.0,
        "stop": 90.0,
        "reject_ts_epoch": 1740723900000,
        "reject_reason": "risk_cap",
    }
    row = analyze_event_outcome(
        event,
        lookahead_minutes=10,
        candle_interval="1minute",
        series_loader=_loader_from_candles(candles),
    )
    assert row["trade_outcome"]["outcome"] == "no_hit"
    assert row["trade_outcome"]["ts_epoch_ms"] == row["resolution_ts_epoch_ms"]


def test_outcome_replay_handles_gap_candles_missing_intervals():
    candles = _load_json("candles_gap_missing_intervals.json")
    event = {
        "event_id": "evt_gap_series",
        "trade_key": "NIFTY|2026-03-05|22500|CE|BUY",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry": 100.0,
        "target": 110.0,
        "stop": 95.0,
        "reject_ts_epoch": 1740723900000,
        "reject_reason": "gap_series",
    }
    row = analyze_event_outcome(
        event,
        lookahead_minutes=30,
        candle_interval="1minute",
        series_loader=_loader_from_candles(candles),
    )
    assert row["trade_outcome"]["outcome"] == "no_hit"
    # For no-hit windows, replay should resolve at the latest observed point in range.
    assert row["resolution_ts_epoch_ms"] == 1740724860000
    assert row["trade_outcome"]["ts_epoch_ms"] == row["resolution_ts_epoch_ms"]


def test_outcome_replay_no_series_data_primary_reason():
    event = {
        "event_id": "evt_no_series",
        "trade_key": "NIFTY|2026-03-05|22500|CE|BUY",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry": 100.0,
        "target": 110.0,
        "stop": 95.0,
        "reject_ts_epoch": 1740723900000,
        "reject_reason": "premium_band_fail",
        "reason_codes": ["premium_band_fail", "liquidity_hard_veto"],
    }

    def _empty_loader(event_row, start_ms, end_ms, interval):
        del event_row, start_ms, end_ms, interval
        return [], "no_series_data"

    row = analyze_event_outcome(
        event,
        lookahead_minutes=30,
        candle_interval="1minute",
        series_loader=_empty_loader,
    )

    assert row["outcome_reason"] == "NO_SERIES_DATA"
    assert row["trade_outcome"]["reject_reason"] == "NO_SERIES_DATA"
    assert row["trade_outcome"]["exec_feasible_flags"]["has_candle_data"] is False
    assert row["trade_outcome"]["exec_feasible_flags"]["has_series_data"] is False
    assert row["series_source"] == "no_series_data"
    assert row["trade_outcome"]["reason_codes"] == ["NO_SERIES_DATA"]
    assert row["trade_outcome"]["reject_reasons"] == ["NO_SERIES_DATA"]
    assert row["trade_outcome"]["primary_reject_reason"] == "NO_SERIES_DATA"


def test_outcome_replay_series_data_keeps_strategy_reject_reason():
    candles = _load_json("candles_target_then_sl.json")
    event = {
        "event_id": "evt_premium_series",
        "trade_key": "NIFTY|2026-03-05|22500|CE|BUY",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry": 100.0,
        "target": 105.0,
        "stop": 95.0,
        "reject_ts_epoch": 1740723900000,
        "reject_reason": "premium_band_fail",
        "reason_codes": ["premium_band_fail", "liquidity_hard_veto"],
    }
    row = analyze_event_outcome(
        event,
        lookahead_minutes=30,
        candle_interval="1minute",
        series_loader=_loader_from_candles(candles),
    )
    assert row["outcome_reason"] == "TARGET_FIRST"
    assert row["trade_outcome"]["reject_reason"] == "premium_band_fail"
    assert row["trade_outcome"]["reason_codes"] == ["premium_band_fail", "liquidity_hard_veto"]
    assert row["trade_outcome"]["reject_reasons"] == ["premium_band_fail", "liquidity_hard_veto"]
    assert row["trade_outcome"]["primary_reject_reason"] == "premium_band_fail"
