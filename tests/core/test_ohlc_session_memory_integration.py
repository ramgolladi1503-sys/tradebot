from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.market_session_store import MarketSessionStore
from core.market_session_memory_contract import install as install_session_memory_contract
install_session_memory_contract()
from core.ohlc_buffer import OhlcBuffer

IST = ZoneInfo("Asia/Kolkata")


def _prov():
    return {
        "source_type": "deterministic_test",
        "live_feed_session_id": "cert-session",
        "feed_epoch": 1,
        "reconnect_generation": 0,
        "historical_seed": False,
        "replay_fixture": False,
        "non_live_fallback": False,
        "recovered_synthetic": False,
    }


def test_ohlc_buffer_write_through_and_restart_read_through(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    buffer = OhlcBuffer(session_store=store)
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)

    buffer.update_tick("NIFTY", 25000.0, ts=start, provenance=_prov())
    result = buffer.update_tick("NIFTY", 25010.0, ts=start + timedelta(minutes=1), provenance=_prov())
    assert result["session_memory_persisted"] is True
    assert result["session_memory_status"] in {"INSERTED", "EXISTS"}

    completed = buffer.get_completed_bars("NIFTY", as_of=start + timedelta(minutes=2))
    assert [row["ts"].minute for row in completed] == [15, 16]

    restarted = OhlcBuffer(session_store=MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports2"))
    recovered = restarted.get_completed_bars("NIFTY", as_of=start + timedelta(minutes=2))
    assert [row["ts"].minute for row in recovered] == [15, 16]
    ctx = restarted.get_session_context("NIFTY", as_of=start + timedelta(minutes=2))
    assert ctx["authoritative"] is True
    assert ctx["observed_1m_bars"] == 2
    assert ctx["coverage_pct"] == 100.0


def test_replay_and_untrusted_sources_do_not_pollute_durable_session_memory(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    buffer = OhlcBuffer(session_store=store)
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)

    replay = _prov()
    replay["source_type"] = "replay_fixture"
    replay["replay_fixture"] = True
    buffer.update_tick("NIFTY", 25000.0, ts=start, provenance=replay)
    result = buffer.update_tick("NIFTY", 25001.0, ts=start + timedelta(minutes=1), provenance=replay)
    assert result["session_memory_persisted"] is False
    assert result["session_memory_status"] == "SKIPPED_REPLAY_FIXTURE"
    assert store.get_bars("NIFTY", as_of=start + timedelta(minutes=2), timeframe="1m") == []


def test_contiguous_one_minute_historical_seed_can_backfill_current_session(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    buffer = OhlcBuffer(session_store=store)
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    seed = []
    for idx in range(5):
        px = 25000 + idx
        seed.append({"date": start + timedelta(minutes=idx), "open": px, "high": px + 1, "low": px - 1, "close": px + 0.5, "volume": 10})
    assert buffer.seed_bars("NIFTY", seed)["accepted"] is True
    buffer.get_completed_bars("NIFTY", as_of=start + timedelta(minutes=5))
    assert len(store.get_bars("NIFTY", as_of=start + timedelta(minutes=5), timeframe="1m")) == 5


def test_five_minute_historical_seed_is_not_mislabeled_as_one_minute_memory(tmp_path):
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    buffer = OhlcBuffer(session_store=store)
    start = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
    seed = []
    for idx in range(4):
        px = 25000 + idx
        seed.append({"date": start + timedelta(minutes=5 * idx), "open": px, "high": px + 1, "low": px - 1, "close": px + 0.5, "volume": 10})
    buffer.seed_bars("NIFTY", seed)
    buffer.get_completed_bars("NIFTY", as_of=start + timedelta(minutes=20))
    assert store.get_bars("NIFTY", as_of=start + timedelta(minutes=20), timeframe="1m") == []
