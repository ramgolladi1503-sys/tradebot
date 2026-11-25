import json
import hashlib
import logging
import threading
import pytest
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.upstox_daily_live_capture_and_stitch import (
    CallbackAdmissionGate,
    DispatchAdmissionFence,
    RecorderAccountingSink,
    Mode5TraceHealthReporter,
    format_depth,
    get_options_subscriptions,
    execute_post_market_stitching,
    get_access_token,
    parse_mode5_trace_health_interval,
    finalize_capture_session,
    write_capture_health_report,
    _safe_trace_health_snapshot,
    run_capture_loop_safely,
    _run_bounded_shutdown_call,
    _trace_capture_status,
    _dispatch_with_lease,
    CaptureResourceRegistry,
    scan_existing_level5_chunks,
)


def _clean_recorder_accounting(record_count: int) -> dict:
    return {
        "input_count": record_count,
        "total_records_written": record_count,
        "known_drops": 0,
        "unknown_telemetry_count": 0,
        "input_error_count": 0,
        "last_error_type": None,
        "accounting_known": True,
    }


def _manifest_source_chunk(path: Path, values=(1, 2)) -> None:
    frame = pd.DataFrame({
        "exchange_timestamp_ms": list(values),
        "token": [f"token-{value}" for value in values],
        "symbol": [f"symbol-{value}" for value in values],
        "ltp": [100.0 + value for value in values],
    })
    pq.write_table(pa.Table.from_pandas(frame), path)


def _empty_historical_response():
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b'{"data":{"candles":[]}}'
    return Response()


def test_format_depth_valid_quotes():
    market_level = {
        "bidAskQuote": [
            {"bidP": 23500.5, "bidQ": 150, "bqo": 3, "askP": 23501.0, "askQ": 225, "aqo": 4},
            {"bidP": 23500.0, "bidQ": 300, "bqo": 5, "askP": 23501.5, "askQ": 100, "aqo": 2},
        ]
    }
    res_str = format_depth(market_level)
    parsed = json.loads(res_str)

    assert parsed["bids"][0]["price"] == 23500.5
    assert parsed["bids"][0]["quantity"] == 150
    assert parsed["bids"][0]["orders"] == 3
    assert parsed["asks"][0]["price"] == 23501.0
    assert parsed["asks"][0]["quantity"] == 225
    assert parsed["asks"][0]["orders"] == 4
    assert parsed["bids"][1]["price"] == 23500.0
    assert parsed["asks"][1]["price"] == 23501.5


def test_format_depth_empty_quotes():
    market_level = {}
    res_str = format_depth(market_level)
    parsed = json.loads(res_str)
    assert parsed == {"bids": [], "asks": []}


def test_get_options_subscriptions_resolution():
    today_ms = int(datetime.now().timestamp() * 1000)

    mock_data = [
        {"name": "NIFTY", "instrument_type": "CE", "strike_price": 24000.0, "expiry": today_ms, "instrument_key": "NSE_FO|101", "trading_symbol": "NIFTY 24000 CE"},
        {"name": "NIFTY", "instrument_type": "PE", "strike_price": 24000.0, "expiry": today_ms, "instrument_key": "NSE_FO|102", "trading_symbol": "NIFTY 24000 PE"},
        {"name": "NIFTY", "instrument_type": "CE", "strike_price": 24050.0, "expiry": today_ms, "instrument_key": "NSE_FO|103", "trading_symbol": "NIFTY 24050 CE"},
        {"name": "NIFTY", "instrument_type": "PE", "strike_price": 23950.0, "expiry": today_ms, "instrument_key": "NSE_FO|104", "trading_symbol": "NIFTY 23950 PE"},
        {"name": "BANKNIFTY", "instrument_type": "CE", "strike_price": 50000.0, "expiry": today_ms, "instrument_key": "NSE_FO|201", "trading_symbol": "BANKNIFTY 50000 CE"},
        {"name": "SENSEX", "instrument_type": "PE", "strike_price": 78000.0, "expiry": today_ms, "instrument_key": "BSE_FO|301", "trading_symbol": "SENSEX 78000 PE"},
    ]
    df_inst = pd.DataFrame(mock_data)
    prices = {"NIFTY": 24010.0, "BANKNIFTY": 50020.0, "SENSEX": 78040.0}

    subs = get_options_subscriptions(df_inst, prices)

    assert subs.get("NSE_INDEX|Nifty 50") == "NIFTY 50"
    assert subs.get("NSE_INDEX|Nifty Bank") == "NIFTY BANK"
    assert subs.get("BSE_INDEX|SENSEX") == "SENSEX"
    assert subs.get("NSE_FO|101") == "NIFTY 24000 CE"
    assert subs.get("NSE_FO|102") == "NIFTY 24000 PE"
    assert subs.get("NSE_FO|103") == "NIFTY 24050 CE"
    assert subs.get("NSE_FO|104") == "NIFTY 23950 PE"
    assert subs.get("NSE_FO|201") == "BANKNIFTY 50000 CE"
    assert subs.get("BSE_FO|301") == "SENSEX 78000 PE"


def test_execute_post_market_stitching_creates_master(tmp_path, monkeypatch):
    class EmptyHistoricalResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @staticmethod
        def read():
            return b'{"data":{"candles":[]}}'

    monkeypatch.setattr(
        "scripts.upstox_daily_live_capture_and_stitch.urllib.request.urlopen",
        lambda *args, **kwargs: EmptyHistoricalResponse(),
    )
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    schema = pa.schema([
        ("ts", pa.float64()),
        ("token", pa.string()),
        ("symbol", pa.string()),
        ("ltp", pa.float64()),
        ("bid", pa.float64()),
        ("ask", pa.float64()),
        ("vol", pa.float64()),
        ("oi", pa.float64()),
        ("depth", pa.string())
    ])

    chunk1_data = {
        "ts": [1789500000.0, 1789500001.0],
        "token": ["NSE_INDEX|Nifty 50", "NSE_FO|101"],
        "symbol": ["NIFTY 50", "NIFTY 24000 CE"],
        "ltp": [24000.0, 150.0],
        "bid": [0.0, 149.5],
        "ask": [0.0, 150.5],
        "vol": [0.0, 5000.0],
        "oi": [0.0, 10000.0],
        "depth": ["{}", "{}"]
    }
    chunk2_data = {
        "ts": [1789500001.0, 1789500002.0],
        "token": ["NSE_FO|101", "NSE_INDEX|Nifty Bank"],
        "symbol": ["NIFTY 24000 CE", "NIFTY BANK"],
        "ltp": [150.0, 50000.0],
        "bid": [149.5, 0.0],
        "ask": [150.5, 0.0],
        "vol": [5000.0, 0.0],
        "oi": [10000.0, 0.0],
        "depth": ["{}", "{}"]
    }

    pq.write_table(pa.Table.from_pandas(pd.DataFrame(chunk1_data), schema=schema), chunks_dir / "chunk_1.parquet")
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(chunk2_data), schema=schema), chunks_dir / "chunk_2.parquet")

    date_str = "2026-09-17"
    date_compact = "20260917"

    execute_post_market_stitching(
        date_str,
        date_compact,
        tmp_path,
        chunk_manifest=(chunks_dir / "chunk_1.parquet", chunks_dir / "chunk_2.parquet"),
        capture_run_id="direct-test-run",
        recorder_accounting=_clean_recorder_accounting(4),
    )

    stitched_file = tmp_path / f"upstox_full_ticks_{date_compact}_stitched.parquet"
    summary_file = tmp_path / f"stitching_summary_{date_compact}.json"

    assert stitched_file.is_file() == True
    assert summary_file.is_file() == True

    df_stitched = pd.read_parquet(stitched_file)
    assert int(df_stitched.shape[0]) == 3
    assert int(df_stitched.isnull().sum().sum()) == 0
    assert tuple(df_stitched.columns) == ("ts", "token", "symbol", "ltp", "bid", "ask", "vol", "oi", "depth")
    assert float(df_stitched["ltp"].iloc[0]) == 24000.0
    assert str(df_stitched["token"].iloc[0]) == "NSE_INDEX|Nifty 50"

    with open(summary_file) as f:
        summary_report = json.load(f)
        assert summary_report["total_chunks"] == 2
        assert summary_report["total_ticks"] == 3
        assert summary_report["duplicates_removed"] == 1
        assert summary_report["unique_tokens"] == 3
        assert summary_report["date"] == "2026-09-17"


def test_stitch_fails_before_replacing_outputs_when_any_manifest_chunk_is_unreadable(tmp_path):
    from scripts.upstox_daily_live_capture_and_stitch import execute_post_market_stitching

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    readable = chunks_dir / "readable.parquet"
    unreadable = chunks_dir / "unreadable.parquet"
    pq.write_table(pa.table({"value": [1]}), readable)
    unreadable.write_bytes(b"not a parquet file")
    date_compact = "20261119"
    master = tmp_path / f"upstox_full_ticks_{date_compact}_stitched.parquet"
    summary = tmp_path / f"stitching_summary_{date_compact}.json"
    master.write_bytes(b"previous-master")
    summary.write_text('{"previous": true}')

    result = execute_post_market_stitching(
        "2026-11-19", date_compact, tmp_path,
        chunk_manifest=(readable, unreadable),
        capture_run_id="unreadable-test-run",
        recorder_accounting=_clean_recorder_accounting(1),
    )
    assert result["status"] == "FAILED_CHUNK_READ"
    assert master.read_bytes() == b"previous-master"
    assert summary.read_text() == '{"previous": true}'


@pytest.mark.parametrize(
    ("manifest_factory", "expected_status"),
    [
        (lambda chunks, outside: (chunks / "missing.parquet",), "FAILED_CHUNK_READ"),
        (lambda chunks, outside: (chunks / "same.parquet", chunks / "same.parquet"), "INVALID_MANIFEST"),
        (lambda chunks, outside: (outside,), "INVALID_MANIFEST"),
    ],
)
def test_stitch_rejects_missing_duplicate_or_out_of_directory_manifest_entries(
    tmp_path, manifest_factory, expected_status
):
    from scripts.upstox_daily_live_capture_and_stitch import execute_post_market_stitching

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    same = chunks_dir / "same.parquet"
    pq.write_table(pa.table({"value": [1]}), same)
    outside = tmp_path / "outside.parquet"
    pq.write_table(pa.table({"value": [2]}), outside)
    date_compact = "20261119"
    master = tmp_path / f"upstox_full_ticks_{date_compact}_stitched.parquet"
    summary = tmp_path / f"stitching_summary_{date_compact}.json"
    master.write_bytes(b"old-master")
    summary.write_text("old-summary")

    result = execute_post_market_stitching(
        "2026-11-19", date_compact, tmp_path,
        chunk_manifest=manifest_factory(chunks_dir, outside),
        capture_run_id="invalid-manifest-test-run",
        recorder_accounting=_clean_recorder_accounting(1),
    )
    assert result["status"] == expected_status
    assert master.read_bytes() == b"old-master"
    assert summary.read_text() == "old-summary"


def test_stitch_does_not_glob_chunks_when_frozen_manifest_is_empty(tmp_path):
    from scripts.upstox_daily_live_capture_and_stitch import execute_post_market_stitching

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    pq.write_table(pa.table({"value": [1]}), chunks_dir / "orphan.parquet")
    result = execute_post_market_stitching(
        "2026-11-19", "20261119", tmp_path, chunk_manifest=(),
        capture_run_id="empty-manifest-test-run",
        recorder_accounting=_clean_recorder_accounting(0),
    )
    assert result["status"] == "NO_CHUNKS"
    assert not (tmp_path / "upstox_full_ticks_20261119_stitched.parquet").exists()


def test_stitch_rejects_symlink_manifest_entry(tmp_path):
    from scripts.upstox_daily_live_capture_and_stitch import execute_post_market_stitching

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    target = chunks_dir / "target.parquet"
    link = chunks_dir / "link.parquet"
    pq.write_table(pa.table({"value": [1]}), target)
    link.symlink_to(target)

    result = execute_post_market_stitching(
        "2026-11-19", "20261119", tmp_path, chunk_manifest=(link,),
        capture_run_id="symlink-manifest-test-run",
        recorder_accounting=_clean_recorder_accounting(1),
    )
    assert result["status"] == "INVALID_MANIFEST"
    assert not (tmp_path / "upstox_full_ticks_20261119_stitched.parquet").exists()
    assert not (tmp_path / "stitching_summary_20261119.json").exists()


def test_stitch_rejects_non_parquet_manifest_suffix(tmp_path):
    from scripts.upstox_daily_live_capture_and_stitch import execute_post_market_stitching

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    mislabeled = chunks_dir / "chunk.pq"
    pq.write_table(pa.table({"value": [1]}), mislabeled)

    result = execute_post_market_stitching(
        "2026-11-19", "20261119", tmp_path, chunk_manifest=(mislabeled,),
        capture_run_id="suffix-manifest-test-run",
        recorder_accounting=_clean_recorder_accounting(1),
    )
    assert result["status"] == "INVALID_MANIFEST"
    assert not (tmp_path / "upstox_full_ticks_20261119_stitched.parquet").exists()
    assert not (tmp_path / "stitching_summary_20261119.json").exists()


def test_token_retrieval_fallback():
    token = get_access_token()
    assert isinstance(token, str) == True


def test_refresh_late_day_option_subscriptions():
    from core.upstox_capture.late_day_option_refresh import refresh_late_day_option_subscriptions

    class MockStreamer:
        def __init__(self):
            self.subscribed_keys = []

        def subscribe(self, keys, mode="full"):
            self.subscribed_keys.extend(keys)

    today_ms = int(datetime.now().timestamp() * 1000)
    mock_data = [
        # Existing morning subscriptions around 23500
        {"name": "NIFTY", "instrument_type": "CE", "strike_price": 23500.0, "expiry": today_ms, "instrument_key": "NSE_FO|101", "trading_symbol": "NIFTY 23500 CE"},
        {"name": "NIFTY", "instrument_type": "PE", "strike_price": 23500.0, "expiry": today_ms, "instrument_key": "NSE_FO|102", "trading_symbol": "NIFTY 23500 PE"},
        # New strikes around 23200 (after 300 pt drop)
        {"name": "NIFTY", "instrument_type": "CE", "strike_price": 23200.0, "expiry": today_ms, "instrument_key": "NSE_FO|201", "trading_symbol": "NIFTY 23200 CE"},
        {"name": "NIFTY", "instrument_type": "PE", "strike_price": 23200.0, "expiry": today_ms, "instrument_key": "NSE_FO|202", "trading_symbol": "NIFTY 23200 PE"},
        {"name": "NIFTY", "instrument_type": "CE", "strike_price": 23150.0, "expiry": today_ms, "instrument_key": "NSE_FO|203", "trading_symbol": "NIFTY 23150 CE"},
        {"name": "NIFTY", "instrument_type": "PE", "strike_price": 23150.0, "expiry": today_ms, "instrument_key": "NSE_FO|204", "trading_symbol": "NIFTY 23150 PE"},
    ]
    df_inst = pd.DataFrame(mock_data)
    streamer = MockStreamer()
    subscriptions = {
        "NSE_FO|101": "NIFTY 23500 CE",
        "NSE_FO|102": "NIFTY 23500 PE",
    }

    # Spot price drops to 23172.0 (ATM 23150 or 23200)
    new_count = refresh_late_day_option_subscriptions(
        streamer=streamer,
        subscriptions=subscriptions,
        df_inst=df_inst,
        current_spot_price=23172.0
    )

    # Must subscribe 23200 and 23150 strikes which were missing
    assert new_count == 4
    assert "NSE_FO|201" in subscriptions
    assert "NSE_FO|202" in subscriptions
    assert "NSE_FO|203" in subscriptions
    assert "NSE_FO|204" in subscriptions
    assert len(streamer.subscribed_keys) == 4
    # Existing morning subscriptions must remain intact
    assert "NSE_FO|101" in subscriptions
    assert "NSE_FO|102" in subscriptions


class _CaptureLog:
    def __init__(self, *, fail_info=False, fail_warning=False):
        self.rows = []
        self.fail_info = fail_info
        self.fail_warning = fail_warning

    def info(self, message, *args):
        if self.fail_info:
            raise RuntimeError("logger unavailable")
        self.rows.append(("info", message % args if args else message))

    def warning(self, message, *args):
        if self.fail_warning:
            raise RuntimeError("logger unavailable")
        self.rows.append(("warning", message % args if args else message))


def test_mode5_trace_health_interval_is_bounded_and_warns_without_echoing_value():
    warnings = _CaptureLog()
    assert parse_mode5_trace_health_interval(None, warnings) == 60.0
    assert parse_mode5_trace_health_interval("5", warnings) == 5.0
    assert parse_mode5_trace_health_interval("3600", warnings) == 3600.0
    assert warnings.rows == []

    for invalid in ("secret-like-invalid", "4", "3601", "NaN", "Infinity"):
        single_warning = _CaptureLog()
        assert parse_mode5_trace_health_interval(invalid, single_warning) == 60.0
        assert len(single_warning.rows) == 1
        assert invalid not in single_warning.rows[0][1]


def test_mode5_trace_health_reporter_uses_monotonic_interval_and_degraded_heartbeat():
    monotonic = [0.0]
    degraded = [False]
    logs = _CaptureLog()
    health = {
        "capacity": 1536,
        "max_record_bytes": 16384,
        "queue_depth": 0,
        "pending_unpersisted": 0,
        "enqueued": 0,
        "append_successes": 0,
        "append_failures": 0,
        "queue_full_drops": 0,
        "oversize_drops": 0,
        "writer_unavailable_drops": 0,
        "active_writes": 0,
        "last_persisted_sequence": None,
        "last_processed_sequence": None,
        "writer_status": "RUNNING",
        "degraded": False,
        "last_error": None,
    }

    class Advisor:
        trace_run_id = "run-1"

        @staticmethod
        def get_mode5_trace_health_snapshot():
            snapshot = dict(health)
            snapshot["degraded"] = degraded[0]
            return snapshot

    reporter = Mode5TraceHealthReporter(
        Advisor(), interval_sec=5.0, monotonic_clock=lambda: monotonic[0], log=logs
    )
    monotonic[0] = 4.99
    assert reporter.maybe_report()["status"] == "AVAILABLE"
    assert [level for level, _ in logs.rows] == ["info"]
    monotonic[0] = 5.0
    reporter.maybe_report()
    assert [level for level, _ in logs.rows] == ["info"]
    monotonic[0] = 9.99
    reporter.maybe_report()
    assert [level for level, _ in logs.rows] == ["info", "info"]
    monotonic[0] = 10.0
    reporter.maybe_report()
    assert [level for level, _ in logs.rows] == ["info", "info"]

    degraded[0] = True
    monotonic[0] = 15.0
    reporter.maybe_report()
    assert [level for level, _ in logs.rows].count("warning") == 1
    monotonic[0] = 310.0
    reporter.maybe_report()
    assert [level for level, _ in logs.rows].count("warning") == 1
    monotonic[0] = 315.0
    reporter.maybe_report()
    assert [level for level, _ in logs.rows].count("warning") == 2


def test_mode5_trace_health_reporter_getter_and_logger_failures_are_isolated():
    monotonic = [0.0]
    logs = _CaptureLog(fail_info=True, fail_warning=True)

    class BrokenAdvisor:
        trace_run_id = "run-broken"

        @staticmethod
        def get_mode5_trace_health_snapshot():
            raise RuntimeError("contains secret token and is never reported")

    reporter = Mode5TraceHealthReporter(
        BrokenAdvisor(), interval_sec=5.0, monotonic_clock=lambda: monotonic[0], log=logs
    )
    monotonic[0] = 5.0
    snapshot = reporter.maybe_report()
    assert snapshot["status"] == "ERROR"
    assert snapshot["health_error_type"] == "RuntimeError"
    assert reporter.reporting_failures == 2
    assert reporter.last_reporting_error_type == "RuntimeError"


def test_health_schema_rejects_missing_fields_and_unknown_run_id():
    class Advisor:
        trace_run_id = "schema-run"

        @staticmethod
        def get_mode5_trace_health_snapshot():
            return {"capacity": 12, "queue_depth": 0, "writer_status": "STOPPED"}

    snapshot = _safe_trace_health_snapshot(Advisor())
    assert snapshot["status"] == "ERROR"

    Advisor.trace_run_id = "UNKNOWN"
    assert _safe_trace_health_snapshot(Advisor())["status"] == "ERROR"


def test_capture_loop_cleanup_runs_and_preserves_interrupts():
    interrupt = KeyboardInterrupt()
    cleanup_calls = []

    def interrupted_loop():
        raise interrupt

    with pytest.raises(KeyboardInterrupt) as exc:
        run_capture_loop_safely(
            interrupted_loop,
            lambda error_type: cleanup_calls.append(error_type) or {"exit_code": 0},
        )
    assert exc.value is interrupt
    assert cleanup_calls == ["KeyboardInterrupt"]

    report, status = run_capture_loop_safely(
        lambda: (_ for _ in ()).throw(RuntimeError("loop error")),
        lambda error_type: {"error_type": error_type, "exit_code": 0},
    )
    assert report["error_type"] == "RuntimeError"
    assert status == 1

    system_exit = SystemExit(17)
    with pytest.raises(SystemExit) as system_exit_result:
        run_capture_loop_safely(
            lambda: (_ for _ in ()).throw(system_exit),
            lambda error_type: {"exit_code": 0},
        )
    assert system_exit_result.value is system_exit


def test_shutdown_worker_start_failure_is_reportable_and_fail_closed(monkeypatch):
    from scripts import upstox_daily_live_capture_and_stitch as capture

    class StartFailureThread:
        def __init__(self, *args, **kwargs):
            self.daemon = kwargs.get("daemon", False)

        def start(self):
            raise OSError("cannot start shutdown worker")

    monkeypatch.setattr(capture.threading, "Thread", StartFailureThread)
    result = _run_bounded_shutdown_call("start-fail", lambda: None, 0.01)
    assert result["status"] == "START_FAILED"
    assert result["error_type"] == "OSError"
    assert result["worker_alive"] is False


def test_callback_admission_gate_drains_admitted_callback_and_counts_late_callbacks():
    gate = CallbackAdmissionGate()
    callback_started = threading.Event()
    release_callback = threading.Event()
    observed = []

    def callback(value):
        callback_started.set()
        assert release_callback.wait(timeout=2)
        observed.append(value)

    admitted = gate.wrap(callback)
    thread = threading.Thread(target=admitted, args=("admitted",))
    thread.start()
    assert callback_started.wait(timeout=1)
    gate.close_admission()
    assert admitted("late") is None
    assert gate.wait_for_quiescence(timeout_sec=0.01) is False
    timed_out = gate.snapshot()
    assert timed_out["active_callback_count"] == 1
    assert timed_out["late_callback_rejects_at_snapshot"] == 1

    release_callback.set()
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert gate.wait_for_quiescence(timeout_sec=1.0) is True
    assert observed == ["admitted"]
    assert gate.snapshot()["active_callback_count"] == 0


def test_capture_finalization_orders_disconnect_gate_drains_report_then_stitch(
    tmp_path, monkeypatch
):
    events = []
    report_path = tmp_path / "capture_health_summary_20261119.json"
    writer = write_capture_health_report

    def observe_report(path, report):
        events.append(f"report:{report['report_stage']}")
        return writer(path, report)

    monkeypatch.setattr(
        "scripts.upstox_daily_live_capture_and_stitch.write_capture_health_report",
        observe_report,
    )

    class Streamer:
        def disconnect(self):
            events.append("disconnect")
            raise RuntimeError("disconnect failed")

    class Gate(CallbackAdmissionGate):
        def close_admission(self):
            events.append("close_gate")
            return super().close_admission()

        def wait_for_quiescence(self, timeout_sec=10.0):
            events.append("wait_callbacks")
            return super().wait_for_quiescence(timeout_sec)

    class Recorder:
        total_records_written = 3
        _worker_thread = SimpleNamespace(is_alive=lambda: False)

        class Queue:
            @staticmethod
            def qsize():
                return 0

        _queue = Queue()

        @staticmethod
        def flush_and_stop(timeout):
            events.append("recorder_stop")

    class Advisor:
        trace_run_id = "test-trace-run"

        @staticmethod
        def shutdown_mode5_trace_writer(timeout_sec):
            events.append("advisor_drain")
            return {
                "capacity": 1536, "max_record_bytes": 16384,
                "queue_depth": 0, "pending_unpersisted": 0,
                "enqueued": 3, "append_successes": 3,
                "append_failures": 0, "queue_full_drops": 0,
                "oversize_drops": 0, "writer_unavailable_drops": 0,
                "active_writes": 0, "last_persisted_sequence": 3,
                "last_processed_sequence": 3, "writer_status": "STOPPED",
                "degraded": False, "last_error": None,
            }

    def stitch(date_str, date_compact, data_dir):
        events.append("stitch")
        pre = json.loads(report_path.read_text())
        assert pre["report_stage"] == "PRE_STITCH"
        assert pre["stitch_status"] == "PENDING"
        return {"status": "COMPLETED", "stitched": True}

    result = finalize_capture_session(
        streamer=Streamer(), callback_gate=Gate(), dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(),
        recorder_accounting=SimpleNamespace(snapshot=lambda: {
            "input_count": 3, "known_drops": 0, "unknown_telemetry_count": 0,
            "input_error_count": 0, "last_error_type": None, "accounting_known": True,
        }), advisor=Advisor(),
        report_path=report_path, date_str="2026-11-19", date_compact="20261119",
        stitch_callable=stitch,
    )
    assert events == [
        "disconnect", "close_gate", "wait_callbacks", "recorder_stop", "advisor_drain",
        "report:PRE_STITCH", "report:POST_STITCH_UPDATE",
    ]
    assert result["disconnect_status"] == "RAISED"
    assert result["trace_capture_status"] == "DEGRADED"
    assert result["stitch_status"] == "SKIPPED_DISCONNECT_UNCONFIRMED"
    assert result["pre_stitch_report_status"] == "WRITTEN"
    assert result["final_report_update_status"] == "WRITTEN"
    final_report = json.loads(report_path.read_text())
    assert final_report["trace_capture_status"] == "DEGRADED"
    assert final_report["stitch_status"] == "SKIPPED_DISCONNECT_UNCONFIRMED"
    assert final_report["trace_run_id"] == "test-trace-run"


def test_capture_finalization_drain_error_cannot_be_reported_healthy(tmp_path):
    class Streamer:
        @staticmethod
        def disconnect():
            return None

    class Recorder:
        total_records_written = 0
        _worker_thread = None
        _queue = None

        @staticmethod
        def flush_and_stop(timeout):
            return None

    class Advisor:
        trace_run_id = "drain-error-run"

        @staticmethod
        def shutdown_mode5_trace_writer(timeout_sec):
            raise RuntimeError("internal error details must not enter report")

        @staticmethod
        def get_mode5_trace_health_snapshot():
            return {
                "capacity": 10, "max_record_bytes": 16384, "queue_depth": 0,
                "pending_unpersisted": 0, "enqueued": 0, "append_successes": 0,
                "append_failures": 0, "queue_full_drops": 0, "oversize_drops": 0,
                "writer_unavailable_drops": 0, "active_writes": 0,
                "last_persisted_sequence": None, "last_processed_sequence": None,
                "writer_status": "STOPPED", "degraded": False, "last_error": None,
            }

    report = finalize_capture_session(
        streamer=Streamer(), callback_gate=CallbackAdmissionGate(), dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(),
        recorder_accounting=SimpleNamespace(snapshot=lambda: {
            "input_count": 0, "known_drops": 0, "unknown_telemetry_count": 0,
            "input_error_count": 0, "last_error_type": None, "accounting_known": True,
        }),
        advisor=Advisor(), report_path=tmp_path / "drain-error.json",
        date_str="2026-11-19", date_compact="20261119",
        stitch_callable=lambda *args: {"status": "COMPLETED"},
    )
    assert report["advisor_drain_status"] == "ERROR"
    assert report["trace_capture_status"] == "DEGRADED"
    assert report["run_capture_status"] == "DEGRADED"
    assert "internal error details" not in (tmp_path / "drain-error.json").read_text()


def test_capture_finalization_callback_timeout_skips_cleanup_unregisters_atexit_and_stitch(tmp_path, monkeypatch):
    from scripts import upstox_daily_live_capture_and_stitch as capture

    gate = CallbackAdmissionGate()
    callback_started = threading.Event()
    release_callback = threading.Event()

    def blocked_callback():
        callback_started.set()
        assert release_callback.wait(timeout=2)

    wrapped = gate.wrap(blocked_callback)
    thread = threading.Thread(target=wrapped)
    thread.start()
    assert callback_started.wait(timeout=1)

    class Streamer:
        @staticmethod
        def disconnect():
            return None

    class Recorder:
        total_records_written = 1
        _worker_thread = None
        _queue = None

        @staticmethod
        def flush_and_stop(timeout):
            return None

    exact_atexit_callback = object()
    unregistered = []
    monkeypatch.setattr(capture.atexit, "unregister", lambda callback: unregistered.append(callback))

    class Advisor:
        trace_run_id = "timeout-run"
        _mode5_trace_atexit_callback = exact_atexit_callback

        @staticmethod
        def shutdown_mode5_trace_writer(timeout_sec):
            pytest.fail("advisor drain must not run while callback is active")

    stitched = []
    try:
        report = finalize_capture_session(
            streamer=Streamer(), callback_gate=gate, dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(), advisor=Advisor(),
            report_path=tmp_path / "timeout-report.json", date_str="2026-11-19",
            date_compact="20261119", stitch_callable=lambda *args: (stitched.append(True) or {"status": "COMPLETED"}),
            callback_timeout_sec=0.01,
        )
        assert report["callback_quiescence_status"] == "CALLBACK_QUIESCENCE_TIMEOUT"
        assert report["active_callback_count"] == 1
        assert report["late_callback_rejects_at_report"] == 0
        assert report["late_callback_rejects_at_report_timestamp_utc"]
        assert report["trace_capture_status"] == "DEGRADED"
        assert report["recorder_status"] == "SKIPPED_CALLBACK_QUIESCENCE_TIMEOUT"
        assert report["advisor_drain_status"] == "SKIPPED_CALLBACK_QUIESCENCE_TIMEOUT"
        assert report["advisor_atexit_unregister_status"] == "UNREGISTERED"
        assert unregistered == [exact_atexit_callback]
        assert report["stitch_status"] == "SKIPPED_CALLBACK_QUIESCENCE_TIMEOUT"
        assert report["exit_code"] == 1
        assert stitched == []
    finally:
        release_callback.set()
        thread.join(timeout=1)
    assert not thread.is_alive()


def _valid_trace_snapshot(run_id="run-test", writer_status="STOPPED"):
    return {
        "capacity": 32,
        "max_record_bytes": 16384,
        "queue_depth": 0,
        "pending_unpersisted": 0,
        "enqueued": 1,
        "append_successes": 1,
        "append_failures": 0,
        "queue_full_drops": 0,
        "oversize_drops": 0,
        "writer_unavailable_drops": 0,
        "active_writes": 0,
        "last_persisted_sequence": 1,
        "last_processed_sequence": 1,
        "writer_status": writer_status,
        "degraded": writer_status != "STOPPED",
        "last_error": None,
    }


def test_trace_health_requires_consistent_sequences_capacity_and_record_size():
    class Advisor:
        trace_run_id = "sequence-test-run"

        def __init__(self, snapshot):
            self.snapshot = snapshot

        def get_mode5_trace_health_snapshot(self):
            return self.snapshot

    healthy_snapshot = _valid_trace_snapshot()
    healthy = _safe_trace_health_snapshot(Advisor(healthy_snapshot))
    assert healthy["status"] == "AVAILABLE"
    assert _trace_capture_status(
        healthy,
        disconnect_status="RETURNED",
        advisor_drain_status="STOPPED",
        callback_status="QUIESCENT",
    ) == "HEALTHY"

    empty = _valid_trace_snapshot()
    empty.update(enqueued=0, append_successes=0, last_persisted_sequence=0, last_processed_sequence=None)
    empty_health = _safe_trace_health_snapshot(Advisor(empty))
    assert _trace_capture_status(
        empty_health,
        disconnect_status="RETURNED",
        advisor_drain_status="STOPPED",
        callback_status="QUIESCENT",
    ) == "HEALTHY"

    recovered_failure = _valid_trace_snapshot()
    recovered_failure.update(append_failures=3, degraded=True)
    recovered_health = _safe_trace_health_snapshot(Advisor(recovered_failure))
    assert recovered_health["status"] == "AVAILABLE"
    assert _trace_capture_status(
        recovered_health,
        disconnect_status="RETURNED",
        advisor_drain_status="STOPPED",
        callback_status="QUIESCENT",
    ) == "DEGRADED"

    successes_exceeding_enqueues = _valid_trace_snapshot()
    successes_exceeding_enqueues.update(enqueued=0)
    assert _safe_trace_health_snapshot(Advisor(successes_exceeding_enqueues))["status"] == "ERROR"

    invalid_record_limit = _valid_trace_snapshot()
    invalid_record_limit["max_record_bytes"] = 0
    invalid_health = _safe_trace_health_snapshot(Advisor(invalid_record_limit))
    assert _trace_capture_status(
        invalid_health,
        disconnect_status="RETURNED",
        advisor_drain_status="STOPPED",
        callback_status="QUIESCENT",
    ) == "DEGRADED"

    unstable_sequences = _valid_trace_snapshot()
    unstable_sequences["last_processed_sequence"] = 2
    unstable_health = _safe_trace_health_snapshot(Advisor(unstable_sequences))
    assert _trace_capture_status(
        unstable_health,
        disconnect_status="RETURNED",
        advisor_drain_status="STOPPED",
        callback_status="QUIESCENT",
    ) == "DEGRADED"



def test_disconnect_is_bounded_before_gate_closes_and_late_callbacks_reject(tmp_path):
    release_disconnect = threading.Event()
    events = []
    gate = CallbackAdmissionGate()

    class Streamer:
        def disconnect(self):
            assert threading.current_thread().daemon
            events.append("disconnect-start")
            release_disconnect.wait(timeout=2)

    class Recorder:
        _worker_thread = None
        class Queue:
            @staticmethod
            def qsize():
                return 0
        _queue = Queue()
        def flush_and_stop(self, timeout):
            assert threading.current_thread().daemon
            events.append("recorder-stop")

    class Advisor:
        trace_run_id = "disconnect-test-run"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            assert threading.current_thread().daemon
            events.append("advisor-drain")
            return _valid_trace_snapshot(self.trace_run_id)

        def get_mode5_trace_health_snapshot(self):
            return _valid_trace_snapshot(self.trace_run_id)

    stitched = []
    try:
        report = finalize_capture_session(
            streamer=Streamer(), callback_gate=gate, dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(), advisor=Advisor(),
            report_path=tmp_path / "disconnect-timeout.json", date_str="2026-11-19",
            date_compact="20261119", stitch_callable=lambda *args: (stitched.append(True) or {"status": "COMPLETED"}),
            disconnect_timeout_sec=0.01,
        )
        assert report["disconnect_status"] == "TIMED_OUT"
        assert report["disconnect_worker_alive"] is True
        assert report["callback_quiescence_status"] == "QUIESCENT"
        assert events[0] == "disconnect-start"
        assert "recorder-stop" in events and "advisor-drain" in events
        assert gate.wrap(lambda: pytest.fail("late callback must not be admitted"))() is None
        assert gate.snapshot()["late_callback_rejects_at_snapshot"] == 1
        assert report["late_callback_rejects_at_report"] == 0
        assert report["late_callback_rejects_at_report_timestamp_utc"]
        assert report["callbacks_may_arrive_after_disconnect_timeout"] is True
        assert report["trace_capture_status"] == "DEGRADED"
        assert report["exit_code"] == 1
        assert report["stitch_status"] == "SKIPPED_DISCONNECT_UNCONFIRMED"
        assert stitched == []
    finally:
        release_disconnect.set()


def test_bounded_recorder_and_advisor_timeout_status_and_stitch(tmp_path):
    release = threading.Event()
    events = []

    class Streamer:
        def disconnect(self):
            return None

    class Recorder:
        _worker_thread = None
        _queue = None
        def flush_and_stop(self, timeout):
            events.append("recorder")
            release.wait(timeout=2)

    class Advisor:
        trace_run_id = "writer-timeout-run"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            events.append("advisor")
            release.wait(timeout=2)

        def get_mode5_trace_health_snapshot(self):
            return _valid_trace_snapshot(self.trace_run_id, writer_status="RUNNING")

    stitched = []
    try:
        report = finalize_capture_session(
            streamer=Streamer(), callback_gate=CallbackAdmissionGate(), dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(), advisor=Advisor(),
            report_path=tmp_path / "writer-timeout.json", date_str="2026-11-19",
            date_compact="20261119", stitch_callable=lambda *args: (stitched.append(True) or {"status": "COMPLETED"}),
            recorder_timeout_sec=0.01, advisor_timeout_sec=0.01,
        )
        assert report["recorder_status"] == "TIMED_OUT"
        assert report["advisor_drain_status"] == "TIMED_OUT"
        assert report["recorder_shutdown_worker_alive"] is True
        assert report["advisor_shutdown_worker_alive"] is True
        assert events == ["recorder", "advisor"]
        assert report["stitch_status"] == "SKIPPED_RECORDER_NOT_POSITIVELY_STOPPED"
        assert stitched == []
        assert report["exit_code"] == 1
    finally:
        release.set()


def test_report_write_failure_is_explicit_and_skips_stitch(tmp_path, monkeypatch):
    from scripts import upstox_daily_live_capture_and_stitch as capture

    def fail_report(*args, **kwargs):
        raise OSError("report write failed")

    monkeypatch.setattr(capture, "write_capture_health_report", fail_report)
    calls = []

    class Streamer:
        def disconnect(self):
            return None

    class Recorder:
        total_records_written = 0
        _worker_thread = SimpleNamespace(is_alive=lambda: False)
        _queue = SimpleNamespace(qsize=lambda: 0)
        def flush_and_stop(self, timeout):
            return None

    class Advisor:
        trace_run_id = "report-failure-run"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            return _valid_trace_snapshot(self.trace_run_id)

    report = finalize_capture_session(
        streamer=Streamer(), callback_gate=CallbackAdmissionGate(), dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(),
        recorder_accounting=SimpleNamespace(snapshot=lambda: {
            "input_count": 0, "known_drops": 0, "unknown_telemetry_count": 0,
            "input_error_count": 0, "last_error_type": None, "accounting_known": True,
        }),
        advisor=Advisor(), report_path=tmp_path / "not-written.json", date_str="2026-11-19",
        date_compact="20261119", stitch_callable=lambda *args: (calls.append("stitch") or {"status": "COMPLETED"}),
    )
    assert report["pre_stitch_report_status"] == "FAILED"
    assert report["final_report_update_status"] == "FAILED"
    assert report["report_error_type"] == "OSError"
    assert calls == []
    assert report["stitch_status"] == "SKIPPED_REPORT_PERSISTENCE_FAILURE"
    assert report["exit_code"] == 1


def test_capture_finalization_requires_full_positive_health_proof(tmp_path):
    class Streamer:
        def disconnect(self):
            return None

    class Recorder:
        total_records_written = 1
        _worker_thread = SimpleNamespace(is_alive=lambda: False)
        _queue = SimpleNamespace(qsize=lambda: 0)
        def flush_and_stop(self, timeout):
            return None

    class Advisor:
        trace_run_id = "healthy-proof-run"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            return _valid_trace_snapshot(self.trace_run_id)

    report = finalize_capture_session(
        streamer=Streamer(), callback_gate=CallbackAdmissionGate(), dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(),
        recorder_accounting=SimpleNamespace(snapshot=lambda: {
            "input_count": 1, "known_drops": 0, "unknown_telemetry_count": 0,
            "input_error_count": 0, "last_error_type": None, "accounting_known": True,
        }),
        advisor=Advisor(), report_path=tmp_path / "healthy.json", date_str="2026-11-19",
        date_compact="20261119", stitch_callable=lambda *args: {"status": "COMPLETED"},
        health_reporting_failures=0,
    )
    assert report["trace_capture_status"] == "HEALTHY"
    assert report["run_capture_status"] == "HEALTHY"
    assert report["exit_code"] == 0
    assert report["final_report_update_status"] == "WRITTEN"


def test_unknown_trace_run_id_cannot_produce_healthy_capture(tmp_path):
    class Streamer:
        def disconnect(self):
            return None

    class Recorder:
        _worker_thread = SimpleNamespace(is_alive=lambda: False)
        _queue = SimpleNamespace(qsize=lambda: 0)
        def flush_and_stop(self, timeout):
            return None

    class Advisor:
        trace_run_id = "UNKNOWN"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            return _valid_trace_snapshot("UNKNOWN")

    report = finalize_capture_session(
        streamer=Streamer(), callback_gate=CallbackAdmissionGate(), dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(),
        advisor=Advisor(), report_path=tmp_path / "unknown-run.json", date_str="2026-11-19",
        date_compact="20261119", stitch_callable=lambda *args: {"status": "COMPLETED"},
    )
    assert report["trace_health"]["status"] == "ERROR"
    assert report["trace_capture_status"] == "UNKNOWN"
    assert report["run_capture_status"] == "DEGRADED"
    assert report["exit_code"] == 1


def test_setup_failure_runs_partial_cleanup_without_claiming_uncreated_resources(
    tmp_path, monkeypatch
):
    from scripts import upstox_daily_live_capture_and_stitch as capture
    events = []

    class PartiallyInitializedRecorder:
        _worker_thread = None
        _queue = None
        def flush_and_stop(self, timeout):
            events.append("recorder-flush")

    report_path = tmp_path / "partial-setup.json"

    def fail_during_setup(resources):
        resources.report_path = report_path
        resources.date_str = "2026-11-19"
        resources.date_compact = "20261119"
        resources.data_dir = tmp_path
        resources.recorder = PartiallyInitializedRecorder()
        resources.started = True
        raise RuntimeError("simulated setup exception")

    monkeypatch.setattr(capture, "_run_capture_pipeline", fail_during_setup)
    with pytest.raises(RuntimeError, match="simulated setup exception"):
        capture.main()

    saved = json.loads(report_path.read_text())
    assert events == ["recorder-flush"]
    assert saved["capture_loop_error_type"] == "RuntimeError"
    assert saved["recorder_status"] == "UNKNOWN"
    assert saved["advisor_drain_status"] == "NOT_CREATED"
    assert saved["trace_capture_status"] == "UNKNOWN"
    assert saved["stitch_status"] == "SKIPPED_RECORDER_NOT_POSITIVELY_STOPPED"
    assert saved["exit_code"] == 1


def test_recorder_flush_exception_skips_stitch_but_advisor_drain_runs(tmp_path):
    events = []

    class Streamer:
        def disconnect(self):
            return None

    class Recorder:
        _worker_thread = SimpleNamespace(is_alive=lambda: False)
        _queue = SimpleNamespace(qsize=lambda: 0)
        def flush_and_stop(self, timeout):
            events.append("recorder")
            raise OSError("recorder flush failed")

    class Advisor:
        trace_run_id = "recorder-failure-run"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            events.append("advisor")
            return _valid_trace_snapshot(self.trace_run_id)

    report = finalize_capture_session(
        streamer=Streamer(), callback_gate=CallbackAdmissionGate(), dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(),
        advisor=Advisor(), report_path=tmp_path / "recorder-failure.json",
        date_str="2026-11-19", date_compact="20261119",
        stitch_callable=lambda *args: pytest.fail("uncertain recorder state must skip stitching"),
    )
    assert events == ["recorder", "advisor"]
    assert report["recorder_status"] == "ERROR"
    assert report["advisor_drain_status"] == "STOPPED"
    assert report["stitch_status"] == "SKIPPED_RECORDER_NOT_POSITIVELY_STOPPED"
    assert report["exit_code"] == 1


def test_capture_health_report_write_is_atomic_and_stitch_status_independent(tmp_path):
    path = tmp_path / "run-health.json"
    payload = {"trace_capture_status": "DEGRADED", "stitch_status": "PENDING", "trace_run_id": "run"}
    write_capture_health_report(path, payload)
    assert json.loads(path.read_text()) == payload
    payload["stitch_status"] = "COMPLETED"
    write_capture_health_report(path, payload)
    saved = json.loads(path.read_text())
    assert saved["trace_capture_status"] == "DEGRADED"
    assert saved["stitch_status"] == "COMPLETED"
    assert list(tmp_path.glob("*.tmp")) == []


def test_capture_finalization_does_not_claim_unknown_recorder_worker_is_stopped(tmp_path):
    class Streamer:
        @staticmethod
        def disconnect():
            return None

    class Recorder:
        @staticmethod
        def flush_and_stop(timeout):
            return None

    class Advisor:
        trace_run_id = "unknown-recorder-run"

        @staticmethod
        def shutdown_mode5_trace_writer(timeout_sec):
            return {
                "capacity": 10, "max_record_bytes": 16384, "queue_depth": 0,
                "pending_unpersisted": 0, "enqueued": 0, "append_successes": 0,
                "append_failures": 0, "queue_full_drops": 0, "oversize_drops": 0,
                "writer_unavailable_drops": 0, "active_writes": 0,
                "last_persisted_sequence": None, "last_processed_sequence": None,
                "writer_status": "STOPPED", "degraded": False, "last_error": None,
            }

    report = finalize_capture_session(
        streamer=Streamer(), callback_gate=CallbackAdmissionGate(), dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(),
        advisor=Advisor(), report_path=tmp_path / "unknown-recorder.json",
        date_str="2026-11-19", date_compact="20261119",
        stitch_callable=lambda *args: {"status": "NO_CHUNKS"},
    )
    assert report["recorder_status"] == "UNKNOWN"
    assert report["recorder_worker_alive"] is None
    assert report["run_capture_status"] == "DEGRADED"


def test_disconnect_timeout_alone_prevents_stitch_with_clean_recorder(tmp_path):
    release_disconnect = threading.Event()
    stitched = []

    class Streamer:
        def disconnect(self):
            release_disconnect.wait(timeout=1)

    class Recorder:
        total_records_written = 1
        _worker_thread = SimpleNamespace(is_alive=lambda: False)
        _queue = SimpleNamespace(qsize=lambda: 0)
        def flush_and_stop(self, timeout):
            return None

    class Advisor:
        trace_run_id = "disconnect-only-run"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            return _valid_trace_snapshot(self.trace_run_id)

    accounting = SimpleNamespace(snapshot=lambda: {
        "input_count": 1, "known_drops": 0, "unknown_telemetry_count": 0,
        "input_error_count": 0, "last_error_type": None, "accounting_known": True,
    })
    try:
        report = finalize_capture_session(
            streamer=Streamer(), callback_gate=CallbackAdmissionGate(),
            dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(),
            recorder_accounting=accounting, advisor=Advisor(),
            report_path=tmp_path / "disconnect-only.json", date_str="2026-11-19",
            date_compact="20261119", disconnect_timeout_sec=0.01,
            stitch_callable=lambda *args: (stitched.append(True) or {"status": "COMPLETED"}),
        )
        assert report["disconnect_status"] == "TIMED_OUT"
        assert report["recorder_status"] == "STOPPED"
        assert report["recorder_data_status"] == "ACCOUNTED"
        assert report["stitch_status"] == "SKIPPED_DISCONNECT_UNCONFIRMED"
        assert report["run_capture_status"] == "DEGRADED"
        assert report["exit_code"] == 1
        assert stitched == []
    finally:
        release_disconnect.set()


def test_dispatch_fence_rejects_callback_paused_before_lease():
    fence = DispatchAdmissionFence()
    resume = threading.Event()
    started = threading.Event()
    calls = []
    result = []

    def callback():
        started.set()
        assert resume.wait(timeout=1)
        result.append(_dispatch_with_lease(fence, lambda: calls.append("depth")))

    worker = threading.Thread(target=callback)
    worker.start()
    assert started.wait(timeout=1)
    fence.close()
    resume.set()
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert result == [False]
    assert calls == []
    assert fence.snapshot()["denied_dispatch_count"] == 1


def test_active_dispatch_lease_times_out_and_skips_all_dependent_shutdown(tmp_path):
    fence = DispatchAdmissionFence()
    lease = fence.acquire()
    calls = []

    class Streamer:
        def disconnect(self):
            calls.append("disconnect")

    class Recorder:
        def flush_and_stop(self, timeout):
            calls.append("recorder")

    class Advisor:
        trace_run_id = "active-lease-run"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            calls.append("advisor")

    try:
        report = finalize_capture_session(
            streamer=Streamer(), callback_gate=CallbackAdmissionGate(),
            dispatch_fence=fence, recorder=Recorder(), advisor=Advisor(),
            report_path=tmp_path / "active-lease.json", date_str="2026-11-19",
            date_compact="20261119", callback_timeout_sec=0.01,
            stitch_callable=lambda *args: calls.append("stitch"),
        )
        assert calls == ["disconnect"]
        assert report["dispatch_quiescence_status"] == "DISPATCH_QUIESCENCE_TIMEOUT"
        assert report["active_dispatch_count"] == 1
        assert report["order_action_may_be_in_flight"] is True
        assert report["recorder_status"] == "SKIPPED_DISPATCH_QUIESCENCE_TIMEOUT"
        assert report["advisor_drain_status"] == "SKIPPED_DISPATCH_QUIESCENCE_TIMEOUT"
        assert report["stitch_status"] == "SKIPPED_DISPATCH_QUIESCENCE_TIMEOUT"
    finally:
        lease.__exit__(None, None, None)


def test_denied_dispatch_fence_skips_stitch_even_with_other_shutdown_proofs(tmp_path):
    fence = DispatchAdmissionFence()
    fence.close()
    assert _dispatch_with_lease(fence, lambda: pytest.fail("denied dispatch ran")) is False

    class Streamer:
        def disconnect(self):
            return None

    class Recorder:
        total_records_written = 0
        _worker_thread = SimpleNamespace(is_alive=lambda: False)
        _queue = SimpleNamespace(qsize=lambda: 0)
        def flush_and_stop(self, timeout):
            return None

    class Advisor:
        trace_run_id = "denied-dispatch-run"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            snapshot = _valid_trace_snapshot(self.trace_run_id)
            snapshot.update(enqueued=0, append_successes=0,
                            last_persisted_sequence=0, last_processed_sequence=0)
            return snapshot

    accounting = SimpleNamespace(snapshot=lambda: {
        "input_count": 0, "known_drops": 0, "unknown_telemetry_count": 0,
        "input_error_count": 0, "last_error_type": None, "accounting_known": True,
    })
    stitched = []
    report = finalize_capture_session(
        streamer=Streamer(), callback_gate=CallbackAdmissionGate(), dispatch_fence=fence,
        recorder=Recorder(), recorder_accounting=accounting, advisor=Advisor(),
        report_path=tmp_path / "denied-dispatch.json", date_str="2026-11-19",
        date_compact="20261119",
        stitch_callable=lambda *args: (stitched.append(True) or {"status": "COMPLETED"}),
    )
    assert report["denied_dispatch_count"] == 1
    assert report["stitch_status"] == "SKIPPED_DISPATCH_FENCE_REJECTIONS"
    assert report["run_capture_status"] == "DEGRADED"
    assert stitched == []


@pytest.mark.parametrize("path", ["depth", "tick"])
def test_depth_and_tick_dispatch_use_fence_and_tick_state_update_is_leased(path):
    fence = DispatchAdmissionFence()
    calls = []
    prices = {"NIFTY": 100.0}
    update = (lambda: prices.update(NIFTY=101.0)) if path == "tick" else None
    assert _dispatch_with_lease(fence, lambda: calls.append(path), update) is True
    assert calls == [path]
    fence.close()
    assert _dispatch_with_lease(
        fence, lambda: calls.append(path), lambda: prices.update(NIFTY=102.0)
    ) is False
    assert calls == [path]
    assert prices["NIFTY"] == (101.0 if path == "tick" else 100.0)


def test_recorder_accounting_sink_tracks_write_and_known_drop_telemetry():
    class Recorder:
        total_records_written = 0
        def add_telemetry_callback(self, callback):
            self.telemetry = callback
        def on_depth(self, record):
            self.total_records_written += 1

    recorder = Recorder()
    sink = RecorderAccountingSink(recorder)
    sink.on_depth(object())
    assert sink.snapshot() == {
        "input_count": 1, "known_drops": 0, "unknown_telemetry_count": 0,
        "input_error_count": 0, "last_error_type": None, "accounting_known": True,
    }
    assert sink.snapshot()["input_count"] == recorder.total_records_written

    class DroppedRecorder(Recorder):
        def on_depth(self, record):
            self.telemetry({"event": "PERSISTENCE_QUEUE_DROPPED_BURST"})

    dropped = DroppedRecorder()
    dropped_sink = RecorderAccountingSink(dropped)
    dropped_sink.on_depth(object())
    assert dropped_sink.snapshot()["known_drops"] == 1
    assert dropped_sink.snapshot()["accounting_known"] is True


def test_recorder_accounting_sink_counts_exhausted_unknown_and_input_exception():
    class Recorder:
        def add_telemetry_callback(self, callback):
            self.telemetry = callback
        def on_depth(self, record):
            self.telemetry({"event": "PERSISTENCE_QUEUE_EXHAUSTED"})
            raise RuntimeError("saturated")

    exhausted = Recorder()
    exhausted_sink = RecorderAccountingSink(exhausted)
    exhausted_sink.on_depth(object())
    exhausted_snapshot = exhausted_sink.snapshot()
    assert exhausted_snapshot["known_drops"] == 1
    assert exhausted_snapshot["input_error_count"] == 1
    assert exhausted_snapshot["accounting_known"] is True

    exhausted.telemetry({"event": "UNRECOGNIZED_EVENT"})
    exhausted.telemetry({"unexpected": "shape"})
    assert exhausted_sink.snapshot()["unknown_telemetry_count"] == 2
    assert exhausted_sink.snapshot()["accounting_known"] is False

    class SilentFailure:
        def add_telemetry_callback(self, callback):
            self.telemetry = callback
        def on_depth(self, record):
            raise OSError("writer failed without disposition telemetry")

    failed_sink = RecorderAccountingSink(SilentFailure())
    failed_sink.on_depth(object())
    failed_snapshot = failed_sink.snapshot()
    assert failed_snapshot["input_count"] == 1
    assert failed_snapshot["input_error_count"] == 1
    assert failed_snapshot["unknown_telemetry_count"] == 1
    assert failed_snapshot["accounting_known"] is False


def test_finalizer_reports_chunk_read_failure_as_degraded_and_nonzero(tmp_path):
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    expected_chunk = chunks_dir / "recorder-listed.parquet"
    expected_chunk.write_bytes(b"broken parquet")
    date_compact = "20261119"
    master = tmp_path / f"upstox_full_ticks_{date_compact}_stitched.parquet"
    summary = tmp_path / f"stitching_summary_{date_compact}.json"
    master.write_bytes(b"prior-master")
    summary.write_text("prior-summary")

    class Streamer:
        def disconnect(self):
            return None

    class Recorder:
        written_files = [expected_chunk]
        total_records_written = 1
        _worker_thread = SimpleNamespace(is_alive=lambda: False)
        _queue = SimpleNamespace(qsize=lambda: 0)
        def flush_and_stop(self, timeout):
            return None

    class Advisor:
        trace_run_id = "manifest-finalizer-run"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            return _valid_trace_snapshot(self.trace_run_id)

    accounting = SimpleNamespace(snapshot=lambda: {
        "input_count": 1, "known_drops": 0, "unknown_telemetry_count": 0,
        "input_error_count": 0, "last_error_type": None, "accounting_known": True,
    })
    report = finalize_capture_session(
        streamer=Streamer(), callback_gate=CallbackAdmissionGate(),
        dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(),
        recorder_accounting=accounting, advisor=Advisor(),
        report_path=tmp_path / "capture-health.json", date_str="2026-11-19",
        date_compact=date_compact,
    )
    assert report["stitch_status"] == "FAILED_CHUNK_READ"
    assert report["run_capture_status"] == "DEGRADED"
    assert report["exit_code"] == 1
    assert master.read_bytes() == b"prior-master"
    assert summary.read_text() == "prior-summary"


def test_finalizer_passes_ordered_post_flush_frozen_manifest_without_globbing(tmp_path, monkeypatch):
    from scripts import upstox_daily_live_capture_and_stitch as capture

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    first = chunks_dir / "first.parquet"
    second = chunks_dir / "second.parquet"
    orphan = chunks_dir / "orphan.parquet"
    for path in (first, second, orphan):
        pq.write_table(pa.table({"value": [1]}), path)
    captured = {}
    recorder_state = {"stopped": False}

    def frozen_manifest_stitch(
        date_str, date_compact, data_dir, *, chunk_manifest,
        capture_run_id, recorder_accounting, excluded_prior_chunk_count,
    ):
        assert recorder_state["stopped"] is True
        captured["manifest"] = chunk_manifest
        captured["args"] = (date_str, date_compact, data_dir)
        captured["run_id"] = capture_run_id
        captured["accounting"] = recorder_accounting
        captured["excluded_prior_chunk_count"] = excluded_prior_chunk_count
        return {"status": "COMPLETED", "total_chunks": len(chunk_manifest)}

    monkeypatch.setattr(capture, "execute_post_market_stitching", frozen_manifest_stitch)

    class Streamer:
        def disconnect(self):
            return None

    class Recorder:
        _worker_thread = SimpleNamespace(is_alive=lambda: False)
        _queue = SimpleNamespace(qsize=lambda: 0)
        total_records_written = 2

        def __init__(self):
            self._written_files = [first]

        @property
        def written_files(self):
            return self._written_files

        def flush_and_stop(self, timeout):
            self._written_files = [second, first]
            recorder_state["stopped"] = True

    class Advisor:
        trace_run_id = "frozen-manifest-run"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            return _valid_trace_snapshot(self.trace_run_id)

    accounting = SimpleNamespace(snapshot=lambda: {
        "input_count": 2, "known_drops": 0, "unknown_telemetry_count": 0,
        "input_error_count": 0, "last_error_type": None, "accounting_known": True,
    })
    report = finalize_capture_session(
        streamer=Streamer(), callback_gate=CallbackAdmissionGate(),
        dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(),
        recorder_accounting=accounting, advisor=Advisor(),
        report_path=tmp_path / "frozen-manifest-health.json", date_str="2026-11-19",
        date_compact="20261119", stitch_callable=frozen_manifest_stitch,
    )
    assert captured["manifest"] == (second, first)
    assert captured["manifest"] == tuple(captured["manifest"])
    assert orphan not in captured["manifest"]
    assert captured["args"] == ("2026-11-19", "20261119", tmp_path)
    assert captured["run_id"] == "frozen-manifest-run"
    assert captured["accounting"]["accounting_known"] is True
    assert report["stitch_status"] == "COMPLETED"
    assert report["run_capture_status"] == "HEALTHY"


def test_existing_chunk_scan_sorts_numerically_and_returns_last_allocated_index(tmp_path):
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    paths = [chunks / "level5_chunk_00012.parquet", chunks / "level5_chunk_00002.parquet"]
    for path in paths:
        path.write_bytes(b"existing chunk")
    (chunks / "other.parquet").write_bytes(b"unrelated")
    nested = chunks / "nested"
    nested.mkdir()
    (nested / "level5_chunk_00099.parquet").write_bytes(b"nested is not top-level")

    ordered, last_index = scan_existing_level5_chunks(chunks)
    assert ordered == (paths[1], paths[0])
    assert last_index == 12


@pytest.mark.parametrize(
    "names",
    [
        ("level5_chunk_bad.parquet",),
        ("level5_chunk_1.parquet", "level5_chunk_00001.parquet"),
        ("level5_chunk_0.parquet", "level5_chunk_000000.parquet"),
    ],
)
def test_existing_chunk_scan_rejects_malformed_or_duplicate_numeric_indices(tmp_path, names):
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    for index, name in enumerate(names):
        (chunks / name).write_bytes(f"entry-{index}".encode())
    with pytest.raises(ValueError):
        scan_existing_level5_chunks(chunks)


def test_existing_chunk_scan_rejects_symlink_and_nonregular_prefix_entries(tmp_path):
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    target = chunks / "target.parquet"
    target.write_bytes(b"target")
    (chunks / "level5_chunk_00001.parquet").symlink_to(target)
    with pytest.raises(ValueError):
        scan_existing_level5_chunks(chunks)
    (chunks / "level5_chunk_00001.parquet").unlink()
    (chunks / "level5_chunk_00002.parquet").mkdir()
    with pytest.raises(ValueError):
        scan_existing_level5_chunks(chunks)


def test_transactional_stitch_commits_hash_verified_same_run_pair_and_source_manifest(
    tmp_path, monkeypatch
):
    from scripts import upstox_daily_live_capture_and_stitch as capture

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    listed = chunks_dir / "level5_chunk_00005.parquet"
    orphan = chunks_dir / "level5_chunk_00006.parquet"
    _manifest_source_chunk(listed, (1, 2))
    _manifest_source_chunk(orphan, (99,))
    monkeypatch.setattr(capture.urllib.request, "urlopen", lambda *a, **k: _empty_historical_response())

    result = capture.execute_post_market_stitching(
        "2026-11-19", "20261119", tmp_path,
        chunk_manifest=(listed,), capture_run_id="transaction-test-run",
        recorder_accounting=_clean_recorder_accounting(2),
        excluded_prior_chunk_count=3,
    )
    assert result["status"] == "COMPLETED"
    pointer = json.loads((tmp_path / "latest_stitch_manifest.json").read_text())
    source_path = tmp_path / pointer["source_manifest"]["path"]
    master_path = tmp_path / pointer["master"]["path"]
    summary_path = tmp_path / pointer["summary"]["path"]
    source = json.loads(source_path.read_text())
    summary = json.loads(summary_path.read_text())

    assert pointer["capture_run_id"] == "transaction-test-run"
    assert source["coverage_scope"] == "CURRENT_RUN_ONLY"
    assert source["claims_whole_session_complete"] is False
    assert source["excluded_prior_chunk_count"] == 3
    assert len(source["chunks"]) == 1
    assert source["chunks"][0]["relative_path"] == "chunks/level5_chunk_00005.parquet"
    assert source["chunks"][0]["sha256"] == hashlib.sha256(listed.read_bytes()).hexdigest()
    assert summary["capture_run_id"] == pointer["capture_run_id"]
    assert summary["source_manifest_sha256"] == pointer["source_manifest"]["sha256"]
    assert pq.read_table(master_path).num_rows == 2
    assert pointer["master"]["sha256"] == hashlib.sha256(master_path.read_bytes()).hexdigest()
    assert pointer["summary"]["sha256"] == hashlib.sha256(summary_path.read_bytes()).hexdigest()
    assert orphan not in [tmp_path / item["relative_path"] for item in source["chunks"]]

    alias_master = tmp_path / "upstox_full_ticks_20261119_stitched.parquet"
    alias_summary = tmp_path / "stitching_summary_20261119.json"
    assert hashlib.sha256(alias_master.read_bytes()).hexdigest() == pointer["master"]["sha256"]
    assert hashlib.sha256(alias_summary.read_bytes()).hexdigest() == pointer["summary"]["sha256"]


@pytest.mark.parametrize("failure_stage", ["master", "summary", "pointer"])
def test_stitch_precommit_failures_preserve_old_pointer_and_canonical_aliases(
    tmp_path, monkeypatch, failure_stage
):
    from scripts import upstox_daily_live_capture_and_stitch as capture

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    source_chunk = chunks_dir / "level5_chunk_00001.parquet"
    _manifest_source_chunk(source_chunk, (1,))
    pointer_path = tmp_path / "latest_stitch_manifest.json"
    master_alias = tmp_path / "upstox_full_ticks_20261119_stitched.parquet"
    summary_alias = tmp_path / "stitching_summary_20261119.json"
    pointer_path.write_text("prior-pointer")
    master_alias.write_bytes(b"prior-master")
    summary_alias.write_bytes(b"prior-summary")
    original_staged_write = capture._write_staged_parquet
    original_atomic_json = capture._atomic_json

    if failure_stage == "master":
        monkeypatch.setattr(
            capture, "_write_staged_parquet",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("master stage failure")),
        )
    elif failure_stage == "summary":
        def fail_summary(path, payload, *, replace):
            if Path(path).name.startswith("stitching_summary_"):
                raise OSError("summary stage failure")
            return original_atomic_json(path, payload, replace=replace)
        monkeypatch.setattr(capture, "_atomic_json", fail_summary)
    else:
        def fail_pointer(path, payload, *, replace):
            if Path(path).name == "latest_stitch_manifest.json":
                raise OSError("pointer commit failure")
            return original_atomic_json(path, payload, replace=replace)
        monkeypatch.setattr(capture, "_atomic_json", fail_pointer)
    monkeypatch.setattr(capture.urllib.request, "urlopen", lambda *a, **k: _empty_historical_response())

    result = capture.execute_post_market_stitching(
        "2026-11-19", "20261119", tmp_path,
        chunk_manifest=(source_chunk,), capture_run_id=f"fail-{failure_stage}-run",
        recorder_accounting=_clean_recorder_accounting(1),
    )
    assert result["status"] == "FAILED_STITCH_PUBLICATION"
    assert pointer_path.read_text() == "prior-pointer"
    assert master_alias.read_bytes() == b"prior-master"
    assert summary_alias.read_bytes() == b"prior-summary"
    assert original_staged_write is not None


def test_alias_failure_keeps_committed_pointer_and_reports_noncompleted_status(tmp_path, monkeypatch):
    from scripts import upstox_daily_live_capture_and_stitch as capture

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    source_chunk = chunks_dir / "level5_chunk_00001.parquet"
    _manifest_source_chunk(source_chunk, (1,))
    alias_master = tmp_path / "upstox_full_ticks_20261119_stitched.parquet"
    alias_master.write_bytes(b"prior-master")
    original_replace = capture.os.replace

    def fail_master_alias(source, destination):
        if Path(destination) == alias_master:
            raise OSError("alias update failure")
        return original_replace(source, destination)

    monkeypatch.setattr(capture.os, "replace", fail_master_alias)
    monkeypatch.setattr(capture.urllib.request, "urlopen", lambda *a, **k: _empty_historical_response())
    result = capture.execute_post_market_stitching(
        "2026-11-19", "20261119", tmp_path,
        chunk_manifest=(source_chunk,), capture_run_id="alias-failure-run",
        recorder_accounting=_clean_recorder_accounting(1),
    )
    assert result["status"] == "ALIAS_UPDATE_FAILED"
    pointer = json.loads((tmp_path / "latest_stitch_manifest.json").read_text())
    assert pointer["capture_run_id"] == "alias-failure-run"
    assert (tmp_path / pointer["master"]["path"]).is_file()
    assert alias_master.read_bytes() == b"prior-master"


def test_pointer_parent_fsync_failure_reports_visible_durability_unknown_and_skips_aliases(
    tmp_path, monkeypatch
):
    from scripts import upstox_daily_live_capture_and_stitch as capture

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    chunk = chunks_dir / "level5_chunk_00001.parquet"
    _manifest_source_chunk(chunk, (1,))
    pointer_path = tmp_path / "latest_stitch_manifest.json"
    master_alias = tmp_path / "upstox_full_ticks_20261119_stitched.parquet"
    summary_alias = tmp_path / "stitching_summary_20261119.json"
    pointer_path.write_text("old-pointer")
    master_alias.write_bytes(b"old-master")
    summary_alias.write_bytes(b"old-summary")
    pointer_replaced = {"value": False, "fsync_failure_injected": False}
    original_replace = capture.os.replace
    original_fsync = capture._fsync_directory

    def mark_pointer_replace(source, destination):
        result = original_replace(source, destination)
        if Path(destination) == pointer_path:
            pointer_replaced["value"] = True
        return result

    def fail_post_pointer_fsync(path):
        if pointer_replaced["value"] and not pointer_replaced["fsync_failure_injected"] and Path(path) == tmp_path:
            pointer_replaced["fsync_failure_injected"] = True
            raise OSError("post-pointer directory fsync failed")
        return original_fsync(path)

    monkeypatch.setattr(capture.os, "replace", mark_pointer_replace)
    monkeypatch.setattr(capture, "_fsync_directory", fail_post_pointer_fsync)
    monkeypatch.setattr(capture.urllib.request, "urlopen", lambda *a, **k: _empty_historical_response())

    class Streamer:
        def disconnect(self):
            return None

    class Recorder:
        written_files = [chunk]
        total_records_written = 1
        _worker_thread = SimpleNamespace(is_alive=lambda: False)
        _queue = SimpleNamespace(qsize=lambda: 0)
        def flush_and_stop(self, timeout):
            return None

    class Advisor:
        trace_run_id = "post-pointer-fsync-run"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            return _valid_trace_snapshot(self.trace_run_id)

    report = finalize_capture_session(
        streamer=Streamer(), callback_gate=CallbackAdmissionGate(),
        dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(),
        recorder_accounting=SimpleNamespace(snapshot=lambda: _clean_recorder_accounting(1)),
        advisor=Advisor(), report_path=tmp_path / "capture-health.json",
        date_str="2026-11-19", date_compact="20261119",
    )

    assert pointer_replaced["fsync_failure_injected"] is True
    assert report["stitch_status"] == "COMMIT_DURABILITY_UNKNOWN"
    assert report["stitch_result"]["pointer_visibility"] == "VISIBLE_DURABILITY_UNCONFIRMED"
    assert report["stitch_result"]["capture_run_id"] == "post-pointer-fsync-run"
    assert report["run_capture_status"] == "DEGRADED"
    assert report["exit_code"] == 1
    committed_pointer = json.loads(pointer_path.read_text())
    assert committed_pointer["capture_run_id"] == "post-pointer-fsync-run"
    assert pq.read_table(tmp_path / committed_pointer["master"]["path"]).num_rows == 1
    assert json.loads((tmp_path / committed_pointer["summary"]["path"]).read_text())["capture_run_id"] == "post-pointer-fsync-run"
    assert master_alias.read_bytes() == b"old-master"
    assert summary_alias.read_bytes() == b"old-summary"


def test_finalizer_maps_alias_update_failure_to_degraded_nonzero(tmp_path):
    class Streamer:
        def disconnect(self):
            return None

    class Recorder:
        total_records_written = 0
        _worker_thread = SimpleNamespace(is_alive=lambda: False)
        _queue = SimpleNamespace(qsize=lambda: 0)
        def flush_and_stop(self, timeout):
            return None

    class Advisor:
        trace_run_id = "alias-report-run"
        def shutdown_mode5_trace_writer(self, timeout_sec):
            snapshot = _valid_trace_snapshot(self.trace_run_id)
            snapshot.update(enqueued=0, append_successes=0,
                            last_persisted_sequence=0, last_processed_sequence=0)
            return snapshot

    report = finalize_capture_session(
        streamer=Streamer(), callback_gate=CallbackAdmissionGate(),
        dispatch_fence=DispatchAdmissionFence(), recorder=Recorder(),
        recorder_accounting=SimpleNamespace(snapshot=lambda: _clean_recorder_accounting(0)),
        advisor=Advisor(), report_path=tmp_path / "alias-report.json",
        date_str="2026-11-19", date_compact="20261119",
        stitch_callable=lambda *args: {"status": "ALIAS_UPDATE_FAILED"},
    )
    assert report["stitch_status"] == "ALIAS_UPDATE_FAILED"
    assert report["run_capture_status"] == "DEGRADED"
    assert report["exit_code"] == 1


@pytest.mark.parametrize("failure_mode", ["manifest_write", "hash_mismatch"])
def test_source_manifest_failure_prevents_pointer_and_preserves_prior_outputs(
    tmp_path, monkeypatch, failure_mode
):
    from scripts import upstox_daily_live_capture_and_stitch as capture

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    source_chunk = chunks_dir / "level5_chunk_00001.parquet"
    _manifest_source_chunk(source_chunk, (1,))
    pointer = tmp_path / "latest_stitch_manifest.json"
    master = tmp_path / "upstox_full_ticks_20261119_stitched.parquet"
    summary = tmp_path / "stitching_summary_20261119.json"
    pointer.write_text("prior-pointer")
    master.write_bytes(b"prior-master")
    summary.write_bytes(b"prior-summary")
    original_atomic_json = capture._atomic_json

    def inject_manifest_failure(path, payload, *, replace):
        if Path(path).name.startswith("capture_source_manifest_"):
            if failure_mode == "manifest_write":
                raise OSError("source manifest write failed")
            original_atomic_json(path, payload, replace=replace)
            source_chunk.write_bytes(b"mutated after manifest write")
            return
        return original_atomic_json(path, payload, replace=replace)

    monkeypatch.setattr(capture, "_atomic_json", inject_manifest_failure)
    result = capture.execute_post_market_stitching(
        "2026-11-19", "20261119", tmp_path,
        chunk_manifest=(source_chunk,), capture_run_id=f"source-fail-{failure_mode}",
        recorder_accounting=_clean_recorder_accounting(1),
    )
    assert result["status"] == "FAILED_SOURCE_MANIFEST"
    assert pointer.read_text() == "prior-pointer"
    assert master.read_bytes() == b"prior-master"
    assert summary.read_bytes() == b"prior-summary"


def test_unknown_run_id_is_rejected_before_manifest_or_output_commit(tmp_path):
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    chunk = chunks_dir / "level5_chunk_00001.parquet"
    _manifest_source_chunk(chunk, (1,))
    result = execute_post_market_stitching(
        "2026-11-19", "20261119", tmp_path,
        chunk_manifest=(chunk,), capture_run_id="UNKNOWN",
        recorder_accounting=_clean_recorder_accounting(1),
    )
    assert result["status"] == "INVALID_MANIFEST"
    assert not list(tmp_path.glob("capture_source_manifest_*.json"))
    assert not (tmp_path / "latest_stitch_manifest.json").exists()


@pytest.mark.parametrize(
    "override",
    [
        {"input_error_count": 1},
        {"unknown_telemetry_count": 1},
        {"accounting_known": 1},
        {"total_records_written": 0},
    ],
)
def test_stitch_rejects_incomplete_recorder_accounting_before_any_manifest_or_pointer(
    tmp_path, override
):
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    chunk = chunks_dir / "level5_chunk_00001.parquet"
    _manifest_source_chunk(chunk, (1,))
    accounting = _clean_recorder_accounting(1)
    accounting.update(override)

    result = execute_post_market_stitching(
        "2026-11-19", "20261119", tmp_path,
        chunk_manifest=(chunk,), capture_run_id="accounting-veto-run",
        recorder_accounting=accounting,
    )
    assert result["status"] == "INVALID_MANIFEST"
    assert not list(tmp_path.glob("capture_source_manifest_*.json"))
    assert not (tmp_path / "latest_stitch_manifest.json").exists()


def test_generation_parent_directories_are_fsynced_before_pointer_replace(tmp_path, monkeypatch):
    from scripts import upstox_daily_live_capture_and_stitch as capture

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    chunk = chunks_dir / "level5_chunk_00001.parquet"
    _manifest_source_chunk(chunk, (1,))
    events = []
    original_fsync_directory = capture._fsync_directory
    original_replace = capture.os.replace

    def record_fsync(path):
        path = Path(path)
        if path == tmp_path:
            events.append("fsync:data_dir")
        elif path == tmp_path / "stitch_generations":
            events.append("fsync:generation_root")
        return original_fsync_directory(path)

    def record_replace(source, destination):
        if Path(destination) == tmp_path / "latest_stitch_manifest.json":
            events.append("pointer:replace")
        return original_replace(source, destination)

    monkeypatch.setattr(capture, "_fsync_directory", record_fsync)
    monkeypatch.setattr(capture.os, "replace", record_replace)
    monkeypatch.setattr(capture.urllib.request, "urlopen", lambda *a, **k: _empty_historical_response())
    result = capture.execute_post_market_stitching(
        "2026-11-19", "20261119", tmp_path,
        chunk_manifest=(chunk,), capture_run_id="parent-fsync-order-run",
        recorder_accounting=_clean_recorder_accounting(1),
    )
    assert result["status"] == "COMPLETED"
    pointer_index = events.index("pointer:replace")
    assert events[:pointer_index].count("fsync:data_dir") >= 2
    assert events.index("fsync:generation_root") < pointer_index


@pytest.mark.parametrize("failure_parent", ["data_dir", "generation_root"])
def test_generation_parent_fsync_failure_preserves_previous_pointer_and_aliases(
    tmp_path, monkeypatch, failure_parent
):
    from scripts import upstox_daily_live_capture_and_stitch as capture

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    chunk = chunks_dir / "level5_chunk_00001.parquet"
    _manifest_source_chunk(chunk, (1,))
    pointer = tmp_path / "latest_stitch_manifest.json"
    master = tmp_path / "upstox_full_ticks_20261119_stitched.parquet"
    summary = tmp_path / "stitching_summary_20261119.json"
    pointer.write_text("prior-pointer")
    master.write_bytes(b"prior-master")
    summary.write_bytes(b"prior-summary")
    original_fsync_directory = capture._fsync_directory
    data_dir_calls = 0

    def fail_target_parent(path):
        nonlocal data_dir_calls
        path = Path(path)
        if path == tmp_path:
            data_dir_calls += 1
            if failure_parent == "data_dir" and data_dir_calls == 2:
                raise OSError("data directory fsync failure")
        if failure_parent == "generation_root" and path == tmp_path / "stitch_generations":
            raise OSError("generation root fsync failure")
        return original_fsync_directory(path)

    monkeypatch.setattr(capture, "_fsync_directory", fail_target_parent)
    result = capture.execute_post_market_stitching(
        "2026-11-19", "20261119", tmp_path,
        chunk_manifest=(chunk,), capture_run_id=f"parent-fsync-{failure_parent}",
        recorder_accounting=_clean_recorder_accounting(1),
    )
    assert result["status"] == "FAILED_STITCH_PUBLICATION"
    assert pointer.read_text() == "prior-pointer"
    assert master.read_bytes() == b"prior-master"
    assert summary.read_bytes() == b"prior-summary"
