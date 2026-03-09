from __future__ import annotations

from datetime import datetime

import pytest

import core.kite_client as kite_client_module
from core.kite_client import KiteClient


class _BoomKite:
    def __init__(self, message: str):
        self.message = message
        self.calls = 0

    def historical_data(self, **kwargs):
        self.calls += 1
        raise RuntimeError(self.message)


def test_historical_data_suppresses_repeated_auth_failures(monkeypatch):
    client = KiteClient()
    logs: list[str] = []
    boom = _BoomKite("TokenException incorrect api_key/access_token")
    now = {"ts": 100.0}

    monkeypatch.setattr(client, "kite", boom)
    monkeypatch.setattr(client, "_log_atomic", lambda msg: logs.append(str(msg)))
    monkeypatch.setattr(kite_client_module.time, "time", lambda: now["ts"])

    with pytest.raises(RuntimeError):
        client.historical_data(
            256265,
            datetime(2026, 3, 9, 9, 15),
            datetime(2026, 3, 9, 9, 30),
            interval="5minute",
            _symbol="NIFTY",
            _exchange="NSE",
            _caller="unit_test_chart",
        )

    out = client.historical_data(
        256265,
        datetime(2026, 3, 9, 9, 15),
        datetime(2026, 3, 9, 9, 30),
        interval="5minute",
        _symbol="NIFTY",
        _exchange="NSE",
        _caller="unit_test_chart",
    )

    assert out == []
    assert boom.calls == 1
    assert any("[HIST_AUTH_COOLDOWN]" in line for line in logs)
    assert any("[HIST_SUPPRESSED]" in line and "caller=unit_test_chart" in line for line in logs)


def test_historical_data_does_not_suppress_non_auth_failures(monkeypatch):
    client = KiteClient()
    boom = _BoomKite("upstream_timeout")
    now = {"ts": 200.0}

    monkeypatch.setattr(client, "kite", boom)
    monkeypatch.setattr(kite_client_module.time, "time", lambda: now["ts"])

    with pytest.raises(RuntimeError):
        client.historical_data(256265, datetime(2026, 3, 9, 9, 15), datetime(2026, 3, 9, 9, 30), interval="5minute")
    with pytest.raises(RuntimeError):
        client.historical_data(256265, datetime(2026, 3, 9, 9, 15), datetime(2026, 3, 9, 9, 30), interval="5minute")

    assert boom.calls == 2
