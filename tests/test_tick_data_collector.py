import pytest
from datetime import date
from scripts import tick_data_collector


class _FakeParquetWriter:
    def __init__(self, *, fail_write=False, write_started=None, release_write=None):
        self.fail_write = fail_write
        self.write_started = write_started
        self.release_write = release_write
        self.write_calls = 0
        self.close_calls = 0
        self.write_after_close = False

    def write_table(self, _table):
        self.write_calls += 1
        if self.close_calls:
            self.write_after_close = True
        if self.write_started:
            self.write_started.set()
        if self.release_write and not self.release_write.wait(timeout=3.0):
            raise TimeoutError("test writer release timed out")
        if self.fail_write:
            raise OSError("fixture EIO")

    def close(self):
        self.close_calls += 1


def _batch_writer(writer, *, batch_size=2):
    return tick_data_collector._SynchronizedParquetBatchWriter(
        writer,
        batch_size=batch_size,
        table_factory=lambda rows: list(rows),
    )


def test_parquet_writer_serializes_callback_write_with_shutdown():
    import threading

    write_started = threading.Event()
    release_write = threading.Event()
    close_started = threading.Event()
    raw_writer = _FakeParquetWriter(
        write_started=write_started,
        release_write=release_write,
    )
    writer = _batch_writer(raw_writer)
    write_thread = threading.Thread(target=lambda: writer.add([{"ts": 1}, {"ts": 2}]))
    write_thread.start()
    assert write_started.wait(timeout=1.0)

    close_result = []

    def close_writer():
        close_started.set()
        close_result.append(writer.close())

    close_thread = threading.Thread(target=close_writer)
    close_thread.start()
    assert close_started.wait(timeout=1.0)
    release_write.set()
    write_thread.join(timeout=2.0)
    close_thread.join(timeout=2.0)

    assert not write_thread.is_alive()
    assert not close_thread.is_alive()
    assert close_result == [True]
    assert raw_writer.write_calls == 1
    assert raw_writer.close_calls == 1
    assert raw_writer.write_after_close is False
    assert writer.add([{"ts": 3}]) is False
    assert writer.closed is True


def test_parquet_writer_stops_writing_after_terminal_io_failure(caplog):
    raw_writer = _FakeParquetWriter(fail_write=True)
    writer = _batch_writer(raw_writer)

    assert writer.add([{"ts": 1}, {"ts": 2}]) is False
    assert writer.failed is True
    assert writer.add([{"ts": 3}]) is False
    assert writer.close() is False

    assert raw_writer.write_calls == 1
    assert raw_writer.close_calls == 1
    assert raw_writer.write_after_close is False
    assert "fixture EIO" in caplog.text
    assert "Dropped 1 ticks after terminal parquet recording failure" in caplog.text

def test_get_target_tokens_resolves_all_indices_and_options(monkeypatch):
    # Mock kite_client methods
    def mock_ensure():
        pass
        
    def mock_instruments_cached(exchange):
        if exchange == "NSE":
            return [
                {
                    "name": "NIFTY 50",
                    "tradingsymbol": "NIFTY 50",
                    "instrument_token": 256265,
                    "instrument_type": "EQ",
                    "strike": 0.0,
                    "expiry": None
                },
                {
                    "name": "NIFTY BANK",
                    "tradingsymbol": "NIFTY BANK",
                    "instrument_token": 260105,
                    "instrument_type": "EQ",
                    "strike": 0.0,
                    "expiry": None
                },
                {
                    "name": "INDIA VIX",
                    "tradingsymbol": "INDIA VIX",
                    "instrument_token": 264969,
                    "instrument_type": "EQ",
                    "strike": 0.0,
                    "expiry": None
                }
            ]
        elif exchange == "BSE":
            return [
                {
                    "name": "SENSEX",
                    "tradingsymbol": "SENSEX",
                    "instrument_token": 265,
                    "instrument_type": "EQ",
                    "strike": 0.0,
                    "expiry": None
                }
            ]
        elif exchange == "NFO":
            return [
                {
                    "name": "NIFTY",
                    "tradingsymbol": "NIFTY26JUN24000CE",
                    "instrument_token": 100001,
                    "instrument_type": "CE",
                    "strike": 24000.0,
                    "expiry": date(2026, 6, 26)
                },
                {
                    "name": "BANKNIFTY",
                    "tradingsymbol": "BANKNIFTY26JUN58000PE",
                    "instrument_token": 100002,
                    "instrument_type": "PE",
                    "strike": 58000.0,
                    "expiry": date(2026, 6, 26)
                }
            ]
        elif exchange == "BFO":
            return [
                {
                    "name": "SENSEX",
                    "tradingsymbol": "SENSEX26JUN77000CE",
                    "instrument_token": 100003,
                    "instrument_type": "CE",
                    "strike": 77000.0,
                    "expiry": date(2026, 6, 26)
                }
            ]
        return []

    def mock_resolve_index_token(symbol):
        tokens = {
            "NIFTY": 256265,
            "BANKNIFTY": 260105,
            "SENSEX": 265,
            "INDIAVIX": 264969
        }
        return tokens.get(symbol.upper())

    def mock_ltp(symbols):
        return {
            "NSE:NIFTY 50": {"last_price": 24000.0},
            "NSE:NIFTY BANK": {"last_price": 58000.0},
            "BSE:SENSEX": {"last_price": 77000.0},
            "NSE:INDIA VIX": {"last_price": 13.0}
        }

    monkeypatch.setattr(tick_data_collector.kite_client, "ensure", mock_ensure)
    monkeypatch.setattr(tick_data_collector.kite_client, "instruments_cached", mock_instruments_cached)
    monkeypatch.setattr(tick_data_collector.kite_client, "resolve_index_token", mock_resolve_index_token)
    monkeypatch.setattr(tick_data_collector.kite_client, "ltp", mock_ltp)
    
    # Force today to match mock expiry date so options are resolved
    class MockDatetime:
        @classmethod
        def now(cls):
            class FakeNow:
                def date(self):
                    return date(2026, 6, 25)
            return FakeNow()
            
    monkeypatch.setattr(tick_data_collector, "datetime", MockDatetime)

    tokens = tick_data_collector.get_target_tokens()
    
    assert tokens[256265] == "NIFTY 50"
    assert tokens[260105] == "NIFTY BANK"
    assert tokens[265] == "SENSEX"
    assert tokens[264969] == "INDIA VIX"
    assert tokens[100001] == "NIFTY26JUN24000CE"
    assert tokens[100002] == "BANKNIFTY26JUN58000PE"
    assert tokens[100003] == "SENSEX26JUN77000CE"


def test_main_initialization(monkeypatch):
    import signal
    import sys
    from types import ModuleType, SimpleNamespace

    monkeypatch.setenv("KITE_API_KEY", "dummy_api_key")
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "dummy_access_token")
    monkeypatch.setattr(tick_data_collector, "get_target_tokens", lambda: {12345: "NIFTY 50"})
    monkeypatch.setattr(signal, "signal", lambda sig, handler: None)

    connect_called = []
    class MockKiteTicker:
        def __init__(self, api_key, access_token):
            assert api_key == "dummy_api_key"
            assert access_token == "dummy_access_token"
            self.on_ticks = None
            self.on_connect = None
            self.on_close = None
            self.on_error = None
            self.MODE_FULL = "full"

        def connect(self, threaded=False):
            connect_called.append(threaded)

    monkeypatch.setattr(tick_data_collector, "KiteTicker", MockKiteTicker)

    fake_pyarrow = ModuleType("pyarrow")
    fake_pyarrow.schema = lambda fields: fields
    fake_pyarrow.float64 = lambda: "float64"
    fake_pyarrow.int64 = lambda: "int64"
    fake_pyarrow.string = lambda: "string"
    fake_pyarrow.Table = SimpleNamespace(from_pandas=lambda frame, schema: (frame, schema))
    fake_parquet = ModuleType("pyarrow.parquet")
    fake_parquet.ParquetWriter = lambda *_args, **_kwargs: _FakeParquetWriter()
    fake_pyarrow.parquet = fake_parquet
    monkeypatch.setitem(sys.modules, "pyarrow", fake_pyarrow)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", fake_parquet)
    monkeypatch.setitem(sys.modules, "pandas", SimpleNamespace(DataFrame=lambda rows: list(rows)))

    tick_data_collector.main()

    _len = len(connect_called)
    assert _len == 1
    assert connect_called[0] is False
