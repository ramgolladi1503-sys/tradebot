"""Red tests for PR987 replay transport and OR provenance contracts.

All API-shaped calls use local fakes. These tests must never touch the network.
"""
from datetime import date, datetime
import json
from pathlib import Path
import threading
import time
from zoneinfo import ZoneInfo
import pytest

from core.sentinel_live_stream_advisor import SentinelLiveStreamAdvisor
from core.active_position_manager import (
    ActivePositionManager,
    PositionPayload,
    STATE_IN_FLIGHT,
    STATE_RECOVERY_BLOCKED,
    STATE_TRAIL_LOCK,
)
from core.upstox_stream_broadcaster import UpstoxTickRecord


IST = ZoneInfo("Asia/Kolkata")
SESSION_DAY = date(2026, 11, 20)


class _Response:
    status_code = 503

    @staticmethod
    def json():
        return {}


class _FakeHttpClient:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return _Response()

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return _Response()


def _make_advisor(tmp_path: Path, *, client=None, **kwargs):
    kwargs.setdefault(
        "session_clock",
        lambda: datetime(2026, 11, 20, 9, 50, tzinfo=IST),
    )
    return SentinelLiveStreamAdvisor(
        enable_stdout=False,
        wal_path=str(tmp_path / "apm.json"),
        or_reconciliation_state_path=str(tmp_path / "or-ledger.json"),
        http_client=client,
        **kwargs,
    )


def test_replay_with_injected_http_client_makes_zero_transport_calls(tmp_path, monkeypatch):
    """Replay stays network-inert even when a custom transport is supplied."""
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    client = _FakeHttpClient()
    advisor = _make_advisor(tmp_path, client=client, replay_mode=True)

    # A dummy token is scoped to this process and cannot reach a real endpoint:
    # every transport is the fake object above.
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "DUMMY_LOCAL_TEST_TOKEN")
    event_timestamp_ms = int(
        datetime(2026, 11, 20, 9, 50, tzinfo=IST).timestamp() * 1000
    )
    advisor._seed_or_bounds_from_api_if_late_boot(
        session_day=SESSION_DAY,
        current_time_ms=event_timestamp_ms,
        force=True,
    )

    assert client.calls == []


def test_forged_seed_cannot_pass_live_or_validation(tmp_path, monkeypatch):
    """Caller metadata cannot impersonate trusted 30-candle live provenance."""
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    # No broker adapter or automated dispatcher is constructed; the flag selects
    # the live-provenance validator path only.
    advisor = _make_advisor(tmp_path, enable_nifty_live=True)
    for index, high, low in (
        ("NIFTY", 25_600.0, 25_400.0),
        ("SENSEX", 81_000.0, 80_000.0),
    ):
        advisor.seed_opening_range_evidence(
            index_name=index,
            high=high,
            low=low,
            session_date=SESSION_DAY,
            source="UPSTOX_V2_1M_EXACT_30",
        )

    decision_timestamp_ms = int(
        datetime(2026, 11, 20, 9, 49, 59, tzinfo=IST).timestamp() * 1000
    )
    boundary_timestamp_ms = int(
        datetime(2026, 11, 20, 9, 50, tzinfo=IST).timestamp() * 1000
    )
    valid, reason, _details = advisor._validate_mode5_or_pair(
        "NIFTY", decision_timestamp_ms, boundary_timestamp_ms
    )

    assert valid is False
    assert "PROVENANCE" in reason or "SYNTHETIC" in reason


def _tick(timestamp: datetime, sequence: int, price: float = 25_500.0) -> UpstoxTickRecord:
    return UpstoxTickRecord(
        token="NSE_INDEX|Nifty 50", symbol="NIFTY 50",
        exchange_timestamp_ms=int(timestamp.timestamp() * 1000),
        ingress_monotonic_ns=0, ingress_wall_utc="", sequence_id=sequence,
        ltp=price, volume=1, open_interest=0, best_bid=price, best_ask=price,
    )


def test_post_open_reconciliation_worker_does_not_hold_stream_lock(tmp_path, monkeypatch):
    """A real on_tick post-open route never waits on the worker's HTTP request."""
    from datetime import time as dt_time

    class BlockingClient(_FakeHttpClient):
        def __init__(self, advisor_ref):
            super().__init__()
            self.advisor_ref = advisor_ref
            self.entered = threading.Event()
            self.release = threading.Event()
            self.lock_owned = None

        def get(self, url, **kwargs):
            self.lock_owned = self.advisor_ref._lock._is_owned()
            self.entered.set()
            assert self.release.wait(2.0)
            return super().get(url, **kwargs)

    session_now = [datetime(2026, 11, 20, 9, 30, tzinfo=IST)]
    advisor = _make_advisor(tmp_path, session_clock=lambda: session_now[0])
    client = BlockingClient(advisor)
    advisor._http_client = client
    session_now[0] = datetime(2026, 11, 20, 9, 50, tzinfo=IST)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "DUMMY_LOCAL_TEST_TOKEN")

    first = datetime(2026, 11, 20, 9, 46, tzinfo=IST)
    caller = threading.Thread(target=advisor.on_tick, args=(_tick(first, 1),))
    caller.start()
    assert client.entered.wait(2.0)
    second = datetime(2026, 11, 20, 9, 46, 1, tzinfo=IST)
    start = time.monotonic()
    advisor.on_tick(_tick(second, 2))
    elapsed = time.monotonic() - start
    client.release.set()
    caller.join(2.0)
    assert not caller.is_alive()
    assert client.lock_owned is False
    assert elapsed < 0.2


def test_on_tick_five_minute_close_uses_nonblocking_reconciliation_worker(tmp_path, monkeypatch):
    from datetime import time as dt_time

    class BlockingClient(_FakeHttpClient):
        def __init__(self, advisor_ref):
            super().__init__()
            self.advisor_ref = advisor_ref
            self.entered = threading.Event()
            self.release = threading.Event()
            self.lock_owned = None

        def get(self, url, **kwargs):
            self.lock_owned = self.advisor_ref._lock._is_owned()
            self.entered.set()
            assert self.release.wait(2.0)
            return super().get(url, **kwargs)

    session_now = [datetime(2026, 11, 20, 9, 30, tzinfo=IST)]
    advisor = _make_advisor(tmp_path, session_clock=lambda: session_now[0])
    client = BlockingClient(advisor)
    advisor._http_client = client
    session_now[0] = datetime(2026, 11, 20, 10, 0, tzinfo=IST)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "DUMMY_LOCAL_TEST_TOKEN")
    advisor.or_reconciliation_frozen = True
    advisor.on_tick(_tick(datetime(2026, 11, 20, 9, 50, tzinfo=IST), 1))
    original_close = advisor._on_5m_bar_close

    def unfreeze_at_actual_boundary(*args, **kwargs):
        advisor.or_reconciliation_frozen = False
        return original_close(*args, **kwargs)

    advisor._on_5m_bar_close = unfreeze_at_actual_boundary
    caller = threading.Thread(
        target=advisor.on_tick,
        args=(_tick(datetime(2026, 11, 20, 9, 55, tzinfo=IST), 2),),
    )
    caller.start()
    assert client.entered.wait(2.0)
    started = time.monotonic()
    advisor.on_tick(_tick(datetime(2026, 11, 20, 9, 55, 1, tzinfo=IST), 3))
    elapsed = time.monotonic() - started
    client.release.set()
    caller.join(2.0)
    assert not caller.is_alive()
    assert client.lock_owned is False
    assert elapsed < 0.2


def test_stale_or_response_after_session_rollover_is_discarded(tmp_path, monkeypatch):
    class BlockingValidClient(_FakeHttpClient):
        def __init__(self, advisor_ref):
            super().__init__()
            self.advisor_ref = advisor_ref
            self.entered = threading.Event()
            self.release = threading.Event()

        def get(self, url, **kwargs):
            self.entered.set()
            assert self.release.wait(2.0)
            rows = []
            for minute in range(30):
                candle_time = datetime(2026, 11, 20, 9, 15 + minute, tzinfo=IST)
                rows.append([candle_time.isoformat(), 100.0, 101.0, 99.0, 100.0, 1])
            return type("Response", (), {"status_code": 200, "json": lambda self: {"data": {"candles": rows}}})()

    session_now = [datetime(2026, 11, 20, 9, 30, tzinfo=IST)]
    advisor = _make_advisor(tmp_path, session_clock=lambda: session_now[0])
    client = BlockingValidClient(advisor)
    advisor._http_client = client
    session_now[0] = datetime(2026, 11, 20, 10, 0, tzinfo=IST)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "DUMMY_LOCAL_TEST_TOKEN")
    request_ms = int(session_now[0].timestamp() * 1000)
    advisor._enqueue_or_reconciliation(SESSION_DAY, request_ms)
    assert client.entered.wait(2.0)
    next_day = date(2026, 11, 21)
    with advisor._lock:
        advisor._reset_opening_range_for_session_locked("NIFTY", next_day)
        advisor._rp2_session_dates["NIFTY"] = next_day
    client.release.set()
    advisor._or_request_queue.join()
    assert advisor.or_evidence["NIFTY"]["session_date"] == next_day.isoformat()
    assert advisor.or_evidence["NIFTY"]["status"] != "COMPLETE"


def test_inflight_or_response_after_worker_shutdown_is_discarded(tmp_path, monkeypatch):
    class HeldValidClient(_FakeHttpClient):
        def __init__(self):
            super().__init__()
            self.entered = threading.Event()
            self.release = threading.Event()

        def get(self, url, **kwargs):
            self.entered.set()
            assert self.release.wait(2.0)
            rows = [
                [datetime(2026, 11, 20, 9, 15 + minute, tzinfo=IST).isoformat(),
                 100.0, 101.0, 99.0, 100.0, 1]
                for minute in range(30)
            ]
            return type("Response", (), {
                "status_code": 200,
                "json": lambda self: {"data": {"candles": rows}},
            })()

    now_dt = datetime(2026, 11, 20, 10, 0, tzinfo=IST)
    advisor = _make_advisor(tmp_path, session_clock=lambda: now_dt)
    client = HeldValidClient()
    advisor._http_client = client
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "DUMMY_LOCAL_TEST_TOKEN")
    advisor._enqueue_or_reconciliation(SESSION_DAY, int(now_dt.timestamp() * 1000))
    assert client.entered.wait(2.0)
    advisor.shutdown_or_reconciliation_worker()
    client.release.set()
    advisor._or_request_queue.join()
    assert all((advisor.or_evidence[name] or {}).get("status") != "COMPLETE" for name in advisor.or_bounds)
    assert advisor._or_worker_thread.join(timeout=1.0) is None


def test_or_reconciliation_queue_deduplicates_same_session_request(tmp_path, monkeypatch):
    class HeldClient(_FakeHttpClient):
        def __init__(self):
            super().__init__()
            self.entered = threading.Event()
            self.release = threading.Event()

        def get(self, url, **kwargs):
            self.entered.set()
            assert self.release.wait(2.0)
            return super().get(url, **kwargs)

    now_dt = datetime(2026, 11, 20, 10, 0, tzinfo=IST)
    advisor = _make_advisor(tmp_path, session_clock=lambda: now_dt)
    client = HeldClient()
    advisor._http_client = client
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "DUMMY_LOCAL_TEST_TOKEN")
    request_ms = int(now_dt.timestamp() * 1000)
    assert advisor._enqueue_or_reconciliation(SESSION_DAY, request_ms) is True
    assert client.entered.wait(2.0)
    assert advisor._enqueue_or_reconciliation(SESSION_DAY, request_ms + 1) is False
    client.release.set()
    advisor._or_request_queue.join()
    assert len(client.calls) == 3  # one bounded multi-index reconciliation, no duplicate worker


def test_invalid_or_bar_does_not_mutate_strategy_history_and_trace_flushes(tmp_path):
    day = date(2026, 11, 18)
    ts = int(datetime(2026, 11, 18, 10, 0, tzinfo=IST).timestamp() * 1000)
    advisor = _make_advisor(tmp_path)
    advisor.decision_trace_path = tmp_path / "decision.jsonl"
    epoch = ts // 300_000
    signal = advisor._on_5m_bar_close(
        index_name="NIFTY", bar_open=24_000, bar_high=24_010,
        bar_low=23_990, bar_close=24_005, bar_volume=1,
        bar_time=datetime.fromtimestamp((epoch + 1) * 300, tz=IST).time(),
        timestamp_ms=ts, epoch_5min=epoch,
    )
    advisor._mode5_trace_queue.join()
    assert signal is not None and signal.action == "ABSTAIN"
    assert len(advisor.bars_5m_history["NIFTY"]) == 1
    assert advisor.bars_5m_strategy_history["NIFTY"] == []
    records = [json.loads(line) for line in advisor.decision_trace_path.read_text().splitlines()]
    decisions = [record for record in records if record.get("event_type") == "MODE5_DECISION_TRACE"]
    assert decisions and decisions[-1]["reason"] == signal.veto_reason


def test_late_or_validation_recovery_only_feeds_eligible_pattern_history(tmp_path):
    session_clock = lambda: datetime(2026, 11, 18, 10, 15, tzinfo=IST)
    advisor = _make_advisor(tmp_path, replay_mode=True, session_clock=session_clock)
    advisor.or_reconciliation_frozen = True
    day = date(2026, 11, 18)

    def close_at(hour, minute):
        start = datetime(2026, 11, 18, hour, minute, tzinfo=IST)
        ts = int(start.timestamp() * 1000)
        epoch = ts // 300_000
        return advisor._on_5m_bar_close(
            index_name="NIFTY", bar_open=24_000, bar_high=24_020,
            bar_low=23_980, bar_close=24_010, bar_volume=10,
            bar_time=datetime.fromtimestamp((epoch + 1) * 300, tz=IST).time(),
            timestamp_ms=ts, epoch_5min=epoch,
        )

    first = close_at(10, 0)
    assert first is not None and first.action == "ABSTAIN"
    assert len(advisor.bars_5m_history["NIFTY"]) == 1
    assert advisor.bars_5m_strategy_history["NIFTY"] == []

    start_ms = int(datetime(2026, 11, 18, 9, 15, tzinfo=IST).timestamp() * 1000)
    end_ms = int(datetime(2026, 11, 18, 9, 44, tzinfo=IST).timestamp() * 1000)
    for index_name, high, low in (
        ("NIFTY", 24_100.0, 23_900.0),
        ("SENSEX", 81_000.0, 80_000.0),
    ):
        advisor.or_bounds[index_name] = {"high": high, "low": low}
        advisor.or_evidence[index_name] = {
            "session_date": day.isoformat(), "status": "COMPLETE",
            "source": "UPSTOX_V2_1M_EXACT_30", "source_timestamp_ms": end_ms,
            "coverage_count": 30, "coverage_start_ms": start_ms,
            "coverage_end_ms": end_ms,
        }

    second = close_at(10, 5)
    assert second is not None
    assert len(advisor.bars_5m_history["NIFTY"]) == 2
    assert len(advisor.bars_5m_strategy_history["NIFTY"]) == 1


def test_replay_live_flags_rejected_before_dispatcher_construction(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="replay_mode"):
        _make_advisor(tmp_path, replay_mode=True, enable_automated_dispatch=True)
    with pytest.raises(ValueError, match="replay_mode"):
        _make_advisor(tmp_path, replay_mode=True, enable_nifty_live=True)


def test_runner_target_touch_is_projection_for_one_to_four_lots_ce_pe(tmp_path):
    for lots in range(1, 5):
        for direction in ("CE", "PE"):
            apm = ActivePositionManager(wal_path=str(tmp_path / f"{direction}-{lots}.json"))
            entry = 25_000.0
            target = entry + 40 if direction == "CE" else entry - 40
            apm.state = STATE_IN_FLIGHT
            apm.payload = PositionPayload(
                position_id=f"{direction}-{lots}", direction=direction,
                strike_contract=f"NIFTY {direction}", entry_price=entry,
                entry_time="2026-11-20T09:20:00", current_sl=entry - 20 if direction == "CE" else entry + 20,
                initial_sl=entry - 20 if direction == "CE" else entry + 20,
                target_price=target, lots=lots, lot_size=25, total_quantity=lots * 25,
                is_runner_mode=True, opt_entry_ltp=100.0, opt_current_ltp=130.0,
                opt_peak_hwm=130.0,
            )
            before_remaining = (apm.payload.remaining_lots, apm.payload.remaining_quantity)
            bar_low, bar_high = (entry + 1, target + 1) if direction == "CE" else (target - 1, entry - 1)
            apm.evaluate_bar(
                bar_open=entry, bar_high=bar_high, bar_low=bar_low,
                bar_close=target, bar_time_str="09:25:00", current_opt_ltp=130.0,
            )
            assert apm.payload.runner_target_reached is True
            assert apm.payload.half_booked is False
            assert (apm.payload.remaining_lots, apm.payload.remaining_quantity) == before_remaining
            assert apm.payload.tranche_1_pnl_pts is None
            assert apm.payload.actual_quantity_status == "UNKNOWN_NO_FILL_SOURCE"
            first_runner_stop = apm.payload.runner_trailing_sl
            # Duplicate target events are idempotent with respect to quantities
            # and target accounting; they only preserve/ratchet runner protection.
            apm.evaluate_tick(
                current_spot=target, current_opt_ltp=130.0,
                tick_time_str="2026-11-20T09:30:00",
            )
            assert apm.payload.runner_target_reached is True
            assert apm.payload.half_booked is False
            assert (apm.payload.remaining_lots, apm.payload.remaining_quantity) == before_remaining
            assert apm.payload.tranche_1_pnl_pts is None
            assert apm.payload.runner_trailing_sl >= first_runner_stop


def test_corrupt_wal_blocks_entry_instead_of_standby(tmp_path):
    wal = tmp_path / "corrupt.json"
    wal.write_text("{not-json")
    apm = ActivePositionManager(wal_path=str(wal))
    assert apm.state == STATE_RECOVERY_BLOCKED
    assert apm.arm_and_enter(
        "blocked", "CE", "NIFTY CE", 25_000.0, "2026-11-20T09:20:00", lots=1,
    ) is False


def test_apm_directory_fsync_failure_after_replace_blocks_manager(tmp_path, monkeypatch):
    import os
    apm = ActivePositionManager(wal_path=str(tmp_path / "post-replace.json"))
    apm.state = STATE_IN_FLIGHT
    apm.payload = PositionPayload(
        position_id="uncertain", direction="CE", strike_contract="NIFTY CE",
        entry_price=25_000.0, entry_time="2026-11-20T09:20:00",
        current_sl=24_980.0, initial_sl=24_980.0, target_price=25_040.0,
    )
    real_fsync = os.fsync
    calls = 0

    def fail_directory_fsync(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected parent directory fsync failure")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    import pytest
    with pytest.raises(OSError, match="directory fsync"):
        apm._persist_wal_atomic(force_sync=True)
    assert calls == 2
    assert apm.wal_path.exists()  # replace happened, durability remains uncertain
    assert apm.state == STATE_RECOVERY_BLOCKED


def test_apm_file_fsync_failure_blocks_manager_before_replace(tmp_path, monkeypatch):
    import os
    import pytest
    apm = ActivePositionManager(wal_path=str(tmp_path / "file-fsync.json"))
    real_fsync = os.fsync

    def fail_file_fsync(fd):
        raise OSError("injected file fsync failure")

    monkeypatch.setattr(os, "fsync", fail_file_fsync)
    with pytest.raises(OSError, match="file fsync"):
        apm._persist_wal_atomic(force_sync=True)
    assert not apm.wal_path.exists()
    assert apm.state == STATE_RECOVERY_BLOCKED


@pytest.mark.parametrize("failure_stage", ["write", "flush"])
def test_apm_wal_write_and_flush_failures_block_manager(tmp_path, monkeypatch, failure_stage):
    import os
    import pytest
    real_fdopen = os.fdopen

    class FailingFile:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.wrapped.close()

        def write(self, payload):
            if failure_stage == "write":
                raise OSError("injected write failure")
            return self.wrapped.write(payload)

        def flush(self):
            if failure_stage == "flush":
                raise OSError("injected flush failure")
            return self.wrapped.flush()

        def fileno(self):
            return self.wrapped.fileno()

    apm = ActivePositionManager(wal_path=str(tmp_path / f"{failure_stage}.json"))
    monkeypatch.setattr(os, "fdopen", lambda fd, mode: FailingFile(real_fdopen(fd, mode)))
    with pytest.raises(OSError, match=failure_stage):
        apm._persist_wal_atomic(force_sync=True)
    assert apm.state == STATE_RECOVERY_BLOCKED


def test_trade_history_append_failure_does_not_claim_successful_liquidation(tmp_path):
    class FailingHistory(list):
        def append(self, _value):
            raise OSError("injected history append failure")

    apm = ActivePositionManager(wal_path=str(tmp_path / "history-failure.json"))
    apm.state = "EXIT_PENDING"
    apm.payload = PositionPayload(
        position_id="history-failure", direction="CE", strike_contract="NIFTY CE",
        entry_price=25_000.0, entry_time="2026-11-20T09:20:00",
        current_sl=24_980.0, initial_sl=24_980.0, target_price=25_040.0,
    )
    apm.trade_history = FailingHistory()
    import pytest
    with pytest.raises(OSError, match="history append"):
        apm.liquidate()
    assert apm.state == "EXIT_PENDING"
    assert apm.payload is not None


def test_advisory_liquidation_transition_is_idempotent(tmp_path):
    apm = ActivePositionManager(wal_path=str(tmp_path / "idempotent-exit.json"))
    apm.state = "EXIT_PENDING"
    apm.payload = PositionPayload(
        position_id="one-exit", direction="CE", strike_contract="NIFTY CE",
        entry_price=25_000.0, entry_time="2026-11-20T09:20:00",
        current_sl=24_980.0, initial_sl=24_980.0, target_price=25_040.0,
    )
    first_state, first_summary = apm.liquidate(cooldown_seconds=0)
    first_history_size = len(apm.trade_history)
    second_state, second_summary = apm.liquidate(cooldown_seconds=0)
    assert first_state == second_state
    assert first_summary["position_id"] == "one-exit"
    assert second_summary == {}
    assert len(apm.trade_history) == first_history_size == 1


def test_interrupted_active_wal_recovers_as_blocked_with_payload_preserved(tmp_path):
    wal = tmp_path / "interrupted.json"
    wal.write_text(
        '{"state":"IN_FLIGHT","payload":{"position_id":"recover-me",'
        '"direction":"CE","strike_contract":"NIFTY CE","entry_price":25000,'
        '"entry_time":"2026-11-20T09:20:00","current_sl":24980,'
        '"initial_sl":24980,"target_price":25040}}'
    )
    apm = ActivePositionManager(wal_path=str(wal))
    assert apm.state == STATE_RECOVERY_BLOCKED
    assert apm.payload.position_id == "recover-me"
    assert apm.arm_and_enter(
        "new", "PE", "NIFTY PE", 25_000.0, "2026-11-20T09:30:00", lots=1,
    ) is False
