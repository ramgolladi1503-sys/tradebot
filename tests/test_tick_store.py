import time

import pytest

from core import tick_store


def _setup_isolated_tick_store(monkeypatch, tmp_path):
    db_path = tmp_path / "ticks.db"
    monkeypatch.setattr(tick_store.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    tick_store._LAST_TICK_BY_TOKEN.clear()
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
    assert last_tick["source"] in {"memory", "db"}

    ltp, ts_epoch = tick_store.get_ltp(token)
    assert isinstance(ltp, float)
    assert isinstance(ts_epoch, float)

    age_sec = tick_store.get_age_sec(token)
    assert isinstance(age_sec, float)
    assert age_sec >= 0.0
    assert age_sec < 5.0


def test_get_last_tick_db_fallback_when_memory_missing(monkeypatch, tmp_path):
    _setup_isolated_tick_store(monkeypatch, tmp_path)
    token = 999001
    price = 222.5

    ok = tick_store.insert_tick(time.time(), token, price, 1, 1)
    assert ok is True
    tick_store._LAST_TICK_BY_TOKEN.pop(token, None)

    last_tick = tick_store.get_last_tick(token, allow_db=True)
    assert isinstance(last_tick, dict)
    assert last_tick["source"] == "db"
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
