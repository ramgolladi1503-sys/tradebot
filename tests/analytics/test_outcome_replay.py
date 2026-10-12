from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

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
        "2026-10-01", session_dir=session_dir, output_path=tmp_path / "session-outcomes.jsonl",
        series_loader=lambda *_args: ([], "fixture_loader"),
    )
    assert result["count"] == 1
    assert json.loads((tmp_path / "session-outcomes.jsonl").read_text().splitlines()[0])["event_ref_id"] == event.event_id


def test_batch_replay_refuses_to_write_unresolved_outcomes_without_offline_loader(tmp_path, monkeypatch):
    event = TradeIntentEvent(
        trade_key="NIFTY|2026-10-08|25000|CE|BUY",
        event_id="evt_missing_local_series",
        intent="rejected",
        ts_epoch_ms=1790841500000,
        symbol="NIFTY",
        side="BUY",
        source="test",
        reject_reason="FEED_STALE",
        metrics_snapshot={"entry": 100, "target": 110, "stop": 95},
    )
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    monkeypatch.setattr(replay_module, "discover_session_paths", lambda **_kwargs: [session_dir])
    monkeypatch.setattr(replay_module, "load_session_events", lambda **_kwargs: [event])
    output_path = tmp_path / "must-not-be-written.jsonl"

    try:
        build_outcomes_for_date("2026-10-01", session_dir=session_dir, output_path=output_path)
    except RuntimeError as exc:
        assert "OFFLINE_SERIES_LOADER_REQUIRED" in str(exc)
    else:
        raise AssertionError("batch replay must require an explicit offline series source")

    assert not output_path.exists()


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
        lookahead_minutes=4,
        candle_interval="1minute",
        series_loader=_loader_from_candles(candles),
    )
    assert row["trade_outcome"]["outcome"] == "no_hit"
    assert row["trade_outcome"]["ts_epoch_ms"] == row["resolution_ts_epoch_ms"]


def test_outcome_replay_rejects_gap_candles_missing_intervals():
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
    with pytest.raises(replay_module.IncompleteOutcomeWindowError, match="incomplete_outcome_window:gap"):
        analyze_event_outcome(
            event,
            lookahead_minutes=30,
            candle_interval="1minute",
            series_loader=_loader_from_candles(candles),
        )


def test_outcome_replay_no_series_data_fails_closed():
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

    with pytest.raises(replay_module.IncompleteOutcomeWindowError, match="incomplete_outcome_window:truncated"):
        analyze_event_outcome(
            event,
            lookahead_minutes=30,
            candle_interval="1minute",
            series_loader=_empty_loader,
        )


def test_default_series_loader_never_falls_through_to_market_data(monkeypatch):
    calls = []
    market_data_stub = types.ModuleType("core.market_data")

    def _forbidden(*_args, **_kwargs):
        calls.append("market_data")
        raise AssertionError("offline analytics must not call market-data loaders")

    market_data_stub.get_candles = _forbidden
    market_data_stub.get_option_candles_or_snapshots = _forbidden
    monkeypatch.setitem(__import__("sys").modules, "core.market_data", market_data_stub)
    event = {
        "event_id": "evt_offline_only",
        "trade_key": "NIFTY|2026-03-05|22500|CE|BUY",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry": 100.0,
        "target": 110.0,
        "stop": 95.0,
        "reject_ts_epoch": 1740723900000,
    }

    assert calls == []
    with pytest.raises(replay_module.IncompleteOutcomeWindowError, match="incomplete_outcome_window:truncated"):
        analyze_event_outcome(event)


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


def _horizon_event(**overrides):
    event = {
        "event_id": "evt_horizon_contract",
        "trade_key": "NIFTY|2026-03-05|22500|CE|BUY",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry": 100.0,
        "target": 110.0,
        "stop": 90.0,
        "reject_ts_epoch": 1740723900000,
    }
    event.update(overrides)
    return event


def _series_loader_for(rows):
    return lambda *_args: (rows, "test_local_series")


def _horizon_row(offset_minutes, *, high=105.0, low=95.0):
    return {
        "time_ms": 1740723900000 + offset_minutes * 60_000,
        "high": high,
        "low": low,
        "ref_price": 100.0,
    }


def test_outcome_replay_accepts_complete_no_hit_window():
    rows = [_horizon_row(offset) for offset in range(3)]
    result = analyze_event_outcome(
        _horizon_event(),
        lookahead_minutes=3,
        candle_interval="1minute",
        series_loader=_series_loader_for(rows),
    )

    assert result["trade_outcome"]["outcome"] == "no_hit"
    assert result["resolution_ts_epoch_ms"] == rows[-1]["time_ms"]


def test_outcome_replay_rejects_missing_event_timestamp_without_synthetic_outcome():
    event = _horizon_event()
    event.pop("reject_ts_epoch")

    with pytest.raises(
        replay_module.IncompleteOutcomeWindowError,
        match="incomplete_outcome_window:missing_event_timestamp",
    ):
        analyze_event_outcome(
            event,
            lookahead_minutes=3,
            candle_interval="1minute",
            series_loader=_series_loader_for([_horizon_row(offset) for offset in range(3)]),
        )


def test_outcome_replay_rejects_missing_levels_instead_of_emitting_no_hit():
    event = _horizon_event()
    event.pop("target")

    with pytest.raises(
        replay_module.IncompleteOutcomeWindowError,
        match="incomplete_outcome_window:missing_outcome_levels",
    ):
        analyze_event_outcome(
            event,
            lookahead_minutes=3,
            candle_interval="1minute",
            series_loader=_series_loader_for([_horizon_row(offset) for offset in range(3)]),
        )


@pytest.mark.parametrize(
    ("first_bar", "later_bar", "expected"),
    [
        ({"high": 111.0, "low": 95.0}, {"high": 120.0, "low": 89.0}, "hit_target"),
        ({"high": 105.0, "low": 89.0}, {"high": 111.0, "low": 80.0}, "hit_sl"),
    ],
)
def test_first_touch_is_terminal_with_truncated_tail_and_later_opposite_hit(first_bar, later_bar, expected):
    rows = [_horizon_row(0, **first_bar), _horizon_row(2, **later_bar)]
    result = analyze_event_outcome(
        _horizon_event(),
        lookahead_minutes=3,
        candle_interval="minute",
        series_loader=_series_loader_for(rows),
    )

    assert result["trade_outcome"]["outcome"] == expected
    assert result["resolution_ts_epoch_ms"] == rows[0]["time_ms"]


def test_outcome_replay_blocks_same_candle_target_stop_ambiguity():
    rows = [_horizon_row(0, high=111.0, low=89.0), _horizon_row(1), _horizon_row(2)]

    with pytest.raises(
        replay_module.IncompleteOutcomeWindowError,
        match="incomplete_outcome_window:ambiguous_same_candle",
    ):
        analyze_event_outcome(
            _horizon_event(),
            lookahead_minutes=3,
            candle_interval="minute",
            series_loader=_series_loader_for(rows),
        )


def test_outcome_replay_accepts_recognized_multiminute_interval():
    rows = [
        {**_horizon_row(0), "time_ms": 1740723900000},
        {**_horizon_row(5), "time_ms": 1740723900000 + 5 * 60_000},
    ]
    result = analyze_event_outcome(
        _horizon_event(),
        lookahead_minutes=10,
        candle_interval="5minute",
        series_loader=_series_loader_for(rows),
    )

    assert result["trade_outcome"]["outcome"] == "no_hit"
    assert result["resolution_ts_epoch_ms"] == rows[-1]["time_ms"]


def test_outcome_replay_rejects_truncated_no_hit_horizon():
    rows = [_horizon_row(offset) for offset in range(2)]

    with pytest.raises(replay_module.IncompleteOutcomeWindowError, match="incomplete_outcome_window:truncated"):
        analyze_event_outcome(
            _horizon_event(),
            lookahead_minutes=3,
            candle_interval="minute",
            series_loader=_series_loader_for(rows),
        )


def test_outcome_replay_rejects_gap_before_later_hit():
    rows = [
        _horizon_row(0),
        _horizon_row(2, high=111.0),
    ]

    with pytest.raises(replay_module.IncompleteOutcomeWindowError, match="incomplete_outcome_window:gap"):
        analyze_event_outcome(
            _horizon_event(),
            lookahead_minutes=3,
            candle_interval="minute",
            series_loader=_series_loader_for(rows),
        )


@pytest.mark.parametrize("interval", ["daily", "5seconds", "2hour"])
def test_outcome_replay_rejects_unsupported_interval(interval):
    with pytest.raises(replay_module.IncompleteOutcomeWindowError, match="incomplete_outcome_window:unsupported_interval"):
        analyze_event_outcome(
            _horizon_event(),
            lookahead_minutes=3,
            candle_interval=interval,
            series_loader=_series_loader_for([_horizon_row(0)]),
        )


def test_outcome_replay_requires_exact_source_bar_at_event_time():
    event = _horizon_event(reject_ts_epoch=1740723901000)
    with pytest.raises(replay_module.IncompleteOutcomeWindowError, match="incomplete_outcome_window:truncated"):
        analyze_event_outcome(
            event,
            lookahead_minutes=3,
            candle_interval="minute",
            series_loader=_series_loader_for([_horizon_row(0)]),
        )


def test_outcome_replay_anchors_multiminute_grid_to_exchange_session_bar():
    event = _horizon_event(reject_ts_epoch=1740714300000)  # 2025-02-28 09:15 IST
    rows = [
        {"time_ms": 1740714300000, "high": 105.0, "low": 95.0, "ref_price": 100.0},
        {"time_ms": 1740714420000, "high": 105.0, "low": 95.0, "ref_price": 100.0},
    ]

    result = analyze_event_outcome(
        event,
        lookahead_minutes=4,
        candle_interval="2minute",
        series_loader=_series_loader_for(rows),
    )

    assert result["trade_outcome"]["outcome"] == "no_hit"
    assert result["resolution_ts_epoch_ms"] == rows[-1]["time_ms"]


def test_batch_replay_preserves_existing_output_on_incomplete_horizon(tmp_path, monkeypatch):
    event = TradeIntentEvent(
        trade_key="NIFTY|2026-03-05|22500|CE|BUY",
        event_id="evt_horizon_batch",
        intent="rejected",
        ts_epoch_ms=1740723900000,
        symbol="NIFTY",
        side="BUY",
        source="test",
        reject_reason="test_horizon",
        metrics_snapshot={"entry": 100.0, "target": 110.0, "stop": 90.0},
    )
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    output_path = tmp_path / "outcomes.jsonl"
    original_bytes = b'{"prior":"complete"}\n'
    output_path.write_bytes(original_bytes)
    monkeypatch.setattr(replay_module, "discover_session_paths", lambda **_kwargs: [session_dir])
    monkeypatch.setattr(replay_module, "load_session_events", lambda **_kwargs: [event])

    with pytest.raises(replay_module.IncompleteOutcomeWindowError, match="incomplete_outcome_window:truncated"):
        build_outcomes_for_date(
            replay_module._to_day_key(event.ts_epoch_ms),
            session_dir=session_dir,
            output_path=output_path,
            lookahead_minutes=3,
            series_loader=_series_loader_for([_horizon_row(0), _horizon_row(1)]),
        )

    assert output_path.read_bytes() == original_bytes
