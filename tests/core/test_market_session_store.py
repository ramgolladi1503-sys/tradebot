import json
import sqlite3
import subprocess
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.market_session_store import MarketSessionStore, SessionMemoryConflict, _normalize

IST = ZoneInfo("Asia/Kolkata")


def _bar(ts, price, *, source="deterministic_test"):
    return {
        "ts": ts,
        "open": float(price),
        "high": float(price) + 1.0,
        "low": float(price) - 1.0,
        "close": float(price) + 0.5,
        "volume": 10.0,
        "bar_provenance": {"source_type": source},
    }


def _persist(store, symbol, bar, *, completed_as_of=None):
    cutoff = completed_as_of or (bar["ts"] + timedelta(minutes=1))
    return store.persist_completed_bar(symbol, bar, completed_as_of=cutoff)


def test_session_store_derives_only_complete_timeframes_and_builds_context(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    for idx in range(15):
        assert _persist(store, "NIFTY", _bar(start + timedelta(minutes=idx), 25000 + idx))["persisted"]

    as_of = start + timedelta(minutes=15)
    assert len(store.get_bars("NIFTY", as_of=as_of, timeframe="1m")) == 15
    assert len(store.get_bars("NIFTY", as_of=as_of, timeframe="5m")) == 3
    assert len(store.get_bars("NIFTY", as_of=as_of, timeframe="15m")) == 1
    assert len(store.get_bars("NIFTY", as_of=start + timedelta(minutes=14), timeframe="15m")) == 0

    ctx = store.build_context("NIFTY", as_of=as_of)
    assert ctx["authoritative"] is True
    assert ctx["coverage_pct"] == 100.0
    assert ctx["missing_1m_bars"] == 0
    assert ctx["bars"]["5m"] == 3
    assert ctx["bars"]["15m"] == 1
    assert ctx["authoritative_up_to_ist"].startswith("2026-09-07T09:29:00")


def test_persisted_market_memory_is_symbol_scoped_complete_and_freshness_is_external(tmp_path):
    db_path = tmp_path / "session.sqlite"
    report_root = tmp_path / "reports"
    store = MarketSessionStore(db_path=db_path, report_root=report_root)
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    for idx in range(20):
        _persist(store, "NIFTY", _bar(start + timedelta(minutes=idx), 25000 + idx))
        _persist(store, "BANKNIFTY", _bar(start + timedelta(minutes=idx), 50000 + idx))

    reopened = MarketSessionStore(db_path=db_path, report_root=report_root)
    snapshot = reopened.get_persisted_market_memory(
        "BANKNIFTY", as_of_timestamp=start + timedelta(minutes=20),
        freshness_watermark=0.0, trace_id="persisted-memory-test",
    )
    assert snapshot.symbol == "BANKNIFTY"
    assert snapshot.rolling_1m_bars_count == 20
    assert snapshot.freshness_watermark == 0.0
    assert snapshot.persistence_watermark == 1.0
    assert snapshot.trace_id == "persisted-memory-test"
    assert snapshot.current_price == 50019.5

    with pytest.raises(ValueError, match="market_memory_session_history_incomplete"):
        reopened.get_persisted_market_memory(
            "NIFTY", as_of_timestamp=start + timedelta(minutes=21),
            freshness_watermark=1.0,
        )

    with pytest.raises(ValueError, match="memory_store_empty"):
        reopened.get_persisted_market_memory(
            "FINNIFTY", as_of_timestamp=start + timedelta(minutes=20),
            freshness_watermark=1.0,
        )

    with pytest.raises(ValueError, match="memory_store_empty"):
        reopened.get_persisted_market_memory(
            "NIFTY", as_of_timestamp=start + timedelta(days=1),
            freshness_watermark=1.0,
        )


def test_persisted_market_memory_rejects_in_session_gap(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    for idx in range(20):
        if idx != 7:
            _persist(store, "NIFTY", _bar(start + timedelta(minutes=idx), 25000 + idx))

    with pytest.raises(ValueError, match="market_memory_minute_gap"):
        store.get_persisted_market_memory(
            "NIFTY", as_of_timestamp=start + timedelta(minutes=20),
            freshness_watermark=1.0,
        )


def test_session_store_rejects_mutation_of_completed_bar(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    ts = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    first = _bar(ts, 25000)
    assert _persist(store, "NIFTY", first)["status"] == "INSERTED"
    assert _persist(store, "NIFTY", first)["status"] == "EXISTS"

    changed = dict(first)
    changed["close"] = 25005.0
    changed["high"] = 25006.0
    with pytest.raises(SessionMemoryConflict):
        _persist(store, "NIFTY", changed)


def test_missing_minute_invalidates_derived_bucket_and_is_reported(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    for idx in (0, 1, 3, 4, 5, 6, 7, 8, 9):
        _persist(store, "NIFTY", _bar(start + timedelta(minutes=idx), 25000 + idx))

    as_of = start + timedelta(minutes=10)
    derived = store.get_bars("NIFTY", as_of=as_of, timeframe="5m")
    assert len(derived) == 1
    assert derived[0]["ts"].hour == 9 and derived[0]["ts"].minute == 20
    ctx = store.build_context("NIFTY", as_of=as_of)
    assert ctx["missing_1m_bars"] == 1
    assert ctx["coverage_pct"] == 90.0


def test_store_reopens_with_same_durable_history_and_seal_verifies(tmp_path):
    db_path = tmp_path / "session.sqlite"
    report_root = tmp_path / "reports"
    store = MarketSessionStore(db_path=db_path, report_root=report_root)
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    for idx in range(10):
        _persist(store, "NIFTY", _bar(start + timedelta(minutes=idx), 25000 + idx))

    reopened = MarketSessionStore(db_path=db_path, report_root=report_root)
    as_of = start + timedelta(minutes=10)
    assert len(reopened.get_bars("NIFTY", as_of=as_of, timeframe="1m")) == 10
    five_minute = reopened.get_bars("NIFTY", as_of=as_of, timeframe="5m")
    assert len(five_minute) == 2
    assert [row["ts"] for row in five_minute] == [start, start + timedelta(minutes=5)]
    assert five_minute[0]["open"] == 25000.0
    assert five_minute[0]["close"] == 25004.5
    integrity = reopened.verify_integrity("2026-09-07", ["NIFTY"])
    assert integrity["status"] == "PASS"
    sealed = reopened.seal_session("2026-09-07", ["NIFTY"])
    assert sealed["status"] == "PASS"
    assert all((report_root / "2026-09-07" / f"bars_{tf}.jsonl").exists() for tf in ("1m", "5m", "15m", "30m", "60m"))
    assert reopened.verify_seal("2026-09-07")["status"] == "PASS"


def test_store_rejects_bar_before_event_time_completion(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    ts = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    result = store.persist_completed_bar(
        "NIFTY", _bar(ts, 25000), completed_as_of=ts + timedelta(seconds=59)
    )

    assert result["status"] == "SKIPPED_INCOMPLETE"
    assert result["persisted"] is False
    assert store.get_bars("NIFTY", as_of=ts + timedelta(minutes=1), timeframe="1m") == []

    cross_session = store.persist_completed_bar(
        "NIFTY", _bar(ts, 25000), completed_as_of=ts + timedelta(days=1)
    )
    assert cross_session["status"] == "SKIPPED_CROSS_SESSION_CUTOFF"
    assert cross_session["persisted"] is False


def test_identical_concurrent_bar_writes_are_idempotent(tmp_path):
    db_path = tmp_path / "session.sqlite"
    report_root = tmp_path / "reports"
    writers = [
        MarketSessionStore(db_path=db_path, report_root=report_root),
        MarketSessionStore(db_path=db_path, report_root=report_root),
    ]
    ts = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    bar = _bar(ts, 25000)
    cutoff = ts + timedelta(minutes=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda writer: writer.persist_completed_bar("NIFTY", bar, completed_as_of=cutoff),
            writers,
        ))

    assert sorted(result["status"] for result in results) == ["EXISTS", "INSERTED"]
    assert all(result["persisted"] is True for result in results)
    assert len(writers[0].get_bars("NIFTY", as_of=cutoff, timeframe="1m")) == 1


def test_aborted_sqlite_insert_leaves_no_valid_partial_bar(tmp_path):
    db_path = tmp_path / "session.sqlite"
    store = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    ts = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    with store._conn() as conn:
        conn.execute("""
            CREATE TRIGGER reject_bar_insert BEFORE INSERT ON market_session_bars
            BEGIN SELECT RAISE(ABORT, 'injected_write_failure'); END
        """)

    with pytest.raises(sqlite3.IntegrityError, match="injected_write_failure"):
        _persist(store, "NIFTY", _bar(ts, 25000))

    with store._conn() as conn:
        conn.execute("DROP TRIGGER reject_bar_insert")
    reopened = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    assert reopened.get_bars(
        "NIFTY", as_of=ts + timedelta(minutes=1), timeframe="1m"
    ) == []
    with reopened._conn() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_process_death_before_store_context_commit_rolls_back_insert(tmp_path):
    db_path = tmp_path / "crash-session.sqlite"
    report_root = tmp_path / "reports"
    child = textwrap.dedent(
        """
        import os
        import sys
        from contextlib import contextmanager
        from datetime import datetime, timedelta
        from pathlib import Path
        from zoneinfo import ZoneInfo

        from core.market_session_store import MarketSessionStore

        db_path = Path(sys.argv[1])
        report_root = Path(sys.argv[2])
        store = MarketSessionStore(db_path=db_path, report_root=report_root)
        original_conn = store._conn

        @contextmanager
        def terminate_before_context_commit():
            with original_conn() as conn:
                yield conn
                # The store's INSERT has completed, but its SQLite connection
                # context has not yet received __exit__ to commit the transaction.
                assert conn.execute(
                    "SELECT COUNT(*) FROM market_session_bars WHERE symbol='NIFTY'"
                ).fetchone()[0] == 1
                os._exit(73)

        store._conn = terminate_before_context_commit
        ts = datetime(2026, 9, 7, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
        store.persist_completed_bar(
            "NIFTY",
            {"ts": ts, "open": 25000.0, "high": 25001.0, "low": 24999.0,
             "close": 25000.5, "volume": 10.0,
             "bar_provenance": {"source_type": "deterministic_test"}},
            completed_as_of=ts + timedelta(minutes=1),
        )
        raise AssertionError("expected abrupt process exit after INSERT")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", child, str(db_path), str(report_root)],
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 73, result.stderr
    reopened = MarketSessionStore(db_path=db_path, report_root=report_root)
    ts = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    assert reopened.get_bars(
        "NIFTY", as_of=ts + timedelta(minutes=1), timeframe="1m"
    ) == []
    with reopened._conn() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_feature_snapshot_is_immutable(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    ts = datetime(2026, 9, 7, 10, 0, tzinfo=IST)
    assert store.persist_feature_snapshot("NIFTY", as_of=ts, payload={"regime": "TREND"})["status"] == "OK"
    with pytest.raises(SessionMemoryConflict):
        store.persist_feature_snapshot("NIFTY", as_of=ts, payload={"regime": "RANGE"})


def test_seal_is_immutable(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    ts = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    _persist(store, "NIFTY", _bar(ts, 25000))
    assert store.seal_session("2026-09-07", ["NIFTY"])["status"] == "PASS"
    with pytest.raises(SessionMemoryConflict):
        _persist(store, "NIFTY", _bar(ts + timedelta(minutes=1), 25001))
        store.seal_session("2026-09-07", ["NIFTY"])


def test_integrity_detects_deleted_minute_and_out_of_session_row(tmp_path):
    db_path = tmp_path / "session.sqlite"
    store = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    for idx in range(3):
        _persist(store, "NIFTY", _bar(start + timedelta(minutes=idx), 25000 + idx))
    with store._conn() as conn:
        conn.execute("DELETE FROM market_session_bars WHERE session_date=? AND symbol=? AND ts_epoch=?", ("2026-09-07", "NIFTY", (start + timedelta(minutes=1)).timestamp()))
    report = store.verify_integrity("2026-09-07", ["NIFTY"])
    assert report["status"] == "FAIL"
    assert any("minute_gap" in failure for failure in report["failures"])


def test_store_preserves_unknown_volume_through_restart(tmp_path):
    db_path = tmp_path / "session.sqlite"
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    bar = _bar(start, 25000)
    bar["volume"] = None
    writer = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    assert _persist(writer, "NIFTY", bar)["persisted"] is True

    reopened = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    rows = reopened.get_bars("NIFTY", as_of=start + timedelta(minutes=1), timeframe="1m")
    assert len(rows) == 1
    assert rows[0]["volume"] is None


def test_store_rejects_corrupt_persisted_bar_on_read(tmp_path):
    db_path = tmp_path / "session.sqlite"
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    store = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    _persist(store, "NIFTY", _bar(start, 25000))
    with store._conn() as conn:
        conn.execute(
            "UPDATE market_session_bars SET close=? WHERE session_date=? AND symbol=?",
            (25099.0, "2026-09-07", "NIFTY"),
        )
    reopened = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    with pytest.raises(SessionMemoryConflict, match="persisted_bar_(schema_invalid|hash_or_identity_mismatch)"):
        reopened.get_bars("NIFTY", as_of=start + timedelta(minutes=1), timeframe="1m")


@pytest.mark.parametrize("epoch_delta", [-60.0, 60.0], ids=["premature", "delayed"])
def test_store_rejects_tampered_epoch_even_when_row_hash_is_unchanged(tmp_path, epoch_delta):
    db_path = tmp_path / "session.sqlite"
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    writer = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    _persist(writer, "NIFTY", _bar(start, 25000))
    with writer._conn() as conn:
        conn.execute(
            "UPDATE market_session_bars SET ts_epoch=ts_epoch+? WHERE session_date=? AND symbol=?",
            (epoch_delta, "2026-09-07", "NIFTY"),
        )

    reopened = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    # Earlier tampering would otherwise make the incomplete 09:15 bar visible
    # before its 09:16 completion boundary. Both directions must fail before
    # the stored epoch can influence ordering or as-of filtering.
    with pytest.raises(SessionMemoryConflict, match="persisted_bar_timestamp_mismatch"):
        reopened.get_bars(
            "NIFTY", as_of=start + timedelta(seconds=30), timeframe="1m", session_date="2026-09-07"
        )

    integrity = reopened.verify_integrity("2026-09-07", ["NIFTY"])
    assert integrity["status"] == "FAIL"
    assert any("timestamp_epoch_mismatch:NIFTY:" in failure for failure in integrity["failures"])


def test_store_reports_malformed_persisted_epoch_as_corruption(tmp_path):
    db_path = tmp_path / "session.sqlite"
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    writer = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    _persist(writer, "NIFTY", _bar(start, 25000))
    with writer._conn() as conn:
        conn.execute(
            "UPDATE market_session_bars SET ts_epoch=? WHERE session_date=? AND symbol=?",
            ("not-an-epoch", "2026-09-07", "NIFTY"),
        )

    reopened = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    with pytest.raises(SessionMemoryConflict, match="persisted_bar_timestamp_invalid"):
        reopened.get_bars(
            "NIFTY", as_of=start + timedelta(minutes=1), timeframe="1m", session_date="2026-09-07"
        )

    integrity = reopened.verify_integrity("2026-09-07", ["NIFTY"])
    assert integrity["status"] == "FAIL"
    assert integrity["failures"] == [f"invalid_epoch:NIFTY:{start.isoformat()}"]


def test_store_migrates_legacy_nonnull_volume_schema_without_losing_rows(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    bar = _bar(start, 25000)
    normalized = _normalize("NIFTY", bar)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
      CREATE TABLE market_session_bars(
        session_date TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
        ts_epoch REAL NOT NULL, ts_ist TEXT NOT NULL, open REAL NOT NULL,
        high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL,
        provenance_json TEXT NOT NULL, row_hash TEXT NOT NULL, persisted_at_epoch REAL NOT NULL,
        PRIMARY KEY(session_date,symbol,timeframe,ts_epoch));
      CREATE INDEX idx_market_session_bars_lookup
        ON market_session_bars(session_date,symbol,timeframe,ts_epoch);
    """)
    conn.execute(
        "INSERT INTO market_session_bars VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (normalized["session_date"], normalized["symbol"], normalized["timeframe"],
         normalized["ts_epoch"], normalized["ts_ist"], normalized["open"], normalized["high"],
         normalized["low"], normalized["close"], normalized["volume"],
         json.dumps(normalized["provenance"], sort_keys=True, separators=(",", ":")),
         normalized["row_hash"], 1.0),
    )
    conn.commit()
    conn.close()

    migrated = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    rows = migrated.get_bars("NIFTY", as_of=start + timedelta(minutes=1), timeframe="1m")
    assert len(rows) == 1
    with migrated._conn() as conn:
        volume_column = next(row for row in conn.execute("PRAGMA table_info(market_session_bars)") if row["name"] == "volume")
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(market_session_bars)")}
    assert volume_column["notnull"] == 0
    assert "idx_market_session_bars_lookup" in indexes
