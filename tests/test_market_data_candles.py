from datetime import datetime, timedelta, timezone

from core import market_data


def test_get_candles_returns_empty_df_on_api_failure(monkeypatch):
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda symbol: 256265)
    monkeypatch.setattr(
        market_data.kite_client,
        "historical_data",
        lambda instrument_token, from_dt, to_dt, interval="minute": (_ for _ in ()).throw(RuntimeError("boom")),
    )

    out = market_data.get_candles(
        symbol="NIFTY",
        interval="5minute",
        start_ms=1_700_000_000_000,
        end_ms=1_700_000_300_000,
    )

    assert list(out.columns) == ["time_ms", "open", "high", "low", "close", "volume"]
    assert out.empty


def test_get_candles_returns_schema_with_required_columns(monkeypatch):
    candle_dt = datetime(2026, 2, 27, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    expected_ms = int(candle_dt.astimezone(timezone.utc).timestamp() * 1000.0)

    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda symbol: 256265)
    monkeypatch.setattr(
        market_data.kite_client,
        "historical_data",
        lambda instrument_token, from_dt, to_dt, interval="minute", **kwargs: [
            {
                "date": candle_dt,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1200,
            },
            {"date": "bad-row", "open": None},
        ],
    )

    out = market_data.get_candles(
        symbol="BANKNIFTY",
        interval="5minute",
        start_ms=1_700_000_000_000,
        end_ms=1_700_000_300_000,
    )

    assert list(out.columns) == ["time_ms", "open", "high", "low", "close", "volume"]
    assert len(out) == 1
    row = out.iloc[0].to_dict()
    assert int(row["time_ms"]) == expected_ms
    assert float(row["open"]) == 100.0
    assert float(row["high"]) == 101.0
    assert float(row["low"]) == 99.0
    assert float(row["close"]) == 100.5
    assert float(row["volume"]) == 1200.0


def test_get_candles_passes_historical_caller_context(monkeypatch):
    calls = []

    def _hist(instrument_token, from_dt, to_dt, interval="minute", **kwargs):
        calls.append(
            {
                "instrument_token": instrument_token,
                "interval": interval,
                "kwargs": dict(kwargs),
            }
        )
        return []

    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda symbol: 256265)
    monkeypatch.setattr(market_data.kite_client, "historical_data", _hist)

    out = market_data.get_candles(
        symbol="NIFTY",
        interval="5minute",
        start_ms=1_700_000_000_000,
        end_ms=1_700_000_300_000,
    )

    assert out.empty
    assert calls == [
        {
            "instrument_token": 256265,
            "interval": "5minute",
            "kwargs": {
                "_symbol": "NIFTY",
                "_exchange": "NSE",
                "_caller": "market_data_underlying_candles",
            },
        }
    ]
