from datetime import timedelta
import json

import pytest
from config import config as cfg
import core.market_data as market_data
from core.indicators_live import compute_indicators
from core.option_liquidity_cache import clear_option_liquidity_cache, update_option_liquidity_cache


def _build_hist_rows(count: int, base_price: float = 100.0, step_minutes: int = 1):
    now = market_data.now_ist().replace(second=0, microsecond=0)
    rows = []
    for i in range(count):
        ts = now - timedelta(minutes=((count - i) * step_minutes))
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


class _DummyNewsCal:
    def get_shock(self):
        return {}


class _DummyNewsText:
    def encode(self):
        return {}


class _DummyCross:
    def update(self, *_args, **_kwargs):
        return {"features": {}, "data_quality": {}}


class _DummyRegimeModel:
    def predict(self, _features):
        return {
            "primary_regime": "TREND",
            "regime_probs": {"TREND": 0.95, "RANGE": 0.05},
            "regime_entropy": 0.2,
            "unstable_regime_flag": False,
        }


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
        lambda instrument_token, from_dt, to_dt, interval="minute", **kwargs: _build_hist_rows(40),
    )

    symbol = "NIFTY_WARMSEED_TEST"
    market_data.ohlc_buffer._bars.pop(symbol, None)
    market_data._INSUFFICIENT_OHLC_WARNED.clear()

    bars, seeded_ok, reason = market_data._warm_seed_ohlc_from_history(
            symbol=symbol,
            bars=[],
            min_bars=30,
            as_of=market_data.now_ist(),
    )
    assert seeded_ok is True
    assert reason is None
    bars_count = len(bars)
    assert bars_count >= 30

    indicators = compute_indicators(bars)
    assert indicators["ok"] is True


def test_fetch_live_market_data_seeds_empty_buffer_and_enables_indicators(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_SEED_FULLPATH"
    fixed_now = market_data.now_ist().replace(second=0, microsecond=0)

    monkeypatch.setattr(cfg, "SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", False, raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "OHLC_WARM_SEED_WINDOWS_MIN", "120,240", raising=False)
    monkeypatch.setattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False, raising=False)
    monkeypatch.setattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO", raising=False)

    market_data._DATA_CACHE.clear()
    market_data._OPEN_RANGE.clear()
    market_data._INSUFFICIENT_OHLC_WARNED.clear()
    market_data.ohlc_buffer._bars.pop(symbol, None)

    monkeypatch.setattr(market_data, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(market_data, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(market_data, "fetch_option_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(market_data, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(market_data, "now_utc_epoch", lambda: fixed_now.timestamp())

    def _fake_get_ltp(sym: str):
        market_data._DATA_CACHE.setdefault(sym, {})
        market_data._DATA_CACHE[sym]["ltp_source"] = "live"
        market_data._DATA_CACHE[sym]["ltp_ts_epoch"] = fixed_now.timestamp()
        return 25000.0

    monkeypatch.setattr(market_data, "get_ltp", _fake_get_ltp)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda _symbol: 256265)
    monkeypatch.setattr(
        market_data.kite_client,
        "historical_data",
        lambda instrument_token, from_dt, to_dt, interval="minute", **kwargs: _build_hist_rows(40, base_price=25000.0),
    )

    rows = market_data.fetch_live_market_data()
    snap = next(r for r in rows if r.get("instrument") == "OPT" and r.get("symbol") == symbol)
    assert snap["ohlc_seeded"] is True
    assert snap["ohlc_bars_count"] >= 30
    assert snap["indicators_ok"] is True
    bars = market_data.ohlc_buffer.get_completed_bars(symbol, as_of=fixed_now)
    expected = market_data.compute_indicators(
        bars,
        vwap_window=getattr(cfg, "VWAP_WINDOW", 20),
        atr_period=getattr(cfg, "ATR_PERIOD", 14),
        adx_period=getattr(cfg, "ADX_PERIOD", 14),
        vol_window=getattr(cfg, "VOL_WINDOW", 30),
        slope_window=getattr(cfg, "VWAP_SLOPE_WINDOW", 10),
    )
    assert expected["ok"] is True
    assert expected.get("rsi") is not None
    assert expected.get("ema") is not None
    assert snap.get("rsi") == pytest.approx(expected.get("rsi"), rel=1e-9, abs=1e-9)
    assert snap.get("ema") == pytest.approx(expected.get("ema"), rel=1e-9, abs=1e-9)
    assert isinstance(snap.get("indicator_last_update_epoch"), (int, float))
    assert isinstance(snap.get("indicators_age_sec"), (int, float))
    assert snap.get("regime_ts_source") == "CANONICAL_EVENT_TIME"
    assert snap.get("regime_ts")


def test_fetch_live_market_data_preserves_unknown_volume_as_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_UNKNOWN_VOLUME"
    fixed_now = market_data.now_ist().replace(second=0, microsecond=0)

    monkeypatch.setattr(cfg, "SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", False, raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 5, raising=False)
    monkeypatch.setattr(cfg, "SYSTEM_WARMUP_MIN_BARS", 5, raising=False)
    monkeypatch.setattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False, raising=False)
    monkeypatch.setattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO", raising=False)

    market_data._DATA_CACHE.clear()
    market_data._OPEN_RANGE.clear()
    market_data._INSUFFICIENT_OHLC_WARNED.clear()
    market_data.ohlc_buffer._bars.pop(symbol, None)
    market_data.ohlc_buffer.seed_bars(symbol, _build_hist_rows(10, base_price=25000.0))

    monkeypatch.setattr(market_data, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(market_data, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(market_data, "fetch_option_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(market_data, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(market_data, "now_utc_epoch", lambda: fixed_now.timestamp())
    monkeypatch.setattr(
        market_data,
        "compute_indicators",
        lambda bars, **kwargs: {
            "ok": True,
            "vwap": 25000.0,
            "atr": 100.0,
            "adx": 25.0,
            "vol_z": 0.1,
            "vwap_slope": 0.2,
            "last_ts": fixed_now,
        },
    )

    def _fake_get_ltp(sym: str):
        market_data._DATA_CACHE.setdefault(sym, {})
        market_data._DATA_CACHE[sym]["ltp_source"] = "live"
        market_data._DATA_CACHE[sym]["ltp_ts_epoch"] = fixed_now.timestamp()
        return 25000.0

    monkeypatch.setattr(market_data, "get_ltp", _fake_get_ltp)

    rows = market_data.fetch_live_market_data()
    snap = next(r for r in rows if r.get("instrument") == "OPT" and r.get("symbol") == symbol)
    assert snap["volume"] is None
    assert market_data.ohlc_buffer.get_bars(symbol)[-1]["volume"] == 0


def test_hydrate_live_option_chain_liquidity_preserves_cached_values_for_incomplete_update() -> None:
    clear_option_liquidity_cache()
    try:
        update_option_liquidity_cache(
            [
                {
                    "symbol": "NIFTY",
                    "expiry": "2026-03-12",
                    "strike": 22500,
                    "type": "CE",
                    "instrument_token": 991111,
                    "volume": 6200,
                    "current_volume": 6200,
                    "oi": 30500,
                    "oi_change": 180,
                    "snapshot_ts_epoch": 100.0,
                }
            ],
            source="unit_cache",
        )
        rows = market_data._hydrate_live_option_chain_liquidity(
            "NIFTY",
            [
                {
                    "symbol": "NIFTY",
                    "expiry": "2026-03-12",
                    "strike": 22500,
                    "type": "CE",
                    "instrument_token": 991111,
                    "quote_age_sec": 0.8,
                }
            ],
            chain_source="live",
            now_epoch=200.0,
        )

        assert rows[0]["volume"] == 6200.0
        assert rows[0]["current_volume"] == 6200.0
        assert rows[0]["oi"] == 30500.0
        assert rows[0]["oi_change"] == 180.0
        assert rows[0]["liquidity_source"] == "unit_cache"
    finally:
        clear_option_liquidity_cache()


def test_fetch_live_market_data_empty_buffer_sets_indicators_false(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_EMPTY_BUFFER"
    fixed_now = market_data.now_ist().replace(second=0, microsecond=0)

    monkeypatch.setattr(cfg, "SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", False, raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False, raising=False)
    monkeypatch.setattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO", raising=False)
    monkeypatch.setattr(cfg, "FORCE_REGIME", "", raising=False)

    market_data._DATA_CACHE.clear()
    market_data._OPEN_RANGE.clear()
    market_data._INSUFFICIENT_OHLC_WARNED.clear()
    market_data.ohlc_buffer._bars.pop(symbol, None)

    monkeypatch.setattr(market_data, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(market_data, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(market_data, "fetch_option_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(market_data, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(market_data, "now_utc_epoch", lambda: fixed_now.timestamp())
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", None, raising=False)

    def _fake_get_ltp(sym: str):
        market_data._DATA_CACHE.setdefault(sym, {})
        market_data._DATA_CACHE[sym]["ltp_source"] = "live"
        market_data._DATA_CACHE[sym]["ltp_ts_epoch"] = fixed_now.timestamp()
        return 25000.0

    monkeypatch.setattr(market_data, "get_ltp", _fake_get_ltp)

    rows = market_data.fetch_live_market_data()
    snap = next(r for r in rows if r.get("instrument") == "OPT" and r.get("symbol") == symbol)
    assert snap["indicators_ok"] is False
    assert int(snap["ohlc_bars_count"]) < int(getattr(cfg, "OHLC_MIN_BARS", 30))
    reasons = set(snap.get("indicator_missing_inputs") or [])
    assert "HIST_FETCH_FAILED" in reasons
    assert isinstance(snap.get("indicator_last_update_epoch"), (int, float))
    assert isinstance(snap.get("indicators_age_sec"), (int, float))
    assert snap.get("regime") == "UNKNOWN"
    regime_reasons = set(snap.get("regime_reasons") or [])
    assert "warmup_incomplete" in regime_reasons


def test_insufficient_ohlc_warning_logged_once_when_kite_unavailable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_API", False, raising=False)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", None, raising=False)
    market_data._INSUFFICIENT_OHLC_WARNED.clear()

    for _ in range(2):
        bars, seeded_ok, reason = market_data._warm_seed_ohlc_from_history(
            symbol="NIFTY",
            bars=[],
            min_bars=30,
            as_of=market_data.now_ist(),
        )
        assert seeded_ok is False
        assert reason == "HIST_FETCH_FAILED"
        assert bars == []

    warn_path = tmp_path / "logs" / "market_data_warnings.jsonl"
    assert warn_path.exists()
    rows = [json.loads(line) for line in warn_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    row_count = len(rows)
    assert row_count == 1
    assert rows[0]["warning"] == "insufficient OHLC bars"
    assert rows[0]["reason"] == "HIST_FETCH_FAILED"
    assert rows[0]["reason_code"] == "HIST_FETCH_FAILED"
    assert rows[0]["detail"] == "kite_api_unavailable"


def test_warm_seed_fallback_to_240m_window(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "OHLC_WARM_SEED_WINDOWS_MIN", "120,240", raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_FETCH_RETRIES", 1, raising=False)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda symbol: 256265)

    calls = []

    def _hist(_token, from_dt, to_dt, interval="minute", **kwargs):
        calls.append(int((to_dt - from_dt).total_seconds() // 60))
        if len(calls) == 1:
            return []
        return _build_hist_rows(40)

    monkeypatch.setattr(market_data.kite_client, "historical_data", _hist)

    bars, seeded_ok, reason = market_data._warm_seed_ohlc_from_history(
            symbol="NIFTY_WARMSEED_FALLBACK",
            bars=[],
            min_bars=30,
            as_of=market_data.now_ist(),
    )
    assert seeded_ok is True
    assert reason is None
    bars_count = len(bars)
    assert bars_count >= 30
    assert calls == [120, 240]


def test_startup_seed_populates_buffer_and_sets_indicator_timestamp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_STARTUP_SEED"

    monkeypatch.setattr(cfg, "SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "SYSTEM_WARMUP_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "OHLC_WARM_SEED_WINDOWS_MIN", "120,240", raising=False)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda _symbol: 256265)
    monkeypatch.setattr(
        market_data.kite_client,
        "historical_data",
        lambda instrument_token, from_dt, to_dt, interval="minute", **kwargs: _build_hist_rows(60, base_price=25200.0),
    )

    market_data.ohlc_buffer._bars.pop(symbol, None)
    market_data._INDICATOR_LAST_UPDATE_EPOCH.pop(symbol, None)

    rows = market_data.seed_ohlc_buffers_on_startup([symbol])
    row_count = len(rows)
    assert row_count == 1
    row = rows[0]
    assert row["symbol"] == symbol
    assert row["seeded_bars_count"] >= 30
    assert row["indicators_ok_after_seed"] is True
    assert row["last_candle_ts"] is not None
    assert row["indicator_last_update_ts"] is not None
    assert isinstance(market_data._INDICATOR_LAST_UPDATE_EPOCH.get(symbol), (int, float))
    bars_count = len(market_data.ohlc_buffer.get_bars(symbol))
    assert bars_count >= 30


def test_startup_seed_uses_minute_contract_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_STARTUP_5M"
    calls = []

    monkeypatch.setattr(cfg, "SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "SYSTEM_WARMUP_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_INTERVAL", "minute", raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_TARGET_BARS", 200, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda _symbol: 256265)

    def _hist(_instrument_token, from_dt, to_dt, interval="minute", **kwargs):
        calls.append(interval)
        return _build_hist_rows(220, base_price=25200.0, step_minutes=1)

    monkeypatch.setattr(market_data.kite_client, "historical_data", _hist)
    market_data.ohlc_buffer._bars.pop(symbol, None)
    market_data._INDICATOR_LAST_UPDATE_EPOCH.pop(symbol, None)

    rows = market_data.seed_ohlc_buffers_on_startup([symbol])
    row_count = len(rows)
    assert row_count == 1
    row = rows[0]
    assert row["seed_interval"] == "minute"
    assert row["target_bars"] == 200
    assert row["seeded_bars_count"] >= 200
    assert row["warmup_ok"] is True
    assert row["indicators_ok_after_seed"] is True
    assert calls and all(interval == "minute" for interval in calls)


def test_minute_seed_does_not_treat_old_five_minute_open_as_current(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_INTERVAL_CONTRACT"
    fixed_now = market_data.now_ist().replace(hour=13, minute=0, second=13, microsecond=0)
    monkeypatch.setattr(market_data, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_INTERVAL", "minute", raising=False)
    monkeypatch.setattr(cfg, "MAX_CANDLE_AGE_SEC", 120, raising=False)

    calls = []
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda _symbol: 256265)

    def _hist(_token, _from_dt, _to_dt, interval="minute", **kwargs):
        calls.append(interval)
        return _build_hist_rows(40, base_price=25200.0, step_minutes=1)

    monkeypatch.setattr(market_data.kite_client, "historical_data", _hist)
    market_data.ohlc_buffer._bars.pop(symbol, None)
    bars, seeded_ok, reason = market_data._warm_seed_ohlc_from_history(
        symbol=symbol,
        bars=[],
        min_bars=30,
        as_of=fixed_now,
        interval="minute",
    )

    assert seeded_ok is True
    assert reason is None
    assert calls and all(interval == "minute" for interval in calls)
    latest = bars[-1]["ts"].timestamp()
    sanity = market_data.check_market_data_time_sanity(
        ltp_ts_epoch=fixed_now.timestamp(),
        candle_ts_epoch=latest,
        market_open=True,
        require_live_quotes=True,
        max_candle_age_sec=120,
        now_epoch=fixed_now.timestamp(),
    )
    assert sanity["candle_age_sec"] <= 120
    assert "CANDLE_STALE" not in sanity["reasons"]


def test_startup_seed_windows_include_calendar_lookback(monkeypatch):
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_LOOKBACK_DAYS", 7, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_LOOKBACK_MINUTES", 7 * 24 * 60, raising=False)

    windows = market_data._startup_seed_windows_minutes("5minute", 200)
    assert windows[0] == 1000
    assert max(windows) >= 10080


def test_startup_seed_uses_long_lookback_window_when_short_windows_empty(tmp_path, monkeypatch):
    pass


def test_startup_seed_respects_nested_runtime_context_payload(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_STARTUP_CTX"

    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "SYSTEM_WARMUP_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_INTERVAL", "5minute", raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_TARGET_BARS", 200, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda _symbol: 256265)
    monkeypatch.setattr(
        market_data.kite_client,
        "historical_data",
        lambda _instrument_token, _from_dt, _to_dt, interval="minute", **kwargs: _build_hist_rows(220, base_price=25200.0, step_minutes=5),
    )

    market_data.ohlc_buffer._bars.pop(symbol, None)
    market_data._INDICATOR_LAST_UPDATE_EPOCH.pop(symbol, None)

    rows = market_data.seed_ohlc_buffers_on_startup(
        [symbol],
        market_context={
            "market_context": {
                "execution_mode": "PAPER",
                "market_open": False,
            }
        },
    )
    row_count = len(rows)
    assert row_count == 1
    row = rows[0]
    assert row["warmup_ok"] is True
    assert row["seeded_bars_count"] >= 200
    assert row["market_context"]["mode"] == "PAPER"
    assert row["market_context"]["planning_only"] is True
    assert row["market_context"]["allow_stale_quotes"] is True


def test_startup_seed_hist_fetch_failed_reason_is_explicit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "BANKNIFTY_STARTUP_FAIL"

    monkeypatch.setattr(cfg, "SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "SYSTEM_WARMUP_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_INTERVAL", "5minute", raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_TARGET_BARS", 200, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda _symbol: 260105)
    monkeypatch.setattr(
        market_data.kite_client,
        "historical_data",
        lambda _instrument_token, _from_dt, _to_dt, interval="minute", **kwargs: [],
    )

    market_data.ohlc_buffer._bars.pop(symbol, None)
    market_data._INDICATOR_LAST_UPDATE_EPOCH.pop(symbol, None)
    rows = market_data.seed_ohlc_buffers_on_startup([symbol])
    row_count = len(rows)
    assert row_count == 1
    row = rows[0]
    assert row["seed_reason"] == "HIST_FETCH_FAILED"
    assert row["warmup_reason"] == "HIST_FETCH_FAILED"
    assert row["warmup_ok"] is False


def test_warm_seed_retries_before_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_WARMUP_RETRY"
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_FETCH_RETRIES", 3, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_RETRY_BACKOFF_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_MAX_BACKOFF_SEC", 0.0, raising=False)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda _symbol: 256265)

    calls = {"n": 0}

    def _hist(_token, _from_dt, _to_dt, interval="minute", **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient_hist_error")
        return _build_hist_rows(40, base_price=25100.0)

    monkeypatch.setattr(market_data.kite_client, "historical_data", _hist)
    market_data.ohlc_buffer._bars.pop(symbol, None)

    bars, seeded_ok, reason = market_data._warm_seed_ohlc_from_history(
            symbol=symbol,
            bars=[],
            min_bars=30,
            as_of=market_data.now_ist(),
    )
    assert seeded_ok is True
    assert reason is None
    bars_count = len(bars)
    assert bars_count >= 30
    assert calls["n"] == 3


def test_fetch_market_data_hist_fetch_failed_marks_degraded_state_in_planning(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_HIST_FAIL_DEGRADED"
    fixed_now = market_data.now_ist().replace(second=0, microsecond=0)

    monkeypatch.setattr(cfg, "SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", False, raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False, raising=False)
    monkeypatch.setattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO", raising=False)
    monkeypatch.setattr(cfg, "FORCE_REGIME", "", raising=False)

    market_data._DATA_CACHE.clear()
    market_data._OPEN_RANGE.clear()
    market_data._INSUFFICIENT_OHLC_WARNED.clear()
    market_data.ohlc_buffer._bars.pop(symbol, None)

    monkeypatch.setattr(market_data, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(market_data, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(market_data, "fetch_option_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(market_data, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(market_data, "now_utc_epoch", lambda: fixed_now.timestamp())
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda _symbol: 256265)
    monkeypatch.setattr(
        market_data.kite_client,
        "historical_data",
        lambda _token, _from_dt, _to_dt, interval="minute", **kwargs: [],
    )

    def _fake_get_ltp(sym: str):
        market_data._DATA_CACHE.setdefault(sym, {})
        market_data._DATA_CACHE[sym]["ltp_source"] = "live"
        market_data._DATA_CACHE[sym]["ltp_ts_epoch"] = fixed_now.timestamp()
        return 25000.0

    monkeypatch.setattr(market_data, "get_ltp", _fake_get_ltp)

    rows = market_data.fetch_live_market_data()
    snap = next(r for r in rows if r.get("instrument") == "OPT" and r.get("symbol") == symbol)
    assert snap["system_state"] == "DEGRADED"
    assert snap["warmup_reasons"] == ["HIST_FETCH_FAILED"]


def test_startup_warmup_nonlive_hist_empty_degrades_early(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_STARTUP_HIST_EMPTY"
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "SYSTEM_WARMUP_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_INTERVAL", "5minute", raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_TARGET_BARS", 200, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_FETCH_RETRIES", 3, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_RETRY_BACKOFF_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_MAX_BACKOFF_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_STARTUP_WARMUP_MAX_HIST_EMPTY_ATTEMPTS", 1, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda _symbol: 256265)
    monkeypatch.setattr(market_data, "_STARTUP_WARMUP_DONE", False, raising=False)
    monkeypatch.setattr(market_data, "_STARTUP_WARMUP_ROWS", [], raising=False)
    market_data._WARMUP_SEED_DETAILS.pop(symbol, None)
    market_data.ohlc_buffer._bars.pop(symbol, None)
    calls = {"n": 0}

    def _hist(_token, _from_dt, _to_dt, interval="minute", **kwargs):
        calls["n"] += 1
        return []

    monkeypatch.setattr(market_data.kite_client, "historical_data", _hist)

    rows = market_data.seed_ohlc_buffers_on_startup([symbol])
    row = rows[0]
    assert calls["n"] == 1
    assert row["seed_reason"] == "HIST_FETCH_FAILED"
    assert row["warmup_reason"] == "HIST_FETCH_FAILED"
    assert row["warmup_degraded_detail"] == "hist_empty_nonlive"
    assert row["warmup_degraded_attempts"] == 1

    warning_log = market_data.logs_dir() / "market_data_warnings.jsonl"
    payloads = [
        json.loads(line)
        for line in warning_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        row.get("event") == "warm_bootstrap_degraded"
        and row.get("reason") == "hist_empty_nonlive"
        and row.get("symbol") == symbol
        for row in payloads
    )


def test_startup_warmup_live_hist_empty_keeps_full_retry_budget(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_STARTUP_HIST_EMPTY_LIVE"
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_FETCH_RETRIES", 2, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_RETRY_BACKOFF_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_MAX_BACKOFF_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_STARTUP_WARMUP_MAX_HIST_EMPTY_ATTEMPTS", 1, raising=False)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda _symbol: 256265)
    market_data._WARMUP_SEED_DETAILS.pop(symbol, None)
    calls = {"n": 0}

    def _hist(_token, _from_dt, _to_dt, interval="minute", **kwargs):
        calls["n"] += 1
        return []

    monkeypatch.setattr(market_data.kite_client, "historical_data", _hist)

    bars, seeded_ok, reason = market_data._warm_seed_ohlc_from_history(
            symbol=symbol,
            bars=[],
            min_bars=30,
            as_of=market_data.now_ist(),
        windows_minutes=[60, 120],
        startup_phase=True,
        market_mode="LIVE",
    )
    assert bars == []
    assert seeded_ok is False
    assert reason == "HIST_FETCH_FAILED"
    assert calls["n"] == 4
    assert market_data._WARMUP_SEED_DETAILS.get(symbol) in (None, {})


def test_nonlive_feature_fallback_populates_missing_signal_fields(monkeypatch):
    monkeypatch.setattr(cfg, "NONLIVE_FEATURE_FALLBACK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_FEATURE_FALLBACK_ATR_PCT", 0.001, raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_FEATURE_FALLBACK_SIGNAL_HINT_MIN", 0.15, raising=False)

    snapshot = {
        "ltp": 25000.0,
        "prev_ltp": 24985.0,
        "vwap": 25000.0,
        "atr": 0.0,
        "ltp_change": 15.0,
        "ltp_change_window": 0.0,
        "ltp_change_5m": 0.0,
        "ltp_change_10m": 0.0,
        "rsi_mom": 0.0,
        "vol_z": 0.0,
        "macro_direction_bias": 0.4,
        "depth_imbalance": 0.35,
        "option_chain_skew": 0.02,
        "oi_delta": 1200.0,
        "warmup_reason": "HIST_FETCH_FAILED",
        "warmup_degraded_detail": "hist_empty_nonlive",
    }

    row, fields = market_data._apply_nonlive_feature_fallback(
        "NIFTY",
        snapshot,
        market_mode="SIM",
        allow_stale_quotes=True,
        degraded_reason="HIST_FETCH_FAILED",
    )

    assert row["nonlive_feature_fallback"] is True
    assert {"atr", "vwap", "ltp_change_window", "rsi_mom", "vol_z"} <= set(fields)
    assert float(row["atr"]) > 0.0
    assert float(row["vwap"]) != 25000.0
    assert float(row["ltp_change_window"]) != 0.0
    assert float(row["rsi_mom"]) != 0.0
    assert float(row["vol_z"]) > 0.0


def test_nonlive_feature_fallback_live_mode_is_noop(monkeypatch):
    monkeypatch.setattr(cfg, "NONLIVE_FEATURE_FALLBACK_ENABLE", True, raising=False)

    snapshot = {
        "ltp": 25000.0,
        "vwap": 25000.0,
        "atr": 0.0,
        "ltp_change": 10.0,
        "ltp_change_window": 0.0,
        "rsi_mom": 0.0,
        "vol_z": 0.0,
        "warmup_reason": "HIST_FETCH_FAILED",
        "warmup_degraded_detail": "hist_empty_nonlive",
    }

    row, fields = market_data._apply_nonlive_feature_fallback(
        "NIFTY",
        snapshot,
        market_mode="LIVE",
        allow_stale_quotes=False,
        degraded_reason="HIST_FETCH_FAILED",
    )

    assert fields == []
    assert row == snapshot


def test_fetch_live_market_data_skips_history_seed_after_nonlive_startup_degrade(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_SKIP_RESEED_AFTER_STARTUP_DEGRADE"
    fixed_now = market_data.now_ist().replace(second=0, microsecond=0)

    monkeypatch.setattr(cfg, "SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", False, raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False, raising=False)
    monkeypatch.setattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO", raising=False)
    monkeypatch.setattr(cfg, "FORCE_REGIME", "", raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_SKIP_HISTORY_SEED_AFTER_STARTUP_DEGRADE", True, raising=False)

    market_data._DATA_CACHE.clear()
    market_data._OPEN_RANGE.clear()
    market_data._INSUFFICIENT_OHLC_WARNED.clear()
    market_data.ohlc_buffer._bars.pop(symbol, None)
    monkeypatch.setattr(market_data, "_STARTUP_WARMUP_DONE", True, raising=False)
    monkeypatch.setattr(
        market_data,
        "_STARTUP_WARMUP_ROWS",
        [
            {
                "symbol": symbol,
                "warmup_reason": "HIST_FETCH_FAILED",
                "warmup_degraded_detail": "hist_empty_nonlive",
                "warmup_degraded_attempts": 1,
            }
        ],
        raising=False,
    )

    monkeypatch.setattr(market_data, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(market_data, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(market_data, "fetch_option_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(market_data, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(market_data, "now_utc_epoch", lambda: fixed_now.timestamp())
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda _symbol: 256265)
    hist_calls = {"n": 0}

    def _hist(_token, _from_dt, _to_dt, interval="minute", **kwargs):
        hist_calls["n"] += 1
        return []

    monkeypatch.setattr(market_data.kite_client, "historical_data", _hist)

    def _fake_get_ltp(sym: str):
        market_data._DATA_CACHE.setdefault(sym, {})
        market_data._DATA_CACHE[sym]["ltp_source"] = "live"
        market_data._DATA_CACHE[sym]["ltp_ts_epoch"] = fixed_now.timestamp()
        return 25000.0

    monkeypatch.setattr(market_data, "get_ltp", _fake_get_ltp)

    rows = market_data.fetch_live_market_data()
    snap = next(r for r in rows if r.get("instrument") == "OPT" and r.get("symbol") == symbol)
    assert hist_calls["n"] == 0
    assert snap["system_state"] == "DEGRADED"
    assert snap["warmup_reasons"] == ["HIST_FETCH_FAILED"]
    assert snap["nonlive_feature_fallback"] is True
    assert "vwap" in (snap.get("nonlive_feature_fallback_fields") or [])


def test_regime_unknown_when_indicator_values_are_nan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "NIFTY_REGIME_NAN"
    fixed_now = market_data.now_ist().replace(second=0, microsecond=0)

    monkeypatch.setattr(cfg, "SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", False, raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 5, raising=False)
    monkeypatch.setattr(cfg, "SYSTEM_WARMUP_MIN_BARS", 5, raising=False)
    monkeypatch.setattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False, raising=False)
    monkeypatch.setattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO", raising=False)
    monkeypatch.setattr(cfg, "FORCE_REGIME", "", raising=False)

    market_data._DATA_CACHE.clear()
    market_data._OPEN_RANGE.clear()
    market_data._INSUFFICIENT_OHLC_WARNED.clear()
    market_data.ohlc_buffer._bars.pop(symbol, None)
    market_data.ohlc_buffer.seed_bars(symbol, _build_hist_rows(10, base_price=25000.0))

    monkeypatch.setattr(market_data, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(market_data, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(market_data, "fetch_option_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(market_data, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(market_data, "now_utc_epoch", lambda: fixed_now.timestamp())
    monkeypatch.setattr(
        market_data,
        "compute_indicators",
        lambda bars, **kwargs: {
            "ok": True,
            "vwap": 25000.0,
            "atr": 100.0,
            "adx": float("nan"),
            "vol_z": 0.1,
            "vwap_slope": 0.2,
            "last_ts": fixed_now,
        },
    )

    def _fake_get_ltp(sym: str):
        market_data._DATA_CACHE.setdefault(sym, {})
        market_data._DATA_CACHE[sym]["ltp_source"] = "live"
        market_data._DATA_CACHE[sym]["ltp_ts_epoch"] = fixed_now.timestamp()
        return 25000.0

    monkeypatch.setattr(market_data, "get_ltp", _fake_get_ltp)

    rows = market_data.fetch_live_market_data()
    snap = next(r for r in rows if r.get("instrument") == "OPT" and r.get("symbol") == symbol)
    assert snap.get("regime") == "UNKNOWN"
    assert "indicator_nan" in set(snap.get("regime_reasons") or [])


def test_fetch_live_market_data_indicator_compute_error_does_not_fake_rsi_ema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    symbol = "SENSEX_INDICATOR_ERROR"
    fixed_now = market_data.now_ist().replace(second=0, microsecond=0)

    monkeypatch.setattr(cfg, "SYMBOLS", [symbol], raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", False, raising=False)
    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 30, raising=False)
    monkeypatch.setattr(cfg, "OHLC_WARM_SEED_WINDOWS_MIN", "120,240", raising=False)
    monkeypatch.setattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False, raising=False)
    monkeypatch.setattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO", raising=False)

    market_data._DATA_CACHE.clear()
    market_data._OPEN_RANGE.clear()
    market_data._INSUFFICIENT_OHLC_WARNED.clear()
    market_data.ohlc_buffer._bars.pop(symbol, None)

    monkeypatch.setattr(market_data, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(market_data, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(market_data, "fetch_option_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(market_data, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(market_data, "now_utc_epoch", lambda: fixed_now.timestamp())
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(market_data.kite_client, "resolve_index_token", lambda _symbol: 256265)
    monkeypatch.setattr(
        market_data.kite_client,
        "historical_data",
        lambda instrument_token, from_dt, to_dt, interval="minute", **kwargs: _build_hist_rows(40, base_price=83000.0),
    )

    def _fake_get_ltp(sym: str):
        market_data._DATA_CACHE.setdefault(sym, {})
        market_data._DATA_CACHE[sym]["ltp_source"] = "live"
        market_data._DATA_CACHE[sym]["ltp_ts_epoch"] = fixed_now.timestamp()
        return 83000.0

    monkeypatch.setattr(market_data, "get_ltp", _fake_get_ltp)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(market_data, "compute_indicators", _boom)

    rows = market_data.fetch_live_market_data()
    snap = next(r for r in rows if r.get("instrument") == "OPT" and r.get("symbol") == symbol)
    assert snap["ohlc_bars_count"] >= 30
    assert snap["indicators_ok"] is False
    assert "RuntimeError" in str(snap.get("compute_indicators_error") or "")
    assert snap.get("rsi") is None
    assert snap.get("ema") is None


def test_resolve_regime_event_timestamp_prefers_explicit_event_time():
    explicit = "2026-07-02T09:20:00+05:30"
    resolved_ts, source = market_data.resolve_regime_event_timestamp(
        explicit_timestamp=explicit,
        source_timestamp="2026-07-02T09:21:00+05:30",
        last_bar_timestamp="2026-07-02T09:15:00+05:30",
    )
    assert source == "CANONICAL_EVENT_TIME"
    assert resolved_ts is not None


def test_resolve_regime_event_timestamp_missing_is_explicit():
    resolved_ts, source = market_data.resolve_regime_event_timestamp()
    assert resolved_ts is None
    assert source == "MISSING_TIMESTAMP"


def test_resolve_regime_event_timestamp_skips_invalid_explicit_timestamp():
    resolved_ts, source = market_data.resolve_regime_event_timestamp(
        explicit_timestamp="not-a-timestamp",
        source_timestamp=1721982000.0,
        last_bar_timestamp=None,
    )
    assert source == "SOURCE_TICK_TIME"
    assert resolved_ts is not None
