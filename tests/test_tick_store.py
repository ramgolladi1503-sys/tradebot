import time

import pytest

from core import tick_store


def _setup_isolated_tick_store(monkeypatch, tmp_path):
    db_path = tmp_path / "ticks.db"
    monkeypatch.setattr(tick_store.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(tick_store.cfg, "TICK_STORE_ASYNC_DB_WRITES", True, raising=False)
    monkeypatch.setattr(tick_store.cfg, "TICK_STORE_ASYNC_FLUSH_INTERVAL_SEC", 10.0, raising=False)
    tick_store.shutdown_persistence_worker(deadline_seconds=1.0)
    tick_store._LAST_TICK_BY_TOKEN.clear()
    tick_store.reset_audit_counters()
    return db_path


def test_get_last_tick_get_ltp_and_age_for_fresh_tick(monkeypatch, tmp_path):
    _setup_isolated_tick_store(monkeypatch, tmp_path)
    token = 123456
    price = 101.25

    ok = tick_store.insert_tick(time.time(), token, price, 10, 5)
    assert ok is True

    last_tick = tick_store.get_last_tick(token)
    assert isinstance(last_tick, dict)
    assert set(last_tick.keys()) == {"ltp", "ts_epoch", "source"}
    assert isinstance(last_tick["ltp"], float)
    assert isinstance(last_tick["ts_epoch"], float)
    assert last_tick["source"] in {"memory", "sqlite"}

    ltp, ts_epoch = tick_store.get_ltp(token)
    assert isinstance(ltp, float)
    assert isinstance(ts_epoch, float)

    age_sec = tick_store.get_age_sec(token)
    assert isinstance(age_sec, float)
    assert age_sec >= 0.0
    assert age_sec < 5.0


def test_async_insert_does_not_flush_sqlite_on_callback_thread(monkeypatch, tmp_path):
    _setup_isolated_tick_store(monkeypatch, tmp_path)
    called = []
    original_flush_pending_ticks = tick_store._flush_pending_ticks

    def _record_flush(*args, **kwargs):
        called.append((args, kwargs))
        return original_flush_pending_ticks(*args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(tick_store, "_flush_pending_ticks", _record_flush)
        assert tick_store.insert_tick(time.time(), 123456, 101.25, 10, 5) is True
        # Join the worker while the contract-preserving probe is still installed.
        # This prevents a background worker from outliving the monkeypatch scope.
        tick_store.shutdown_persistence_worker(deadline_seconds=1.0)
    # The async worker may drain immediately. What this safety contract forbids
    # is a callback/direct flush; any observed flush must therefore be explicitly
    # worker-owned rather than requiring a timing-dependent empty call list.
    assert all(kwargs.get("worker_owned") is True for _args, kwargs in called)


def test_get_last_tick_db_fallback_when_memory_missing(monkeypatch, tmp_path):
    _setup_isolated_tick_store(monkeypatch, tmp_path)
    token = 999001
    price = 222.5

    ok = tick_store.insert_tick(time.time(), token, price, 1, 1)
    assert ok is True
    tick_store._LAST_TICK_BY_TOKEN.pop(token, None)

    last_tick = tick_store.get_last_tick(token, allow_db=True)
    assert isinstance(last_tick, dict)
    assert last_tick["source"] == "sqlite"
    assert isinstance(last_tick["ltp"], float)
    assert isinstance(last_tick["ts_epoch"], float)


def test_unknown_token_returns_none_values(monkeypatch, tmp_path):
    _setup_isolated_tick_store(monkeypatch, tmp_path)
    unknown_token = 42424242

    assert tick_store.get_last_tick(unknown_token, allow_db=False) is None
    assert tick_store.get_ltp(unknown_token) == (None, None)
    assert tick_store.get_age_sec(unknown_token) is None


def test_insert_tick_accepts_alias_kwargs(monkeypatch, tmp_path):
    _setup_isolated_tick_store(monkeypatch, tmp_path)
    token = 777123
    ts_epoch = float(time.time())

    ok = tick_store.insert_tick(
        ts_epoch=ts_epoch,
        instrument_token=token,
        last_price=150.5,
        volume=12,
        oi=7,
    )
    assert ok is True

    last_tick = tick_store.get_last_tick(token)
    assert isinstance(last_tick, dict)
    assert last_tick["ts_epoch"] == pytest.approx(ts_epoch)


def test_insert_tick_unknown_kwarg_raises_type_error(monkeypatch, tmp_path):
    _setup_isolated_tick_store(monkeypatch, tmp_path)

    with pytest.raises(TypeError) as exc:
        tick_store.insert_tick(
            ts=time.time(),
            token=1,
            last_price=100.0,
            volume=1,
            oi=1,
            bad_kwarg=True,
        )

    msg = str(exc.value)
    assert "bad_kwarg" in msg
    assert "Allowed kwargs" in msg
    assert "ts_epoch" in msg
    assert "instrument_token" in msg


def test_shutdown_completes_and_rejects_writes_after_shutdown(monkeypatch, tmp_path):
    _setup_isolated_tick_store(monkeypatch, tmp_path)
    try:
        tick_store.set_replay_pressure_immediate_flush_enabled(False)
        tick_store.set_replay_pressure_read_flush_enabled(False)
        for i in range(4):
            assert tick_store.insert_tick(time.time() + i, 1000 + i, 10.0 + i, 1, 1) is True

        result = tick_store.shutdown_persistence_worker(deadline_seconds=1.0)
        assert result["status"] == "COMPLETE_DRAIN"
        assert result["deadline_expired"] is False
        assert result["worker_join_completed"] is True
        assert result["worker_terminated"] is True
        assert result["worker_daemon"] is True
        assert result["rows_enqueued"] == 4
        assert result["rows_dequeued"] == 4
        assert result["rows_committed"] == 4
        assert result["pending_writes"] == 0
        assert result["queue_depth"] == 0
        assert result["writes_rejected_after_shutdown"] == 0

        assert tick_store.insert_tick(time.time(), 2000, 20.0, 1, 1) is False
        assert tick_store.get_audit_counters()["writes_rejected_after_shutdown"] == 1
    finally:
        tick_store.reset_audit_counters()
        tick_store.set_replay_pressure_immediate_flush_enabled(True)
        tick_store.set_replay_pressure_read_flush_enabled(True)


def test_shutdown_times_out_then_completes_on_retry(monkeypatch, tmp_path):
    _setup_isolated_tick_store(monkeypatch, tmp_path)
    try:
        tick_store.set_replay_pressure_immediate_flush_enabled(False)
        tick_store.set_replay_pressure_read_flush_enabled(False)
        for i in range(8):
            assert tick_store.insert_tick(time.time() + i, 3000 + i, 30.0 + i, 1, 1) is True

        original_write_rows = tick_store._write_rows

        def slow_write_rows(rows, *, worker_owned=False):
            if worker_owned:
                time.sleep(0.05)
            return original_write_rows(rows, worker_owned=worker_owned)

        monkeypatch.setattr(tick_store, "_write_rows", slow_write_rows)
        timeout_result = tick_store.shutdown_persistence_worker(deadline_seconds=0.001)
        assert timeout_result["status"] == "INCOMPLETE_DRAIN_TIMEOUT"
        assert timeout_result["deadline_expired"] is True
        assert timeout_result["worker_alive"] is True
        assert timeout_result["worker_join_completed"] is False
        assert timeout_result["worker_terminated"] is False
        assert timeout_result["queue_depth"] >= 0
        assert timeout_result["pending_writes"] >= timeout_result["queue_depth"]
        assert tick_store.get_persistence_worker_state()["initial_shutdown_result"] == timeout_result

        monkeypatch.setattr(tick_store, "_write_rows", original_write_rows)
        complete_result = tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
        assert complete_result["status"] == "COMPLETE_DRAIN"
        assert complete_result["worker_join_completed"] is True
        assert complete_result["worker_terminated"] is True
        assert complete_result["queue_depth"] == 0
        assert complete_result["pending_writes"] == 0
        state = tick_store.get_persistence_worker_state()
        assert state["initial_shutdown_result"] == timeout_result
        assert state["cleanup_shutdown_result"] == complete_result
        assert timeout_result["status"] == "INCOMPLETE_DRAIN_TIMEOUT"
    finally:
        tick_store.reset_audit_counters()
        tick_store.set_replay_pressure_immediate_flush_enabled(True)
        tick_store.set_replay_pressure_read_flush_enabled(True)


def test_shutdown_worker_failure_is_reported(monkeypatch, tmp_path):
    _setup_isolated_tick_store(monkeypatch, tmp_path)
    try:
        tick_store.set_replay_pressure_immediate_flush_enabled(False)
        tick_store.set_replay_pressure_read_flush_enabled(False)
        for i in range(3):
            assert tick_store.insert_tick(time.time() + i, 4000 + i, 40.0 + i, 1, 1) is True

        original_write_rows = tick_store._write_rows
        state = {"failed": False}

        def flaky_write_rows(rows, *, worker_owned=False):
            if worker_owned and not state["failed"]:
                state["failed"] = True
                tick_store._AUDIT_COUNTERS["worker_failures"] += 1
                return False
            return original_write_rows(rows, worker_owned=worker_owned)

        monkeypatch.setattr(tick_store, "_write_rows", flaky_write_rows)
        result = tick_store.shutdown_persistence_worker(deadline_seconds=1.0)
        assert result["status"] == "WORKER_FAILURE"
        assert result["worker_failures"] >= 1
        assert result["worker_daemon"] is True
    finally:
        tick_store.reset_audit_counters()
        tick_store.set_replay_pressure_immediate_flush_enabled(True)
        tick_store.set_replay_pressure_read_flush_enabled(True)
