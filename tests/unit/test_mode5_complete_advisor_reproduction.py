"""Read-only source-behavior reproduction through advisor.on_tick.

Each oracle run occurs in a child process whose cwd and every explicit runtime
path live under pytest's temporary directory. No broker, dispatcher or live
network path is enabled.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from dataclasses import replace
from datetime import date, datetime, time as dt_time
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from core.sentinel_live_stream_advisor import (
    CachedRBFNAuctionSignal,
    SentinelLiveStreamAdvisor,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


_CHILD = textwrap.dedent(r'''
    import builtins, fcntl, inspect, io, json, os, socket, sys, tempfile, urllib.request
    from datetime import date, datetime, time
    from pathlib import Path
    from zoneinfo import ZoneInfo

    root = Path.cwd().resolve()
    # Resolve every repository runtime/data root under the child-owned temp cwd
    # before importing configuration or advisor modules.
    os.environ["DATA_ROOT"] = str(root / "data")
    os.environ["DB_ROOT"] = str(root / "data" / "db")
    os.environ["TRADE_DB_PATH"] = str(root / "data" / "db" / "trades.sqlite")
    os.environ.pop("UPSTOX_ACCESS_TOKEN", None)
    network_attempts = []
    def deny_network(*args, **kwargs):
        network_attempts.append("blocked")
        raise RuntimeError("M5_NETWORK_SENTINEL")
    socket.create_connection = deny_network
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    urllib.request.urlopen = deny_network

    from core.sentinel_realtime_journal import SentinelRealtimeJournal
    from core.sentinel_live_stream_advisor import SentinelLiveStreamAdvisor
    from core.upstox_stream_broadcaster import UpstoxTickRecord
    import requests
    requests.sessions.Session.request = deny_network

    class ForbiddenHTTP:
        def get(self, *args, **kwargs):
            return deny_network(*args, **kwargs)

    # Deny path-based writes outside the temporary cwd after source imports.
    # Python-level open guards alone are insufficient: APM/WAL code can use
    # os.open, atomic replace/rename, directory creation, unlink, or tempfile.
    real_open = builtins.open
    real_io_open = io.open
    real_os_open = os.open
    real_os_replace = os.replace
    real_os_rename = os.rename
    real_os_unlink = os.unlink
    real_os_remove = os.remove
    real_os_mkdir = os.mkdir
    real_os_rmdir = os.rmdir
    real_os_close = os.close
    guard_blocks = []
    def under_root(file):
        if isinstance(file, int):
            return False
        candidate = Path(os.fsdecode(file))
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve(strict=False)
        return resolved == root or root in resolved.parents
    def resolve_dirfd_path(file, dir_fd):
        if dir_fd is None:
            return file
        candidate = Path(os.fsdecode(file))
        if candidate.is_absolute():
            return candidate
        try:
            if sys.platform == "darwin" and hasattr(fcntl, "F_GETPATH"):
                base_value = fcntl.fcntl(dir_fd, fcntl.F_GETPATH, b"\0" * 1024)
                base = Path(os.fsdecode(base_value).rstrip("\0"))
            elif sys.platform.startswith("linux"):
                base = Path(os.readlink(f"/proc/self/fd/{dir_fd}"))
            else:
                raise OSError(f"descriptor path resolution unsupported on {sys.platform}")
            base = base.resolve(strict=True)
            if not base.is_dir():
                raise OSError("dir_fd does not refer to a directory")
        except (OSError, RuntimeError, TypeError, ValueError):
            guard_blocks.append("unresolvable_dir_fd")
            raise RuntimeError("M5_WRITE_OUTSIDE_TEMP_SENTINEL")
        return base / candidate
    def check_write_path(file, *, dir_fd=None):
        resolved_file = resolve_dirfd_path(file, dir_fd)
        if not under_root(resolved_file):
            guard_blocks.append(os.fspath(file) if not isinstance(file, int) else "fd")
            raise RuntimeError("M5_WRITE_OUTSIDE_TEMP_SENTINEL")
    def guarded_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+"):
            check_write_path(file)
        return real_open(file, mode, *args, **kwargs)
    def guarded_io_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+"):
            check_write_path(file)
        return real_io_open(file, mode, *args, **kwargs)
    def guarded_os_open(file, flags, mode=0o777, *, dir_fd=None):
        writes = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        if writes:
            check_write_path(file, dir_fd=dir_fd)
        return real_os_open(file, flags, mode, dir_fd=dir_fd)
    def guarded_replace(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
        check_write_path(src, dir_fd=src_dir_fd)
        check_write_path(dst, dir_fd=dst_dir_fd)
        return real_os_replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
    def guarded_rename(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
        check_write_path(src, dir_fd=src_dir_fd)
        check_write_path(dst, dir_fd=dst_dir_fd)
        return real_os_rename(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
    def guarded_unlink(path, *, dir_fd=None):
        check_write_path(path, dir_fd=dir_fd)
        return real_os_unlink(path, dir_fd=dir_fd)
    def guarded_remove(path, *, dir_fd=None):
        check_write_path(path, dir_fd=dir_fd)
        return real_os_remove(path, dir_fd=dir_fd)
    def guarded_mkdir(path, mode=0o777, *, dir_fd=None):
        check_write_path(path, dir_fd=dir_fd)
        return real_os_mkdir(path, mode, dir_fd=dir_fd)
    def guarded_rmdir(path, *, dir_fd=None):
        check_write_path(path, dir_fd=dir_fd)
        return real_os_rmdir(path, dir_fd=dir_fd)

    real_temp_functions = {
        name: getattr(tempfile, name) for name in
        ("mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryFile",
         "SpooledTemporaryFile", "TemporaryDirectory", "mktemp")
    }
    def guarded_temp_function(function):
        def wrapped(*args, **kwargs):
            directory = inspect.signature(function).bind_partial(*args, **kwargs).arguments.get("dir")
            if directory is None:
                directory = tempfile.gettempdir()
            check_write_path(directory)
            return function(*args, **kwargs)
        return wrapped

    builtins.open = guarded_open
    io.open = guarded_io_open
    os.open = guarded_os_open
    os.replace = guarded_replace
    os.rename = guarded_rename
    os.unlink = guarded_unlink
    os.remove = guarded_remove
    os.mkdir = guarded_mkdir
    os.rmdir = guarded_rmdir
    for name, function in real_temp_functions.items():
        setattr(tempfile, name, guarded_temp_function(function))

    # Prove the lower-level guards actively reject each operation class before
    # constructing the advisor. These attempts are intercepted before effects.
    outside = root.parent / "M5_CONTAINMENT_SENTINEL"
    outside_dir_fd = real_os_open(root.parent, os.O_RDONLY)
    probes = (
        lambda: os.open(outside, os.O_WRONLY | os.O_CREAT, 0o600),
        lambda: os.replace(outside, root / "probe-target"),
        lambda: os.rename(outside, root / "probe-target"),
        lambda: os.unlink(outside),
        lambda: os.remove(outside),
        lambda: os.mkdir(outside),
        lambda: os.rmdir(outside),
        lambda: tempfile.mkstemp(dir=str(root.parent)),
        lambda: os.open("M5_CONTAINMENT_SENTINEL", os.O_WRONLY | os.O_CREAT,
                        0o600, dir_fd=outside_dir_fd),
        lambda: os.unlink("M5_CONTAINMENT_SENTINEL", dir_fd=outside_dir_fd),
    )
    for probe in probes:
        try:
            probe()
        except RuntimeError as exc:
            if str(exc) != "M5_WRITE_OUTSIDE_TEMP_SENTINEL":
                raise
        else:
            raise AssertionError("low-level write guard failed to intercept probe")
    assert len(guard_blocks) >= len(probes)
    guard_probe_blocks = len(guard_blocks)
    real_os_close(outside_dir_fd)

    # The probes above intentionally attempt blocked writes. Reset their
    # counters before constructing the advisor so this assertion measures
    # advisor-phase behavior only.
    guard_blocks.clear()

    ist = ZoneInfo("Asia/Kolkata")
    session_day = date(2026, 11, 23)
    def stamp(hh, mm, ss=0, ms=0):
        value = datetime.combine(session_day, time(hh, mm, ss, ms * 1000), tzinfo=ist)
        return int(value.timestamp() * 1000)
    def tick(token, timestamp_ms, sequence, ltp):
        return UpstoxTickRecord(
            token=token, symbol=token, exchange_timestamp_ms=timestamp_ms,
            ingress_monotonic_ns=sequence, ingress_wall_utc="2026-11-23T00:00:00Z",
            sequence_id=sequence, ltp=ltp, volume=1, open_interest=0,
            best_bid=0.0, best_ask=0.0,
        )

    runtime = root / "runtime"
    logs = root / "logs"
    runtime.mkdir(parents=True, exist_ok=True)
    journal = SentinelRealtimeJournal(logs_dir=logs, enable_writer_thread=False)
    # The replay's explicit clock must be at or after the replayed event; a
    # 09:15 clock would correctly reject the 09:23/09:25 event timestamps as
    # future-skewed input.
    fixed_clock = lambda: datetime.combine(session_day, time(9, 26), tzinfo=ist)
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(runtime / "sentinel_apm_wal.json"),
        or_reconciliation_state_path=str(runtime / "sentinel_or_ledger.json"),
        journal=journal, replay_mode=True, session_clock=fixed_clock,
        http_client=ForbiddenHTTP(), enable_stdout=False,
        enable_automated_dispatch=False, enable_nifty_live=False,
        broker_adapter=None,
    )
    processed_unverified_epochs = []
    original_unverified_recorder = advisor._record_unverified_synthetic_5m_bar_locked
    def record_unverified_spy(**kwargs):
        processed_unverified_epochs.append(kwargs["epoch_5min"])
        return original_unverified_recorder(**kwargs)
    advisor._record_unverified_synthetic_5m_bar_locked = record_unverified_spy
    event_offset_ms = int(os.environ["M5_EVENT_OFFSET_MS"])
    def strategy_state():
        current_signal = advisor.cached_rbfn_signals.get("NIFTY")
        current_meta = advisor._cached_rbfn_candidate_meta.get("NIFTY")
        return {
            "strategy_history_count": len(advisor.bars_5m_strategy_history["NIFTY"]),
            "raw_bar_history_count": len(advisor.bars_5m_history["NIFTY"]),
            "signal_action": getattr(current_signal, "action", None),
            "signal_setup_reason": getattr(current_signal, "setup_reason", None),
            "signal_veto_reason": getattr(current_signal, "veto_reason", None),
            "rejection_reason": advisor._mode5_last_eval_rejection.get("NIFTY"),
            "nifty_rp2_session": (
                advisor._rp2_session_dates["NIFTY"].isoformat()
                if advisor._rp2_session_dates["NIFTY"] else None
            ),
            "candidate_generation": getattr(current_meta, "generation", None),
            "candidate_status": getattr(current_meta, "status", None),
        }
    strategy_result = None
    try:
        for seq, (token, price) in enumerate((
            ("Nifty 50", 25900.0), ("SENSEX", 84000.0), ("Nifty Bank", 59000.0),
        ), start=1):
            advisor.on_tick(tick(token, stamp(9, 23), seq, price))
        advisor.on_tick(tick("Nifty 50", stamp(9, 25) + event_offset_ms, 10, 25905.0))
        after_first_rollover = strategy_state()
        # Duplicate and older records must not cause another close/history append.
        advisor.on_tick(tick("Nifty 50", stamp(9, 25) + event_offset_ms, 11, 25906.0))
        after_duplicate_tick = strategy_state()
        advisor.on_tick(tick("Nifty 50", stamp(9, 24, 59, 999) , 12, 25907.0))
        after_older_tick = strategy_state()
        advisor.on_tick(tick("Nifty 50", stamp(9, 23) + 31 * 86_400_000, 13, 25908.0))
        after_future_tick = strategy_state()
        strategy_result = {
            **after_first_rollover,
            "after_first_rollover": after_first_rollover,
            "after_duplicate_tick": after_duplicate_tick,
            "after_older_tick": after_older_tick,
            "after_future_tick": after_future_tick,
            "replay_mode": advisor.replay_mode,
            "dispatch_enabled": advisor.enable_automated_dispatch,
            "live_enabled": advisor.enable_nifty_live,
            "broker_adapter_present": advisor.automated_dispatcher is not None,
            "processed_unverified_epochs": list(processed_unverified_epochs),
        }
    finally:
        advisor.shutdown_or_reconciliation_worker()
        advisor._or_request_queue.join()
        advisor._or_worker_thread.join(timeout=3.0)
        advisor.shutdown_mode5_trace_writer(timeout_sec=3.0)
        for manager in advisor.apms.values():
            manager.close()
        journal.close()
    # Measure containment only after every producer and writer is stopped.
    # The strategy result above is intentionally captured before shutdown.
    result = dict(strategy_result)
    result.update({
        "network_attempts": len(network_attempts),
        "guard_probe_blocks": guard_probe_blocks,
        "advisor_outside_write_attempts": list(guard_blocks),
        "runtime_files": sorted(
            str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()
        ),
    })
    print(json.dumps(result, sort_keys=True))
''')


def _run_child(tmp_path: Path, offset_ms: int) -> dict:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(REPO_ROOT),
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmp"),
        "TZ": "UTC",
        "PYTHONDONTWRITEBYTECODE": "1",
        "M5_EVENT_OFFSET_MS": str(offset_ms),
    }
    (tmp_path / "home").mkdir()
    (tmp_path / "tmp").mkdir()
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert completed.returncode == 0, (
        f"advisor child failed ({completed.returncode})\n"
        f"stdout={completed.stdout}\nstderr={completed.stderr}"
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip().startswith("{")]
    assert lines, f"advisor child produced no JSON result: {completed.stdout!r}"
    result = json.loads(lines[-1])
    assert result["network_attempts"] == 0
    assert result["guard_probe_blocks"] >= 10
    assert result["advisor_outside_write_attempts"] == []
    assert result["replay_mode"] is True
    assert result["dispatch_enabled"] is False
    assert result["live_enabled"] is False
    assert result["broker_adapter_present"] is False
    assert all(not Path(path).is_absolute() for path in result["runtime_files"])
    return result


@pytest.mark.parametrize(
    ("offset_ms",),
    [
        (0,),
        (1,),
    ],
)
def test_on_tick_rollover_retains_but_never_promotes_unverified_synthetic_bar(tmp_path, offset_ms):
    result = _run_child(tmp_path, offset_ms)
    expected_rollover_state = {
        "strategy_history_count": 0,
        "raw_bar_history_count": 1,
        "signal_action": None,
        "signal_setup_reason": None,
        "signal_veto_reason": None,
        "rejection_reason": "MODE5_BAR_COMPLETENESS_UNKNOWN",
        "nifty_rp2_session": "2026-11-23",
        "candidate_generation": None,
        "candidate_status": None,
    }
    assert result["after_first_rollover"] == expected_rollover_state
    assert result["after_duplicate_tick"] == expected_rollover_state
    assert result["after_older_tick"] == expected_rollover_state
    assert result["after_future_tick"] == expected_rollover_state
    expected_unverified_epoch = (
        int(datetime.combine(date(2026, 11, 23), dt_time(9, 20), tzinfo=ZoneInfo("Asia/Kolkata")).timestamp()) // 300
    )
    assert expected_unverified_epoch in result["processed_unverified_epochs"]
    assert len(result["processed_unverified_epochs"]) == 1
    assert result["raw_bar_history_count"] == 1
    assert result["strategy_history_count"] == 0
    assert result["signal_veto_reason"] is None
    assert result["rejection_reason"] == "MODE5_BAR_COMPLETENESS_UNKNOWN"
    assert result["nifty_rp2_session"] == "2026-11-23"
    assert result["advisor_outside_write_attempts"] == []
    # Trace and runtime outputs are confined to the child temp cwd.
    assert result["runtime_files"]
    assert all(path.startswith(("runtime/", "logs/")) for path in result["runtime_files"])


def _advisor_with_mode5_candidate(
    tmp_path: Path, candidate_epoch: int, action: str = "BUY_CALL"
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"candidate-{candidate_epoch}.json"),
        or_reconciliation_state_path=str(tmp_path / f"candidate-{candidate_epoch}-or.json"),
        enable_stdout=False,
        enable_automated_dispatch=False,
        enable_nifty_live=False,
    )
    ist = ZoneInfo("Asia/Kolkata")
    candidate_boundary_ms = (candidate_epoch + 1) * 300_000
    signal = CachedRBFNAuctionSignal(
        timestamp_ms=candidate_boundary_ms - 1,
        index_name="NIFTY",
        action=action,
        direction="CE" if action == "BUY_CALL" else "PE",
        target_strike=26_000.0,
        target_pts=100.0,
        sl_pts=50.0,
        setup_reason="TEST_SYNTHETIC_EPOCH_RETENTION",
        trade_phase="CONTINUOUS_STATE_MACHINE",
        bar_time=datetime.fromtimestamp(candidate_boundary_ms / 1000.0, tz=ist).time(),
        allowed_for_live_execution=False,
    )
    with advisor._lock:
        advisor._rp2_session_dates["NIFTY"] = date(2026, 11, 23)
        advisor._cache_rbfn_signal_locked("NIFTY", signal, candidate_epoch)
    advisor.apms["NIFTY"].arm_and_enter = Mock()
    advisor.automated_dispatcher = SimpleNamespace(
        reserve_entry_intent=Mock(),
        on_apm_entry=Mock(),
    )
    return advisor, signal


def _record_synthetic_epoch(advisor, epoch_5min: int) -> None:
    ist = ZoneInfo("Asia/Kolkata")
    boundary_ms = (epoch_5min + 1) * 300_000
    with advisor._lock:
        advisor._record_unverified_synthetic_5m_bar_locked(
            index_name="NIFTY",
            bar_open=25_900.0,
            bar_high=25_920.0,
            bar_low=25_890.0,
            bar_close=25_905.0,
            bar_volume=10.0,
            bar_time=datetime.fromtimestamp(boundary_ms / 1000.0, tz=ist).time(),
            timestamp_ms=epoch_5min * 300_000 + 1_000,
            epoch_5min=epoch_5min,
        )


@pytest.mark.parametrize("candidate_epoch_delta", [-1, 0, 1], ids=["older-E-1", "same-E", "newer-E-plus-1"])
@pytest.mark.parametrize(
    ("candidate_action", "candidate_direction"),
    [("BUY_CALL", "CE"), ("BUY_PUT", "PE")],
    ids=["call-ce", "put-pe"],
)
def test_synthetic_epoch_only_clears_strictly_older_candidate_and_is_idempotent(
    tmp_path: Path,
    candidate_epoch_delta: int,
    candidate_action: str,
    candidate_direction: str,
):
    ist = ZoneInfo("Asia/Kolkata")
    session_day = date(2026, 11, 23)
    synthetic_epoch = int(
        datetime.combine(session_day, dt_time(10, 0), tzinfo=ist).timestamp() // 300
    )
    candidate_epoch = synthetic_epoch + candidate_epoch_delta
    advisor, signal = _advisor_with_mode5_candidate(
        tmp_path, candidate_epoch, action=candidate_action
    )
    assert signal.direction == candidate_direction
    try:
        initial_generation = advisor._cached_rbfn_candidate_meta["NIFTY"].generation
        _record_synthetic_epoch(advisor, synthetic_epoch)
        generation_after_first = advisor._cached_rbfn_generation["NIFTY"]
        _record_synthetic_epoch(advisor, synthetic_epoch)

        if candidate_epoch_delta < 0:
            assert advisor.cached_rbfn_signals["NIFTY"] is None
            assert advisor._cached_rbfn_candidate_meta["NIFTY"] is None
            assert generation_after_first == initial_generation + 1
            assert advisor._cached_rbfn_generation["NIFTY"] == generation_after_first
        else:
            assert advisor.cached_rbfn_signals["NIFTY"] is signal
            assert advisor._cached_rbfn_candidate_meta["NIFTY"].generation == initial_generation
            assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "AVAILABLE"
            assert advisor._cached_rbfn_generation["NIFTY"] == initial_generation

        assert signal.allowed_for_live_execution is False
        advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
        advisor.automated_dispatcher.on_apm_entry.assert_not_called()
        advisor.apms["NIFTY"].arm_and_enter.assert_not_called()
    finally:
        advisor.shutdown_or_reconciliation_worker()
        advisor.shutdown_mode5_trace_writer(timeout_sec=3)
        for manager in advisor.apms.values():
            manager.close()


@pytest.mark.parametrize(
    "metadata_state",
    [
        "missing_metadata",
        "missing_signal",
        "malformed_boundary",
        "unaligned_boundary",
        "generation_mismatch",
        "signal_epoch_mismatch",
        "index_mismatch",
        "status_mismatch",
        "inactive_signal",
        "vetoed_signal",
        "action_direction_mismatch",
        "session_mismatch",
    ],
)
def test_synthetic_epoch_clears_candidate_with_missing_or_malformed_metadata(
    tmp_path: Path, metadata_state: str
):
    ist = ZoneInfo("Asia/Kolkata")
    session_day = date(2026, 11, 23)
    synthetic_epoch = int(
        datetime.combine(session_day, dt_time(10, 0), tzinfo=ist).timestamp() // 300
    )
    advisor, _ = _advisor_with_mode5_candidate(tmp_path, synthetic_epoch + 1)
    try:
        signal = advisor.cached_rbfn_signals["NIFTY"]
        metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
        if metadata_state == "missing_metadata":
            advisor._cached_rbfn_candidate_meta["NIFTY"] = None
        elif metadata_state == "missing_signal":
            advisor.cached_rbfn_signals["NIFTY"] = None
        elif metadata_state == "malformed_boundary":
            advisor._cached_rbfn_candidate_meta["NIFTY"] = replace(
                metadata, boundary_timestamp_ms=True
            )
        elif metadata_state == "unaligned_boundary":
            advisor._cached_rbfn_candidate_meta["NIFTY"] = replace(
                metadata, boundary_timestamp_ms=metadata.boundary_timestamp_ms + 1
            )
        elif metadata_state == "generation_mismatch":
            advisor._cached_rbfn_candidate_meta["NIFTY"] = replace(
                metadata, generation=metadata.generation + 1
            )
        elif metadata_state == "signal_epoch_mismatch":
            advisor.cached_rbfn_signals["NIFTY"] = replace(
                signal, timestamp_ms=signal.timestamp_ms - 300_000
            )
        elif metadata_state == "index_mismatch":
            advisor.cached_rbfn_signals["NIFTY"] = replace(
                signal, index_name="SENSEX"
            )
        elif metadata_state == "status_mismatch":
            advisor._cached_rbfn_candidate_meta["NIFTY"] = replace(
                metadata, status="CONSUMED"
            )
        elif metadata_state == "inactive_signal":
            advisor.cached_rbfn_signals["NIFTY"] = replace(signal, is_active=False)
        elif metadata_state == "vetoed_signal":
            advisor.cached_rbfn_signals["NIFTY"] = replace(signal, is_vetoed=True)
        elif metadata_state == "action_direction_mismatch":
            advisor.cached_rbfn_signals["NIFTY"] = replace(signal, direction="PE")
        elif metadata_state == "session_mismatch":
            advisor._cached_rbfn_candidate_meta["NIFTY"] = replace(
                metadata, session_day=date(2026, 11, 22)
            )
        else:
            raise AssertionError(f"unknown malformed candidate state: {metadata_state}")
        _record_synthetic_epoch(advisor, synthetic_epoch)
        assert advisor.cached_rbfn_signals["NIFTY"] is None
        assert advisor._cached_rbfn_candidate_meta["NIFTY"] is None
        advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
        advisor.apms["NIFTY"].arm_and_enter.assert_not_called()
    finally:
        advisor.shutdown_or_reconciliation_worker()
        advisor.shutdown_mode5_trace_writer(timeout_sec=3)
        for manager in advisor.apms.values():
            manager.close()
