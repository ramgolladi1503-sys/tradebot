import strategies.ensemble as ensemble


def test_event_regime_calls_event_breakout(monkeypatch):
    calls = {"event": 0, "micro": 0}

    monkeypatch.setattr(ensemble, "volatility_filter", lambda atr, ltp: True)

    def _event(*_args, **_kwargs):
        calls["event"] += 1
        return ensemble.StrategySignal("BUY_CALL", 0.9, "event")

    def _micro(*_args, **_kwargs):
        calls["micro"] += 1
        return ensemble.StrategySignal("BUY_CALL", 0.7, "micro")

    monkeypatch.setattr(ensemble, "event_breakout_signal", _event)
    monkeypatch.setattr(ensemble, "micro_pattern_signal", _micro)
    monkeypatch.setattr(ensemble, "orb_breakout_signal", lambda *_args, **_kwargs: None)

    signal = ensemble.ensemble_signal(
        {
            "regime": "EVENT",
            "ltp": 100.0,
            "vwap": 100.0,
            "vwap_slope": 0.1,
            "rsi_mom": 0.0,
            "atr": 1.0,
            "ltp_change_window": 2.0,
            "vol_z": 1.0,
        }
    )

    assert signal is not None
    assert calls["event"] >= 1
    assert calls["micro"] == 0


def test_range_regime_calls_mean_reversion_and_micro(monkeypatch):
    calls = {"mr": 0, "micro": 0}

    monkeypatch.setattr(ensemble, "volatility_filter", lambda atr, ltp: True)

    def _mr(*_args, **_kwargs):
        calls["mr"] += 1
        return ensemble.StrategySignal("BUY_CALL", 0.7, "mr")

    def _micro(*_args, **_kwargs):
        calls["micro"] += 1
        return ensemble.StrategySignal("BUY_CALL", 0.8, "micro")

    monkeypatch.setattr(ensemble, "mean_reversion_signal", _mr)
    monkeypatch.setattr(ensemble, "micro_pattern_signal", _micro)

    signal = ensemble.ensemble_signal(
        {
            "regime": "RANGE",
            "ltp": 100.0,
            "vwap": 100.0,
            "vwap_slope": 0.0,
            "rsi_mom": 0.0,
            "atr": 1.0,
            "ltp_change_5m": 12.0,
            "ltp_change_10m": 4.0,
        }
    )

    assert signal is not None
    assert calls["mr"] >= 1
    assert calls["micro"] >= 1
