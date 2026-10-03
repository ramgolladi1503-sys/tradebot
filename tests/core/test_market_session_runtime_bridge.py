import json
import os
from collections import defaultdict, deque
from datetime import datetime, timedelta
import subprocess
import sys
import textwrap
from zoneinfo import ZoneInfo

import pytest

from core import market_session_memory_contract as contract
from core import ohlc_buffer as ohlc_module
from core.market_data import _ingest_trusted_ltp_tick
from core.market_session_store import MarketSessionStore
from core.time_utils import IST_TZ

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture(autouse=True)
def _restore_global_buffer_store(monkeypatch):
    """Keep explicit bridge installs from leaking a per-test SQLite store."""
    previous_store = getattr(ohlc_module.ohlc_buffer, "_session_store", None)
    monkeypatch.setattr(
        ohlc_module.ohlc_buffer, "_session_store", previous_store, raising=False
    )


def test_explicit_runtime_install_connects_singleton_buffer_to_durable_store(tmp_path, monkeypatch):
    db_path = tmp_path / "market-session.sqlite"
    store = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    previous_store = getattr(ohlc_module.ohlc_buffer, "_session_store", None)
    monkeypatch.setattr(ohlc_module.ohlc_buffer, "_session_store", previous_store, raising=False)
    monkeypatch.setattr(contract, "market_session_store", store)
    monkeypatch.setattr(contract, "_INSTALLED", False)
    monkeypatch.setattr(contract, "_INSTALL_STATUS", {})

    status = contract.install()
    assert status == {
        "installed": True,
        "store_enabled": True,
        "buffer_connected": True,
        "status": "PERSISTENCE_READY",
    }

    symbol = "ISSUE9TEST"
    first_minute = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    provenance = {
        "source_type": "deterministic_test",
        "live_feed_session_id": "runtime-bridge-test",
        "replay_fixture": False,
        "historical_seed": False,
        "non_live_fallback": False,
        "recovered_synthetic": False,
    }
    ohlc_module.ohlc_buffer.update_tick(symbol, 25000.0, ts=first_minute, provenance=provenance)
    ohlc_module.ohlc_buffer.update_tick(
        symbol, 25001.0, ts=first_minute + timedelta(minutes=1), provenance=provenance
    )
    completed = ohlc_module.ohlc_buffer.get_completed_bars(
        symbol, as_of=first_minute + timedelta(minutes=2)
    )
    assert len(completed) == 2

    reopened = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    durable = reopened.get_bars(
        symbol, as_of=first_minute + timedelta(minutes=2), timeframe="1m"
    )
    assert len(durable) == 2
    assert durable[0]["open"] == 25000.0


def test_stale_quote_across_minute_boundary_cannot_finalize_or_persist_live_bar(tmp_path, monkeypatch):
    db_path = tmp_path / "stale-session.sqlite"
    store = MarketSessionStore(db_path=db_path, report_root=tmp_path / "stale-reports")
    monkeypatch.setattr(contract, "market_session_store", store)
    monkeypatch.setattr(contract, "_INSTALLED", False)
    monkeypatch.setattr(contract, "_INSTALL_STATUS", {})
    assert contract.install()["status"] == "PERSISTENCE_READY"

    buffer = ohlc_module.OhlcBuffer(session_store=store)
    first_event = datetime(2026, 9, 7, 9, 15, 5, tzinfo=IST)
    provenance = {
        "live_feed_session_id": "stale-boundary-test",
        "replay_fixture": False,
        "historical_seed": False,
        "non_live_fallback": False,
        "recovered_synthetic": False,
    }
    first = _ingest_trusted_ltp_tick(
        buffer=buffer, symbol="STALETEST", price=25000.0, volume=None,
        ltp_source="live", ltp_ts_epoch=first_event.timestamp(),
        cycle_cutoff=first_event + timedelta(seconds=1), market_open=True,
        max_ltp_age_sec=8.0, provenance=provenance,
    )
    assert first["accepted"] is True

    stale_cutoff = datetime(2026, 9, 7, 9, 16, 30, tzinfo=IST)
    stale = _ingest_trusted_ltp_tick(
        buffer=buffer, symbol="STALETEST", price=25001.0, volume=None,
        ltp_source="live", ltp_ts_epoch=(first_event + timedelta(seconds=1)).timestamp(),
        cycle_cutoff=stale_cutoff, market_open=True,
        max_ltp_age_sec=8.0, provenance=provenance,
    )
    assert stale["accepted"] is False
    assert stale["status"] == "LTP_SOURCE_TIMESTAMP_STALE"
    assert len(buffer.get_bars("STALETEST")) == 1

    reopened = MarketSessionStore(db_path=db_path, report_root=tmp_path / "stale-reports")
    assert reopened.get_bars(
        "STALETEST", as_of=stale_cutoff, timeframe="1m"
    ) == []


def test_offhours_stale_quote_is_rejected_at_configured_age_limit():
    buffer = ohlc_module.OhlcBuffer()
    cutoff = datetime(2026, 10, 1, 15, 45, tzinfo=IST)
    stale_event = cutoff - timedelta(seconds=901)
    result = _ingest_trusted_ltp_tick(
        buffer=buffer, symbol="OFFHOURSTALE", price=25000.0, volume=None,
        ltp_source="live", ltp_ts_epoch=stale_event.timestamp(),
        cycle_cutoff=cutoff, market_open=False, max_ltp_age_sec=900.0,
        provenance={},
    )
    assert result["accepted"] is False
    assert result["status"] == "LTP_SOURCE_TIMESTAMP_STALE"
    assert buffer.get_bars("OFFHOURSTALE") == []


def test_invalid_ltp_age_limit_fails_closed():
    buffer = ohlc_module.OhlcBuffer()
    cutoff = datetime(2026, 10, 1, 15, 45, tzinfo=IST)
    event = cutoff - timedelta(seconds=1)
    result = _ingest_trusted_ltp_tick(
        buffer=buffer, symbol="INVALIDLIMIT", price=25000.0, volume=None,
        ltp_source="live", ltp_ts_epoch=event.timestamp(), cycle_cutoff=cutoff,
        market_open=False, max_ltp_age_sec=float("nan"), provenance={},
    )
    assert result["accepted"] is False
    assert result["status"] == "INVALID_LTP_AGE_LIMIT"
    assert buffer.get_bars("INVALIDLIMIT") == []


def test_missing_future_and_untrusted_ltp_sources_are_not_ingested():
    buffer = ohlc_module.OhlcBuffer()
    cutoff = datetime(2026, 9, 7, 9, 16, tzinfo=IST)
    common = {
        "buffer": buffer, "symbol": "SOURCEGATE", "price": 25000.0, "volume": None,
        "cycle_cutoff": cutoff, "market_open": True,
        "max_ltp_age_sec": 8.0, "provenance": {},
    }
    missing = _ingest_trusted_ltp_tick(
        **common, ltp_source="live", ltp_ts_epoch=None,
    )
    future = _ingest_trusted_ltp_tick(
        **common, ltp_source="live", ltp_ts_epoch=(cutoff + timedelta(seconds=1)).timestamp(),
    )
    untrusted = _ingest_trusted_ltp_tick(
        **common, ltp_source="cache", ltp_ts_epoch=cutoff.timestamp(),
    )
    non_finite_timestamp = _ingest_trusted_ltp_tick(
        **common, ltp_source="live", ltp_ts_epoch=float("nan"),
    )
    invalid_prices = [
        _ingest_trusted_ltp_tick(
            **{**common, "symbol": f"BADPRICE{index}", "price": price},
            ltp_source="live", ltp_ts_epoch=cutoff.timestamp(),
        )
        for index, price in enumerate((float("nan"), float("inf"), 0.0, -1.0))
    ]
    assert missing["status"] == "LTP_SOURCE_TIMESTAMP_MISSING"
    assert future["status"] == "LTP_SOURCE_TIMESTAMP_FUTURE"
    assert untrusted["status"] == "UNTRUSTED_LTP_SOURCE"
    assert non_finite_timestamp["status"] == "LTP_SOURCE_TIMESTAMP_INVALID"
    assert buffer.get_bars("SOURCEGATE") == []
    assert [item["status"] for item in invalid_prices] == ["INVALID_LTP_PRICE"] * 4
    assert all(buffer.get_bars(f"BADPRICE{index}") == [] for index in range(4))


def test_shared_ohlc_buffer_rejects_non_finite_and_non_positive_prices():
    buffer = ohlc_module.OhlcBuffer()
    timestamp = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    for index, price in enumerate((float("nan"), float("inf"), 0.0, -1.0)):
        result = buffer.update_tick(f"BUFFERBAD{index}", price, ts=timestamp)
        assert result["accepted"] is False
        assert result["status"] == "INVALID_TICK"
        assert buffer.get_bars(f"BUFFERBAD{index}") == []


def test_normal_trusted_tick_restart_path_hydrates_c1_from_durable_bars(tmp_path, monkeypatch):
    store_path = tmp_path / "runtime-market-session.sqlite"
    report_root = tmp_path / "runtime-reports"
    store = MarketSessionStore(db_path=store_path, report_root=report_root)
    previous_store = getattr(ohlc_module.ohlc_buffer, "_session_store", None)
    monkeypatch.setattr(ohlc_module.ohlc_buffer, "_session_store", previous_store, raising=False)
    monkeypatch.setattr(contract, "market_session_store", store)
    monkeypatch.setattr(contract, "_INSTALLED", False)
    monkeypatch.setattr(contract, "_INSTALL_STATUS", {})
    assert contract.install()["status"] == "PERSISTENCE_READY"

    orchestrator = __import__("core.orchestrator", fromlist=["_evaluate_c1_c2_for_symbol"])
    monkeypatch.setattr(orchestrator, "_global_market_session_store", store)
    monkeypatch.setattr(
        ohlc_module.ohlc_buffer, "_bars",
        defaultdict(lambda: deque(maxlen=500)),
    )

    session_open = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    for index in range(31):
        event_time = session_open + timedelta(minutes=index, seconds=5)
        result = _ingest_trusted_ltp_tick(
            buffer=ohlc_module.ohlc_buffer,
            symbol="NIFTY",
            price=25000.0 + index * 10.0,
            volume=None,
            ltp_source="live",
            ltp_ts_epoch=event_time.timestamp(),
            cycle_cutoff=event_time,
            market_open=True,
            max_ltp_age_sec=8.0,
            provenance={
                "live_feed_session_id": "offline-runtime-restart-test",
                "reconnect_generation": 1,
                "historical_seed": False,
                "replay_fixture": False,
                "non_live_fallback": False,
                "recovered_synthetic": False,
            },
        )
        assert result["accepted"] is True

    decision_time = session_open + timedelta(minutes=30)
    # Simulate a fresh process: no process-local bars survive, only the database.
    ohlc_module.ohlc_buffer._bars.clear()
    restored = ohlc_module.ohlc_buffer.get_completed_bars(
        "NIFTY", as_of=decision_time
    )
    assert len(restored) == 30
    assert restored[0]["ts"] == session_open
    assert restored[-1]["ts"] == session_open + timedelta(minutes=29)

    reopened = MarketSessionStore(db_path=store_path, report_root=report_root)
    monkeypatch.setattr(orchestrator, "_global_market_session_store", reopened)
    market_data = {
        "valid": True,
        "timestamp": decision_time.timestamp(),
        "ltp_ts_epoch": decision_time.timestamp(),
        "ltp_source": "live",
        "time_sanity": {"ok": True, "ltp_ts_epoch": decision_time.timestamp()},
        "offhours_mode": False,
    }
    evaluations, candidates = orchestrator._evaluate_c1_c2_for_symbol(
        market_data=market_data,
        sym="NIFTY",
        trace_id="restart-causal-memory-test",
        ts_str=decision_time.strftime("%Y-%m-%d %H:%M:%S%z"),
    )

    c1 = next(result for result in evaluations if result.strategy_id == "C1_INTRADAY_15M_IMPULSE")
    assert c1.reason_code == "C1_QUALIFIED"
    assert len(candidates) == 1
    assert candidates[0].trace_id == "restart-causal-memory-test"


def test_fresh_interpreter_restart_restores_completed_bars_and_evaluates_c1(tmp_path):
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    db_path = tmp_path / "process-restart" / "market-session.sqlite"
    report_root = tmp_path / "process-restart" / "reports"
    session_open = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    decision_time = session_open + timedelta(minutes=30)
    common_env = {
        **os.environ,
        "DB_ROOT": str(tmp_path / "isolated-default-db"),
        "DATA_ROOT": str(tmp_path / "isolated-data-root"),
        "PYTHONPATH": str(repo_root) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    writer = textwrap.dedent(
        """
        import sys
        from datetime import datetime, timedelta
        from pathlib import Path
        from zoneinfo import ZoneInfo

        from core import market_session_memory_contract as contract
        from core import ohlc_buffer as ohlc
        from core.market_session_store import MarketSessionStore

        db_path, report_root = map(Path, sys.argv[1:3])
        store = MarketSessionStore(db_path=db_path, report_root=report_root)
        contract.market_session_store = store
        contract._INSTALLED = False
        contract._INSTALL_STATUS = {}
        assert contract.install()["status"] == "PERSISTENCE_READY"
        opened = datetime(2026, 9, 7, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
        provenance = {
            "source_type": "deterministic_test",
            "live_feed_session_id": "offline-fresh-process-restart",
            "replay_fixture": False,
            "historical_seed": False,
            "non_live_fallback": False,
            "recovered_synthetic": False,
        }
        for minute in range(31):
            event_time = opened + timedelta(minutes=minute, seconds=5)
            result = ohlc.ohlc_buffer.update_tick(
                "NIFTY", 25000.0 + minute * 10.0, ts=event_time,
                provenance=provenance,
            )
            assert result["accepted"] is True
            if minute:
                assert result["session_memory_persisted"] is True
        assert len(store.get_bars("NIFTY", as_of=opened + timedelta(minutes=30), timeframe="1m")) == 30
        """
    )
    writer_result = subprocess.run(
        [sys.executable, "-c", writer, str(db_path), str(report_root)],
        cwd=repo_root,
        env=common_env,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert writer_result.returncode == 0, writer_result.stdout + writer_result.stderr

    reader = textwrap.dedent(
        """
        import json
        import sys
        from datetime import datetime, timedelta
        from pathlib import Path
        from zoneinfo import ZoneInfo

        from core import market_session_memory_contract as contract
        from core import ohlc_buffer as ohlc
        from core.market_session_store import MarketSessionStore
        from core.orchestrator import _evaluate_c1_c2_for_symbol

        db_path, report_root = map(Path, sys.argv[1:3])
        store = MarketSessionStore(db_path=db_path, report_root=report_root)
        contract.market_session_store = store
        contract._INSTALLED = False
        contract._INSTALL_STATUS = {}
        assert contract.install()["status"] == "PERSISTENCE_READY"
        _global = __import__("core.orchestrator", fromlist=["_unused"])
        _global._global_market_session_store = store
        opened = datetime(2026, 9, 7, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
        decision = opened + timedelta(minutes=30)
        restored = ohlc.ohlc_buffer.get_completed_bars("NIFTY", as_of=decision)
        market_data = {
            "valid": True,
            "timestamp": decision.timestamp(),
            "ltp_ts_epoch": decision.timestamp(),
            "ltp_source": "tick_store",
            "time_sanity": {"ok": True, "ltp_ts_epoch": decision.timestamp()},
            "offhours_mode": False,
        }
        evaluations, candidates = _evaluate_c1_c2_for_symbol(
            market_data=market_data, sym="NIFTY", trace_id="fresh-process-restart",
            ts_str=decision.strftime("%Y-%m-%d %H:%M:%S%z"),
        )
        c1 = next(item for item in evaluations if item.strategy_id == "C1_INTRADAY_15M_IMPULSE")
        print(json.dumps({
            "restored_count": len(restored),
            "first_ts": restored[0]["ts"].isoformat() if restored else None,
            "last_ts": restored[-1]["ts"].isoformat() if restored else None,
            "c1_reason": c1.reason_code,
            "candidate_count": len(candidates),
        }))
        """
    )
    reader_result = subprocess.run(
        [sys.executable, "-c", reader, str(db_path), str(report_root)],
        cwd=repo_root,
        env=common_env,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert reader_result.returncode == 0, reader_result.stdout + reader_result.stderr
    result = json.loads(reader_result.stdout.strip().splitlines()[-1])

    assert result == {
        "restored_count": 30,
        "first_ts": session_open.isoformat(),
        "last_ts": (session_open + timedelta(minutes=29)).isoformat(),
        "c1_reason": "C1_QUALIFIED",
        "candidate_count": 1,
    }


def test_completed_history_survives_duplicate_and_late_tick_attack_after_restart(tmp_path, monkeypatch):
    db_path = tmp_path / "attacked-session.sqlite"
    report_root = tmp_path / "attacked-reports"
    store = MarketSessionStore(db_path=db_path, report_root=report_root)
    previous_store = getattr(ohlc_module.ohlc_buffer, "_session_store", None)
    monkeypatch.setattr(ohlc_module.ohlc_buffer, "_session_store", previous_store, raising=False)
    monkeypatch.setattr(contract, "market_session_store", store)
    monkeypatch.setattr(contract, "_INSTALLED", False)
    monkeypatch.setattr(contract, "_INSTALL_STATUS", {})
    assert contract.install()["status"] == "PERSISTENCE_READY"

    buffer = ohlc_module.OhlcBuffer(session_store=store)
    opened = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    provenance = {
        "live_feed_session_id": "restart-attack-test",
        "reconnect_generation": 1,
        "historical_seed": False,
        "replay_fixture": False,
        "non_live_fallback": False,
        "recovered_synthetic": False,
    }

    for index in range(15):
        event_time = opened + timedelta(minutes=index, seconds=5)
        result = _ingest_trusted_ltp_tick(
            buffer=buffer,
            symbol="NIFTY",
            price=25000.0 + index,
            volume=None,
            ltp_source="live",
            ltp_ts_epoch=event_time.timestamp(),
            cycle_cutoff=event_time,
            market_open=True,
            max_ltp_age_sec=8.0,
            provenance=provenance,
        )
        assert result["accepted"] is True

    duplicate_time = opened + timedelta(minutes=14, seconds=5)
    duplicate = _ingest_trusted_ltp_tick(
        buffer=buffer,
        symbol="NIFTY",
        price=25014.0,
        volume=None,
        ltp_source="live",
        ltp_ts_epoch=duplicate_time.timestamp(),
        cycle_cutoff=duplicate_time,
        market_open=True,
        max_ltp_age_sec=8.0,
        provenance=provenance,
    )
    assert duplicate["accepted"] is True
    assert duplicate["status"] == "UPDATED_CURRENT_BAR"

    next_minute = opened + timedelta(minutes=15, seconds=5)
    finalized = _ingest_trusted_ltp_tick(
        buffer=buffer,
        symbol="NIFTY",
        price=25015.0,
        volume=None,
        ltp_source="live",
        ltp_ts_epoch=next_minute.timestamp(),
        cycle_cutoff=next_minute,
        market_open=True,
        max_ltp_age_sec=8.0,
        provenance=provenance,
    )
    assert finalized["accepted"] is True

    before_attack = store.get_bars(
        "NIFTY", as_of=opened + timedelta(minutes=16), timeframe="1m"
    )
    assert len(before_attack) == 15
    assert before_attack[-1]["close"] == 25014.0

    late_time = opened + timedelta(minutes=6, seconds=30)
    late = buffer.update_tick(
        "NIFTY", 99999.0, ts=late_time, provenance=provenance
    )
    assert late["accepted"] is False
    assert late["status"] == "REJECTED_LATE_BUCKET"

    reopened = MarketSessionStore(db_path=db_path, report_root=report_root)
    cutoff = opened + timedelta(minutes=16)
    one_minute = reopened.get_bars("NIFTY", as_of=cutoff, timeframe="1m")
    five_minute = reopened.get_bars("NIFTY", as_of=cutoff, timeframe="5m")
    fifteen_minute = reopened.get_bars("NIFTY", as_of=cutoff, timeframe="15m")
    assert len(one_minute) == 15
    assert len(five_minute) == 3
    assert len(fifteen_minute) == 1
    assert [row["close"] for row in one_minute] == [25000.0 + i for i in range(15)]
    assert reopened.verify_integrity("2026-09-07", ["NIFTY"])["status"] == "PASS"


def test_absent_tick_volume_stays_unknown_through_durable_restart(tmp_path, monkeypatch):
    db_path = tmp_path / "volume-authority.sqlite"
    report_root = tmp_path / "volume-reports"
    store = MarketSessionStore(db_path=db_path, report_root=report_root)
    previous_store = getattr(ohlc_module.ohlc_buffer, "_session_store", None)
    monkeypatch.setattr(ohlc_module.ohlc_buffer, "_session_store", previous_store, raising=False)
    monkeypatch.setattr(contract, "market_session_store", store)
    monkeypatch.setattr(contract, "_INSTALLED", False)
    monkeypatch.setattr(contract, "_INSTALL_STATUS", {})
    assert contract.install()["status"] == "PERSISTENCE_READY"
    buffer = ohlc_module.OhlcBuffer(session_store=store)

    opened = datetime(2026, 9, 7, 9, 15, 5, tzinfo=IST)
    common = {
        "buffer": buffer,
        "ltp_source": "live",
        "market_open": True,
        "max_ltp_age_sec": 8.0,
        "provenance": {
            "live_feed_session_id": "volume-authority-test",
            "reconnect_generation": 1,
            "historical_seed": False,
            "replay_fixture": False,
            "non_live_fallback": False,
            "recovered_synthetic": False,
        },
    }

    missing = _ingest_trusted_ltp_tick(
        **common,
        symbol="UNKNOWNVOLUME",
        price=25000.0,
        volume=None,
        ltp_ts_epoch=opened.timestamp(),
        cycle_cutoff=opened,
    )
    assert missing["accepted"] is True
    first_bar = buffer.get_bars("UNKNOWNVOLUME")[0]
    assert first_bar["volume"] is None
    assert first_bar["bar_provenance"]["volume_observation_complete"] is False

    next_minute = opened + timedelta(minutes=1)
    finalized = _ingest_trusted_ltp_tick(
        **common,
        symbol="UNKNOWNVOLUME",
        price=25001.0,
        volume=None,
        ltp_ts_epoch=next_minute.timestamp(),
        cycle_cutoff=next_minute,
    )
    assert finalized["accepted"] is True

    explicit_zero = _ingest_trusted_ltp_tick(
        **common,
        symbol="OBSERVEDZERO",
        price=25000.0,
        volume=0.0,
        ltp_ts_epoch=opened.timestamp(),
        cycle_cutoff=opened,
    )
    assert explicit_zero["accepted"] is True
    zero_bar = buffer.get_bars("OBSERVEDZERO")[0]
    assert zero_bar["volume"] == 0.0
    assert zero_bar["bar_provenance"]["volume_observation_complete"] is True
    _ingest_trusted_ltp_tick(
        **common,
        symbol="OBSERVEDZERO",
        price=25001.0,
        volume=0.0,
        ltp_ts_epoch=next_minute.timestamp(),
        cycle_cutoff=next_minute,
    )

    invalid_volumes = (float("nan"), float("inf"), -1.0, "not-a-volume")
    for index, invalid_volume in enumerate(invalid_volumes):
        symbol = f"INVALIDVOLUME{index}"
        invalid = _ingest_trusted_ltp_tick(
            **common,
            symbol=symbol,
            price=25000.0,
            volume=invalid_volume,
            ltp_ts_epoch=opened.timestamp(),
            cycle_cutoff=opened,
        )
        assert invalid["accepted"] is True
        invalid_bar = buffer.get_bars(symbol)[0]
        assert invalid_bar["volume"] is None
        assert invalid_bar["bar_provenance"]["volume_observation_complete"] is False
        _ingest_trusted_ltp_tick(
            **common,
            symbol=symbol,
            price=25001.0,
            volume=None,
            ltp_ts_epoch=next_minute.timestamp(),
            cycle_cutoff=next_minute,
        )

    reopened = MarketSessionStore(db_path=db_path, report_root=report_root)
    cutoff = opened + timedelta(minutes=1)
    missing_row = reopened.get_bars("UNKNOWNVOLUME", as_of=cutoff, timeframe="1m")[0]
    zero_row = reopened.get_bars("OBSERVEDZERO", as_of=cutoff, timeframe="1m")[0]
    assert missing_row["volume"] is None
    assert missing_row["provenance"]["volume_observation_complete"] is False
    assert zero_row["volume"] == 0.0
    assert zero_row["provenance"]["volume_observation_complete"] is True
    for index in range(len(invalid_volumes)):
        symbol = f"INVALIDVOLUME{index}"
        row = reopened.get_bars(symbol, as_of=cutoff, timeframe="1m")[0]
        assert row["volume"] is None
        assert row["provenance"]["volume_observation_complete"] is False
    assert reopened.verify_integrity(
        "2026-09-07", ["UNKNOWNVOLUME", "OBSERVEDZERO"] +
        [f"INVALIDVOLUME{index}" for index in range(len(invalid_volumes))]
    )["status"] == "PASS"


def test_same_process_session_rollover_excludes_prior_date_bars_from_runtime_view(tmp_path, monkeypatch):
    store = MarketSessionStore(
        db_path=tmp_path / "session-rollover.sqlite",
        report_root=tmp_path / "session-rollover-reports",
    )
    monkeypatch.setattr(contract, "market_session_store", store)
    monkeypatch.setattr(contract, "_INSTALLED", False)
    monkeypatch.setattr(contract, "_INSTALL_STATUS", {})
    assert contract.install()["status"] == "PERSISTENCE_READY"

    symbol = "ISSUE9ROLLOVER"
    buffer = ohlc_module.OhlcBuffer(session_store=store)
    prior_open = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    current_open = datetime(2026, 9, 8, 9, 15, tzinfo=IST)
    provenance = {
        "source_type": "deterministic_test",
        "live_feed_session_id": "issue9-same-process-rollover",
        "replay_fixture": False,
        "historical_seed": False,
        "non_live_fallback": False,
        "recovered_synthetic": False,
    }

    for offset in (0, 1, 2):
        result = buffer.update_tick(
            symbol,
            25000.0 + offset,
            ts=prior_open + timedelta(minutes=offset),
            provenance=provenance,
        )
        assert result["accepted"] is True
    assert len(
        store.get_bars(
            symbol,
            as_of=prior_open + timedelta(minutes=3),
            timeframe="1m",
            session_date="2026-09-07",
        )
    ) == 2

    for offset in (0, 1):
        result = buffer.update_tick(
            symbol,
            25100.0 + offset,
            ts=current_open + timedelta(minutes=offset),
            provenance=provenance,
        )
        assert result["accepted"] is True

    completed = buffer.get_completed_bars(
        symbol,
        as_of=current_open + timedelta(minutes=1),
    )
    assert [bar["ts"] for bar in completed] == [current_open]

    prior_session = store.get_bars(
        symbol,
        as_of=prior_open + timedelta(minutes=3),
        timeframe="1m",
        session_date="2026-09-07",
    )
    assert [bar["ts"] for bar in prior_session] == [
        prior_open,
        prior_open + timedelta(minutes=1),
    ]


@pytest.mark.parametrize(
    ("bar_ts", "as_of", "expected"),
    [
        (
            datetime(2026, 9, 7, 18, 30, tzinfo=ZoneInfo("UTC")),
            datetime(2026, 9, 8, 0, 15, tzinfo=ZoneInfo("UTC")),
            True,
        ),
        (
            datetime(2026, 9, 8, 18, 30, tzinfo=ZoneInfo("UTC")),
            datetime(2026, 9, 8, 0, 15, tzinfo=ZoneInfo("UTC")),
            False,
        ),
        (
            datetime(2026, 9, 8, 9, 15),
            datetime(2026, 9, 8, 10, 0, tzinfo=IST),
            True,
        ),
    ],
    ids=["aware-utc-same-ist-date", "aware-utc-next-ist-date", "naive-is-ist"],
)
def test_runtime_session_date_filter_uses_ist_calendar_date(bar_ts, as_of, expected):
    assert contract._is_same_ist_session_date({"ts": bar_ts}, as_of) is expected
