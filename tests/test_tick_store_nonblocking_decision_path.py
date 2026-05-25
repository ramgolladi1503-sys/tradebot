from core import tick_store


def _setup(monkeypatch, memory=None):
    monkeypatch.setattr(
        tick_store.cfg,
        "DISALLOW_MEMORY_TICK_SOURCE_FOR_DECISIONS",
        False,
        raising=False,
    )
    monkeypatch.setattr(tick_store, "_LAST_TICK_BY_TOKEN", memory or {}, raising=False)


def test_decision_path_get_ltp_skips_sqlite_when_memory_tick_missing(monkeypatch):
    _setup(monkeypatch)
    calls = []

    def db_lookup(token):
        calls.append(token)
        return {"ltp": 99.5, "ts_epoch": 1_700_000_001.0, "source": "sqlite"}

    monkeypatch.setattr(tick_store, "get_latest_tick_db", db_lookup)

    assert tick_store.get_ltp(12345, decision_path=True) == (None, None)
    assert calls == []


def test_decision_path_get_ltp_uses_memory_tick(monkeypatch):
    _setup(monkeypatch, {12345: {"ltp": 101.25, "ts_epoch": 1_700_000_000.0}})
    calls = []

    def db_lookup(token):
        calls.append(token)
        return {"ltp": 99.5, "ts_epoch": 1_700_000_001.0, "source": "sqlite"}

    monkeypatch.setattr(tick_store, "get_latest_tick_db", db_lookup)

    assert tick_store.get_ltp(12345, decision_path=True) == (101.25, 1_700_000_000.0)
    assert calls == []


def test_non_decision_get_ltp_keeps_sqlite_fallback(monkeypatch):
    _setup(monkeypatch)
    calls = []

    def db_lookup(token):
        calls.append(token)
        return {"ltp": 99.5, "ts_epoch": 1_700_000_001.0, "source": "sqlite"}

    monkeypatch.setattr(tick_store, "get_latest_tick_db", db_lookup)

    assert tick_store.get_ltp(12345) == (99.5, 1_700_000_001.0)
    assert calls == [12345]


def test_decision_path_get_ltp_allows_explicit_sqlite_opt_in(monkeypatch):
    _setup(monkeypatch)
    calls = []

    def db_lookup(token):
        calls.append(token)
        return {"ltp": 88.75, "ts_epoch": 1_700_000_002.0, "source": "sqlite"}

    monkeypatch.setattr(tick_store, "get_latest_tick_db", db_lookup)

    assert tick_store.get_ltp(12345, decision_path=True, allow_db=True) == (88.75, 1_700_000_002.0)
    assert calls == [12345]
