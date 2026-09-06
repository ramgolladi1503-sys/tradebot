from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.market_session_store import MarketSessionStore, SessionMemoryConflict

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


def test_session_store_derives_only_complete_timeframes_and_builds_context(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    for idx in range(15):
        assert store.persist_completed_bar("NIFTY", _bar(start + timedelta(minutes=idx), 25000 + idx))["persisted"]

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


def test_session_store_rejects_mutation_of_completed_bar(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    ts = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    first = _bar(ts, 25000)
    assert store.persist_completed_bar("NIFTY", first)["status"] == "INSERTED"
    assert store.persist_completed_bar("NIFTY", first)["status"] == "EXISTS"

    changed = dict(first)
    changed["close"] = 25005.0
    changed["high"] = 25006.0
    with pytest.raises(SessionMemoryConflict):
        store.persist_completed_bar("NIFTY", changed)


def test_missing_minute_invalidates_derived_bucket_and_is_reported(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    for idx in (0, 1, 3, 4, 5, 6, 7, 8, 9):
        store.persist_completed_bar("NIFTY", _bar(start + timedelta(minutes=idx), 25000 + idx))

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
        store.persist_completed_bar("NIFTY", _bar(start + timedelta(minutes=idx), 25000 + idx))

    reopened = MarketSessionStore(db_path=db_path, report_root=report_root)
    as_of = start + timedelta(minutes=10)
    assert len(reopened.get_bars("NIFTY", as_of=as_of, timeframe="1m")) == 10
    integrity = reopened.verify_integrity("2026-09-07", ["NIFTY"])
    assert integrity["status"] == "PASS"
    sealed = reopened.seal_session("2026-09-07", ["NIFTY"])
    assert sealed["status"] == "PASS"
    assert reopened.verify_seal("2026-09-07")["status"] == "PASS"


def test_feature_snapshot_is_immutable(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    ts = datetime(2026, 9, 7, 10, 0, tzinfo=IST)
    assert store.persist_feature_snapshot("NIFTY", as_of=ts, payload={"regime": "TREND"})["status"] == "OK"
    with pytest.raises(SessionMemoryConflict):
        store.persist_feature_snapshot("NIFTY", as_of=ts, payload={"regime": "RANGE"})


def test_seal_is_immutable(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    ts = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    store.persist_completed_bar("NIFTY", _bar(ts, 25000))
    assert store.seal_session("2026-09-07", ["NIFTY"])["status"] == "PASS"
    with pytest.raises(SessionMemoryConflict):
        store.persist_completed_bar("NIFTY", _bar(ts + timedelta(minutes=1), 25001))
        store.seal_session("2026-09-07", ["NIFTY"])
