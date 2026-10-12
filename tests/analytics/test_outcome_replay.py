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


def test_cli_requires_operator_to_explicitly_select_series_manifest():
    args = replay_module._build_cli().parse_args(
        ["--date", "2026-10-12", "--series-manifest", "/tmp/manifest.json"]
    )
    assert args.series_manifest == "/tmp/manifest.json"


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
    assert row["trade_outcome"]["exec_feasible"] is False
    assert row["trade_outcome"]["exec_feasible_flags"]["execution_feasibility_status"] == "UNASSESSED"
    assert row["trade_outcome"]["exec_feasible_flags"]["outcome_path_observed"] is True


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
    loader_calls = []

    def loader(*_args):
        loader_calls.append(True)
        return [_horizon_row(0)], "test_local_series"

    with pytest.raises(
        replay_module.IncompleteOutcomeWindowError,
        match="incomplete_outcome_window:event_not_on_source_bar_boundary",
    ):
        analyze_event_outcome(
            event,
            lookahead_minutes=3,
            candle_interval="minute",
            series_loader=loader,
        )
    assert loader_calls == []


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


def test_outcome_replay_uses_configured_nondefault_open_for_multiminute_grid(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(replay_module.cfg, "MARKET_OPEN_IST", "09:30")
    start = int(datetime(2025, 2, 28, 9, 30, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000)
    event = _horizon_event(reject_ts_epoch=start)
    rows = [
        {"time_ms": start, "high": 105.0, "low": 95.0, "ref_price": 100.0},
        {"time_ms": start + 2 * 60_000, "high": 105.0, "low": 95.0, "ref_price": 100.0},
    ]

    result = analyze_event_outcome(
        event, lookahead_minutes=4, candle_interval="2minute", series_loader=_series_loader_for(rows)
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


def test_atomic_writer_preserves_previous_output_and_cleans_temp_on_write_error(tmp_path, monkeypatch):
    output_path = tmp_path / "outcomes.jsonl"
    previous = b'{"prior":"preserved"}\n'
    output_path.write_bytes(previous)

    def fail_serialization(*_args, **_kwargs):
        raise OSError("simulated serialization failure")

    monkeypatch.setattr(replay_module.json, "dumps", fail_serialization)
    with pytest.raises(OSError, match="simulated serialization failure"):
        replay_module._atomic_write_jsonl(output_path, [{"new": "row"}])

    assert output_path.read_bytes() == previous
    assert list(tmp_path.glob(".outcomes.jsonl.*.tmp")) == []


def test_atomic_writer_uses_isolated_temps_for_concurrent_writers(tmp_path, monkeypatch):
    import threading

    output_path = tmp_path / "outcomes.jsonl"
    barrier = threading.Barrier(2)
    real_dumps = replay_module.json.dumps

    def synchronized_dumps(*args, **kwargs):
        barrier.wait(timeout=5)
        return real_dumps(*args, **kwargs)

    monkeypatch.setattr(replay_module.json, "dumps", synchronized_dumps)
    failures = []

    def write(value):
        try:
            replay_module._atomic_write_jsonl(output_path, [{"writer": value}])
        except BaseException as exc:  # Propagate worker failures through assertion below.
            failures.append(exc)

    threads = [threading.Thread(target=write, args=(value,)) for value in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not failures
    assert all(not thread.is_alive() for thread in threads)
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result in ({"writer": "a"}, {"writer": "b"})
    assert list(tmp_path.glob(".outcomes.jsonl.*.tmp")) == []


def test_batch_cli_manifest_persists_operator_provenance_and_safety_contract(tmp_path, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from tests.analytics.test_upstox_replay_source import _write_source

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    manifest_path, _, _ = _write_source(tmp_path)
    event_ts = int(datetime(2026, 10, 12, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000)
    candidate_row = {
        "candidate_id": "candidate_manifest_batch",
        "status": "REJECTED",
        "reject_reason": "TEST_REJECT",
        "ts_epoch_ms": event_ts,
        "symbol": "NIFTY",
        "expiry": "2026-10-29",
        "strike": 25000,
        "option_type": "CE",
        "side": "BUY",
        "entry_price": 100,
        "target_price": 200,
        "stop_loss": 50,
    }
    (session_dir / "candidate_journal.jsonl").write_text(json.dumps(candidate_row) + "\n", encoding="utf-8")
    monkeypatch.setattr(replay_module, "discover_session_paths", lambda **_kwargs: [session_dir])
    output_path = tmp_path / "outcomes.jsonl"

    report = build_outcomes_for_date(
        "2026-10-12", session_dir=session_dir, output_path=output_path,
        lookahead_minutes=2, series_manifest=manifest_path,
    )

    row = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])
    assert report["count"] == 1
    assert report["series_provenance"]["dataset_id"] == "capture-2026-10-12-nifty-25000ce"
    assert "file_sha256" not in report["series_provenance"]
    assert "instrument_token" not in report["series_provenance"]
    assert row["series_provenance"]["event_token_bound"] is False
    assert row["series_provenance"]["identity_binding_mode"] == "STRUCTURED_CONTRACT_AND_HASHED_OPERATOR_MASTER"
    assert row["series_provenance"]["provenance_status"] == "OPERATOR_SUPPLIED_UNVERIFIED"
    assert row["series_provenance"]["source_authenticity_verified"] is False
    assert row["series_provenance"]["instrument_token"] == "12345"
    assert row["trade_outcome"]["exec_feasible"] is False
    assert row["read_only"] is True
    assert row["is_order_action"] is False
    assert row["broker_api_called"] is False
    assert row["allowed_for_live_execution"] is False


def test_manifest_batch_failure_preserves_existing_output(tmp_path, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from tests.analytics.test_upstox_replay_source import _write_source

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    manifest_path, _, source = _write_source(tmp_path)
    source.write_text(source.read_text() + "\n", encoding="utf-8")
    event = TradeIntentEvent(
        trade_key="NIFTY|2026-10-29|25000|CE|BUY", event_id="evt_bad_manifest",
        intent="rejected",
        ts_epoch_ms=int(datetime(2026, 10, 12, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000),
        symbol="NIFTY", expiry="2026-10-29", strike=25000, option_type="CE", side="BUY",
        source="test", metrics_snapshot={"instrument_token": "12345", "entry": 100, "target": 200, "stop": 50},
    )
    monkeypatch.setattr(replay_module, "discover_session_paths", lambda **_kwargs: [session_dir])
    monkeypatch.setattr(replay_module, "load_session_events", lambda **_kwargs: [event])
    output_path = tmp_path / "outcomes.jsonl"
    output_path.write_bytes(b"previous\n")

    with pytest.raises(replay_module.IncompleteOutcomeWindowError, match="source_error:ReplaySourceError"):
        build_outcomes_for_date(
            "2026-10-12", session_dir=session_dir, output_path=output_path,
            lookahead_minutes=2, series_manifest=manifest_path,
        )
    assert output_path.read_bytes() == b"previous\n"


def test_multi_contract_batch_keeps_per_event_file_provenance(tmp_path, monkeypatch):
    from datetime import datetime
    import hashlib
    from zoneinfo import ZoneInfo

    from tests.analytics.test_upstox_replay_source import _write_source

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    manifest_path, manifest, _ = _write_source(tmp_path)
    second_source = tmp_path / "option-25200.csv"
    second_source.write_text(
        "timestamp,open,high,low,close\n"
        "2026-10-12T09:15:00+05:30,80,82,79,81\n"
        "2026-10-12T09:16:00+05:30,81,83,80,82\n",
        encoding="utf-8",
    )
    second_bytes = second_source.read_bytes()
    master_path = tmp_path / "instrument_master.csv"
    with master_path.open("a", encoding="utf-8") as handle:
        handle.write("23456,NIFTY,2026-10-29,25200,CE\n")
    master_bytes = master_path.read_bytes()
    manifest["instrument_master"].update(
        size_bytes=len(master_bytes), sha256=hashlib.sha256(master_bytes).hexdigest()
    )
    manifest["entries"].append(
        {
            "contract": {"underlying": "NIFTY", "expiry": "2026-10-29", "strike": 25200, "option_type": "CE"},
            "instrument_token": "23456",
            "path": second_source.name,
            "format": "csv",
            "size_bytes": len(second_bytes),
            "sha256": hashlib.sha256(second_bytes).hexdigest(),
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    event_ts = int(datetime(2026, 10, 12, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000)
    candidate_rows = [
        {
            "candidate_id": f"candidate-{strike}", "status": "REJECTED", "reject_reason": "TEST_REJECT",
            "ts_epoch_ms": event_ts, "symbol": "NIFTY", "expiry": "2026-10-29", "strike": strike,
            "option_type": "CE", "side": "BUY", "entry_price": 100, "target_price": 200, "stop_loss": 50,
        }
        for strike in (25000, 25200)
    ]
    journal = "\n".join(json.dumps(row) for row in candidate_rows) + "\n"
    (session_dir / "candidate_journal.jsonl").write_text(journal, encoding="utf-8")
    monkeypatch.setattr(replay_module, "discover_session_paths", lambda **_kwargs: [session_dir])
    output_path = tmp_path / "outcomes.jsonl"

    report = build_outcomes_for_date(
        "2026-10-12", session_dir=session_dir, output_path=output_path,
        lookahead_minutes=2, series_manifest=manifest_path,
    )

    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    source_receipts = report["series_sources"]
    assert report["count"] == len(rows) == len(source_receipts) == 2
    assert "file_sha256" not in report["series_provenance"]
    assert {item["series_provenance"]["instrument_token"] for item in source_receipts} == {"12345", "23456"}
    assert len({item["series_provenance"]["file_sha256"] for item in source_receipts}) == 2
    assert {row["series_provenance"]["contract"]["strike"] for row in rows} == {25000.0, 25200.0}
