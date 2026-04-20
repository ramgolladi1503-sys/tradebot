from __future__ import annotations

import sqlite3

import pytest

from config import config as cfg
import core.trade_store as trade_store


def test_insert_depth_snapshot_skips_after_lock_retries(monkeypatch):
    monkeypatch.setattr(trade_store, "init_db", lambda force=False: None)
    monkeypatch.setattr(trade_store, "_should_prune_depth_snapshots", lambda _ts: False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_DB_WRITE_RETRY_ATTEMPTS", 3, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_DB_WRITE_RETRY_BACKOFF_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_DB_LOCK_SKIP_ENABLE", True, raising=False)
    monkeypatch.setattr(trade_store.time, "sleep", lambda _s: None)

    attempts = {"count": 0}
    incidents = {"count": 0}

    def _fake_trigger(_payload):
        incidents["count"] += 1
        return "inc-test"

    monkeypatch.setattr(trade_store, "trigger_db_write_fail", _fake_trigger)

    def _fake_conn():
        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                _ = exc_type
                _ = exc
                _ = tb
                return False

            def execute(self, *_args, **_kwargs):
                attempts["count"] += 1
                raise sqlite3.OperationalError("database is locked")

        return _Ctx()

    monkeypatch.setattr(trade_store, "_conn", _fake_conn)

    written = trade_store.insert_depth_snapshot(
        "2026-04-17T00:00:00Z",
        12345,
        "{}",
        1776384000.0,
    )

    assert written is False
    assert attempts["count"] == 3
    assert incidents["count"] == 0


def test_insert_depth_snapshot_non_lock_error_triggers_incident(monkeypatch):
    monkeypatch.setattr(trade_store, "init_db", lambda force=False: None)
    monkeypatch.setattr(trade_store, "_should_prune_depth_snapshots", lambda _ts: False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_DB_WRITE_RETRY_ATTEMPTS", 3, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_DB_WRITE_RETRY_BACKOFF_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_DB_LOCK_SKIP_ENABLE", True, raising=False)

    attempts = {"count": 0}
    incidents = {"count": 0}

    def _fake_trigger(_payload):
        incidents["count"] += 1
        return "inc-test"

    monkeypatch.setattr(trade_store, "trigger_db_write_fail", _fake_trigger)

    def _fake_conn():
        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                _ = exc_type
                _ = exc
                _ = tb
                return False

            def execute(self, *_args, **_kwargs):
                attempts["count"] += 1
                raise sqlite3.OperationalError("disk I/O error")

        return _Ctx()

    monkeypatch.setattr(trade_store, "_conn", _fake_conn)

    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        trade_store.insert_depth_snapshot(
            "2026-04-17T00:00:00Z",
            12345,
            "{}",
            1776384000.0,
        )
    assert attempts["count"] == 1
    assert incidents["count"] == 1
