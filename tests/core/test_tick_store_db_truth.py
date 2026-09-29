from __future__ import annotations

import time

from config import config as cfg
from core import freshness_sla, tick_store


def _setup_tick_db(monkeypatch, tmp_path):
    db_path = tmp_path / "ticks_truth.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "TICK_STORE_ASYNC_DB_WRITES", False, raising=False)
    tick_store._LAST_TICK_BY_TOKEN.clear()
    tick_store._LAST_TICK_EPOCH = None
    tick_store._INIT_DONE = False
    tick_store._SCHEMA_LOGGED = False
    freshness_sla._reset_cache_for_tests()
    return db_path


def test_get_latest_tick_db_returns_inserted_row(monkeypatch, tmp_path):
    _setup_tick_db(monkeypatch, tmp_path)
    now_epoch = float(time.time())
    token = 256265
    assert tick_store.insert_tick(ts=now_epoch, token=token, last_price=25001.25, volume=11, oi=7) is True

    row = tick_store.get_latest_tick_db(token)
    assert isinstance(row, dict)
    assert row["instrument_token"] == token
    assert row["source"] == "sqlite"
    assert float(row["ltp"]) == 25001.25
    assert abs(float(row["ts_epoch"]) - now_epoch) < 5.0


def test_tick_event_identity_survives_memory_and_sqlite_reads(monkeypatch, tmp_path):
    _setup_tick_db(monkeypatch, tmp_path)
    now_epoch = float(time.time())
    identity = {
        "timestamp_authority": "EXCHANGE_TIMESTAMP",
        "timestamp_source_field": "exchange_timestamp",
        "source_timestamp_epoch": now_epoch,
        "receive_timestamp_epoch": now_epoch + 0.25,
        "timestamp_fallback_used": False,
        "source_event_id": "feed-session:9:256265:abc123",
        "source_event_sha256": "a" * 64,
    }
    assert tick_store.insert_tick(ts=now_epoch, token=256265, last_price=25001.25, **identity)
    memory = tick_store.get_last_tick(256265, include_provenance=True)
    assert memory is not None
    assert {key: (memory.get("_provenance") or {}).get(key) for key in identity} == identity
    sqlite_row = tick_store.get_latest_tick_db(256265)
    assert sqlite_row is not None
    assert sqlite_row.get("source_event_id") is None  # SQLite remains the bounded 12-field legacy contract.


def test_latest_memory_tick_preserves_event_identity_for_equal_timestamps(monkeypatch, tmp_path):
    _setup_tick_db(monkeypatch, tmp_path)
    ts = float(time.time())
    assert tick_store.insert_tick(ts=ts, token=256265, last_price=1.0, source_event_id="first", source_event_sha256="1" * 64)
    assert tick_store.insert_tick(ts=ts, token=256265, last_price=2.0, source_event_id="second", source_event_sha256="2" * 64)
    row = tick_store.get_last_tick(256265, include_provenance=True)
    assert row["ltp"] == 2.0
    assert row["_provenance"]["source_event_id"] == "second"
    assert row["_provenance"]["source_event_sha256"] == "2" * 64


def test_get_max_tick_epoch_db_returns_correct_max(monkeypatch, tmp_path):
    _setup_tick_db(monkeypatch, tmp_path)
    now_epoch = float(time.time())
    assert tick_store.insert_tick(ts=now_epoch - 5.0, token=101, last_price=10.0, volume=1, oi=1) is True
    assert tick_store.insert_tick(ts=now_epoch - 2.0, token=102, last_price=20.0, volume=1, oi=1) is True
    assert tick_store.insert_tick(ts=now_epoch - 1.0, token=101, last_price=11.0, volume=1, oi=1) is True

    max_all = tick_store.get_max_tick_epoch_db()
    max_subset = tick_store.get_max_tick_epoch_db([102])
    assert max_all is not None
    assert max_subset is not None
    assert abs(float(max_all) - float(now_epoch - 1.0)) < 5.0
    assert abs(float(max_subset) - float(now_epoch - 2.0)) < 5.0


def test_get_last_tick_decision_path_forces_sqlite(monkeypatch, tmp_path):
    _setup_tick_db(monkeypatch, tmp_path)
    now_epoch = float(time.time())
    token = 333
    assert tick_store.insert_tick(ts=now_epoch - 4.0, token=token, last_price=55.0, volume=1, oi=1) is True

    # Corrupt/override memory cache to simulate process-local drift.
    tick_store._LAST_TICK_BY_TOKEN[token] = {"ltp": 999.0, "ts_epoch": now_epoch}
    monkeypatch.setattr(cfg, "DISALLOW_MEMORY_TICK_SOURCE_FOR_DECISIONS", True, raising=False)

    from_memory = tick_store.get_last_tick(token, allow_db=True, decision_path=False)
    from_sqlite = tick_store.get_last_tick(token, allow_db=True, decision_path=True)

    assert from_memory is not None and from_memory["source"] == "memory"
    assert float(from_memory["ltp"]) == 999.0
    assert from_sqlite is not None and from_sqlite["source"] == "sqlite"
    assert float(from_sqlite["ltp"]) == 55.0


def test_freshness_sla_never_uses_memory_source_when_disallowed(monkeypatch, tmp_path):
    _setup_tick_db(monkeypatch, tmp_path)
    now_epoch = float(time.time())
    token = 256265
    assert tick_store.insert_tick(ts=now_epoch - 2.0, token=token, last_price=24999.0, volume=1, oi=1) is True

    # Make memory path look newer; SLA should still ignore it when disallowed.
    tick_store._LAST_TICK_EPOCH = now_epoch
    monkeypatch.setattr(cfg, "DISALLOW_MEMORY_TICK_SOURCE_FOR_DECISIONS", True, raising=False)
    monkeypatch.setattr(freshness_sla, "is_market_open_ist", lambda: True)
    freshness_sla._reset_cache_for_tests()

    payload = freshness_sla.get_freshness_status(force=True)
    source = str((payload.get("ltp") or {}).get("source") or "")
    assert source != "tick_store_memory"


def test_freshness_status_scoped_shape_contains_sla_fields(monkeypatch, tmp_path):
    _setup_tick_db(monkeypatch, tmp_path)
    now_epoch = float(time.time())
    token = 777
    assert tick_store.insert_tick(ts=now_epoch - 1.0, token=token, last_price=123.4, volume=1, oi=1) is True

    monkeypatch.setattr(freshness_sla, "is_market_open_ist", lambda: True)
    freshness_sla._reset_cache_for_tests()
    payload = freshness_sla.get_freshness_status(symbol="NIFTY", tokens=[token], force=True)

    assert "sla_threshold_sec" in payload
    assert "max_tick_age_sec" in payload
    assert "stale_tokens" in payload
    assert isinstance(payload["stale_tokens"], list)
    assert payload["ok"] is True
