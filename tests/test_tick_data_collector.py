import pytest
from datetime import date
from scripts import tick_data_collector

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
    import builtins
    from unittest.mock import mock_open

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

    m_open = mock_open()
    monkeypatch.setattr(builtins, "open", m_open)

    tick_data_collector.main()

    _len = len(connect_called)
    assert _len == 1
    assert connect_called[0] is False
