from datetime import timedelta
import json

from config import config as cfg
import core.market_data as market_data
from core.indicators_live import compute_indicators


def _build_hist_rows(count: int, base_price: float = 100.0):
    now = market_data.now_ist().replace(second=0, microsecond=0)
    rows = []
    for i in range(count):
        ts = now - timedelta(minutes=(count - i))
        px = base_price + (i * 0.2)
        rows.append(
            {
                "date": ts,
                "open": px - 0.1,
                "high": px + 0.2,
                "low": px - 0.2,
                "close": px,
                "volume": 100 + i,
            }
        )
    return rows


def test_warm_seed_from_historical_enables_indicator_compute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "KITE_USE_API", False, raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "OHLC_WARM_SEED_WINDOWS_MIN", "120,240", raising=False)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda symbol: 256265)
    monkeypatch.setattr(
        market_data.kite_client,
        "historical_data",
        lambda instrument_token, from_dt, to_dt, interval="minute": _build_hist_rows(40),
    )

    symbol = "NIFTY_WARMSEED_TEST"
    market_data.ohlc_buffer._bars.pop(symbol, None)
    market_data._INSUFFICIENT_OHLC_WARNED.clear()

    bars, seeded_ok, reason = market_data._warm_seed_ohlc_from_history(
        symbol=symbol,
        bars=[],
        min_bars=30,
    )
    assert seeded_ok is True
    assert reason is None
    assert len(bars) >= 30

    indicators = compute_indicators(bars)
    assert indicators["ok"] is True


def test_insufficient_ohlc_warning_logged_once_when_kite_unavailable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "KITE_USE_API", False, raising=False)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", None, raising=False)
    market_data._INSUFFICIENT_OHLC_WARNED.clear()

    for _ in range(2):
        bars, seeded_ok, reason = market_data._warm_seed_ohlc_from_history(
            symbol="NIFTY",
            bars=[],
            min_bars=30,
        )
        assert seeded_ok is False
        assert reason == "kite_api_unavailable"
        assert bars == []

    warn_path = tmp_path / "logs" / "market_data_warnings.jsonl"
    assert warn_path.exists()
    rows = [json.loads(line) for line in warn_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["warning"] == "insufficient OHLC bars"


def test_warm_seed_fallback_to_240m_window(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "OHLC_WARM_SEED_WINDOWS_MIN", "120,240", raising=False)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda symbol: 256265)

    calls = []

    def _hist(_token, from_dt, to_dt, interval="minute"):
        calls.append(int((to_dt - from_dt).total_seconds() // 60))
        if len(calls) == 1:
            return []
        return _build_hist_rows(40)

    monkeypatch.setattr(market_data.kite_client, "historical_data", _hist)

    bars, seeded_ok, reason = market_data._warm_seed_ohlc_from_history(
        symbol="NIFTY_WARMSEED_FALLBACK",
        bars=[],
        min_bars=30,
    )
    assert seeded_ok is True
    assert reason is None
    assert len(bars) >= 30
    assert calls == [120, 240]
