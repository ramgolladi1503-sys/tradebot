from types import SimpleNamespace

import core.market_data_warmup_probe as probe


def test_market_data_warmup_probe_records_success_events(monkeypatch):
    events = []

    def fake_record(event, *, source, details=None, error=None):
        events.append({"event": event, "source": source, "details": details or {}, "error": error or ""})

    monkeypatch.setattr(probe, "_record", fake_record)
    monkeypatch.setattr(probe, "_PATCHED", False)

    def ensure_startup_warmup_bootstrap(symbols=None, *, force=False, market_context=None):
        resolved = fake_module._startup_warmup_symbols(symbols)
        return fake_module.seed_ohlc_buffers_on_startup(symbols=resolved, market_context=market_context)

    def _startup_warmup_symbols(symbols=None):
        return [str(symbol).upper() for symbol in (symbols or ["NIFTY"]) if str(symbol).strip()]

    def seed_ohlc_buffers_on_startup(symbols=None, *, market_context=None):
        rows = []
        for symbol in list(symbols or []):
            bars, seeded_ok, reason = fake_module._warm_seed_ohlc_from_history(
                symbol=symbol,
                bars=[],
                min_bars=1,
                interval="minute",
                startup_phase=True,
                market_mode=(market_context or {}).get("mode", "PAPER"),
            )
            ind = fake_module.compute_indicators(bars)
            rows.append({"symbol": symbol, "seeded_ok": seeded_ok, "reason": reason, "indicators_ok": ind.get("ok")})
        return rows

    def _warm_seed_ohlc_from_history(**kwargs):
        return ([{"close": 100.0}], True, None)

    def compute_indicators(bars):
        return {"ok": bool(bars)}

    fake_module = SimpleNamespace(
        ensure_startup_warmup_bootstrap=ensure_startup_warmup_bootstrap,
        _startup_warmup_symbols=_startup_warmup_symbols,
        seed_ohlc_buffers_on_startup=seed_ohlc_buffers_on_startup,
        _warm_seed_ohlc_from_history=_warm_seed_ohlc_from_history,
        compute_indicators=compute_indicators,
    )

    probe.install_market_data_warmup_probe(fake_module)
    rows = fake_module.ensure_startup_warmup_bootstrap(["NIFTY"], market_context={"mode": "PAPER"})

    assert rows == [{"symbol": "NIFTY", "seeded_ok": True, "reason": None, "indicators_ok": True}]
    event_names = [event["event"] for event in events]
    assert "MARKET_DATA_WARMUP_ENTERED" in event_names
    assert "MARKET_DATA_WARMUP_SYMBOLS_RESOLVE_STARTED" in event_names
    assert "MARKET_DATA_WARMUP_SYMBOLS_RESOLVE_COMPLETED" in event_names
    assert "MARKET_DATA_WARMUP_SEED_STARTED" in event_names
    assert "MARKET_DATA_WARMUP_SYMBOL_SEED_STARTED" in event_names
    assert "MARKET_DATA_WARMUP_SYMBOL_SEED_COMPLETED" in event_names
    assert "MARKET_DATA_WARMUP_INDICATORS_STARTED" in event_names
    assert "MARKET_DATA_WARMUP_INDICATORS_COMPLETED" in event_names
    assert "MARKET_DATA_WARMUP_SEED_COMPLETED" in event_names
    assert "MARKET_DATA_WARMUP_COMPLETED" in event_names


def test_market_data_warmup_probe_records_failure_events(monkeypatch):
    events = []

    def fake_record(event, *, source, details=None, error=None):
        events.append({"event": event, "source": source, "details": details or {}, "error": error or ""})

    monkeypatch.setattr(probe, "_record", fake_record)
    monkeypatch.setattr(probe, "_PATCHED", False)

    def ensure_startup_warmup_bootstrap(symbols=None, *, force=False, market_context=None):
        return fake_module.seed_ohlc_buffers_on_startup(symbols=symbols, market_context=market_context)

    def seed_ohlc_buffers_on_startup(symbols=None, *, market_context=None):
        return fake_module._warm_seed_ohlc_from_history(symbol="NIFTY", bars=[], min_bars=1)

    def _warm_seed_ohlc_from_history(**kwargs):
        raise RuntimeError("historical fetch stuck")

    fake_module = SimpleNamespace(
        ensure_startup_warmup_bootstrap=ensure_startup_warmup_bootstrap,
        seed_ohlc_buffers_on_startup=seed_ohlc_buffers_on_startup,
        _warm_seed_ohlc_from_history=_warm_seed_ohlc_from_history,
    )

    probe.install_market_data_warmup_probe(fake_module)

    try:
        fake_module.ensure_startup_warmup_bootstrap(["NIFTY"])
    except RuntimeError as exc:
        assert "historical fetch stuck" in str(exc)
    else:
        raise AssertionError("expected warmup failure")

    event_names = [event["event"] for event in events]
    assert "MARKET_DATA_WARMUP_ENTERED" in event_names
    assert "MARKET_DATA_WARMUP_SEED_STARTED" in event_names
    assert "MARKET_DATA_WARMUP_SYMBOL_SEED_STARTED" in event_names
    assert "MARKET_DATA_WARMUP_SYMBOL_SEED_FAILED" in event_names
    assert "MARKET_DATA_WARMUP_SEED_FAILED" in event_names
    assert "MARKET_DATA_WARMUP_FAILED" in event_names
