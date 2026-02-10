from strategies.trade_builder import TradeBuilder


def _base_market_data():
    return {
        "symbol": "NIFTY",
        "segment": "NSE_FNO",
        "ltp": 25000.0,
        "ltp_source": "live",
        "chain_source": "live",
        "quote_ok": True,
        "quote_age_sec": 1.0,
    }


def _base_opt():
    return {
        "quote_ok": True,
        "quote_age_sec": 1.0,
    }


def test_tradable_false_when_market_closed(monkeypatch):
    monkeypatch.setattr("strategies.trade_builder.is_market_open_ist", lambda *args, **kwargs: False)
    builder = TradeBuilder()
    intent = builder.trade_intent_flags(_base_market_data(), opt=_base_opt())
    assert intent["tradable"] is False
    assert "market_closed" in intent["tradable_reasons_blocking"]


def test_tradable_false_when_quote_stale(monkeypatch):
    monkeypatch.setattr("strategies.trade_builder.is_market_open_ist", lambda *args, **kwargs: True)
    builder = TradeBuilder()
    stale_opt = _base_opt()
    stale_opt["quote_age_sec"] = 30.0
    intent = builder.trade_intent_flags(_base_market_data(), opt=stale_opt)
    assert intent["tradable"] is False
    assert "stale_option_quote" in intent["tradable_reasons_blocking"]


def test_tradable_true_when_all_conditions_good(monkeypatch):
    monkeypatch.setattr("strategies.trade_builder.is_market_open_ist", lambda *args, **kwargs: True)
    builder = TradeBuilder()
    intent = builder.trade_intent_flags(_base_market_data(), opt=_base_opt(), risk_guard_passed=True)
    assert intent["tradable"] is True
    assert intent["tradable_reasons_blocking"] == []
    assert intent["source_flags"]["chain_source"] == "live"
    assert intent["source_flags"]["market_open"] is True
    assert intent["source_flags"]["ltp_source"] == "live"
    assert intent["source_flags"]["risk_guard_passed"] is True


def test_tradable_false_when_risk_guard_fails(monkeypatch):
    monkeypatch.setattr("strategies.trade_builder.is_market_open_ist", lambda *args, **kwargs: True)
    builder = TradeBuilder()
    intent = builder.trade_intent_flags(_base_market_data(), opt=_base_opt(), risk_guard_passed=False)
    assert intent["tradable"] is False
    assert "risk_guard_failed" in intent["tradable_reasons_blocking"]
    assert intent["source_flags"]["risk_guard_passed"] is False


def test_tradable_false_when_ltp_not_live(monkeypatch):
    monkeypatch.setattr("strategies.trade_builder.is_market_open_ist", lambda *args, **kwargs: True)
    builder = TradeBuilder()
    md = _base_market_data()
    md["ltp_source"] = "fallback"
    intent = builder.trade_intent_flags(md, opt=_base_opt(), risk_guard_passed=True)
    assert intent["tradable"] is False
    assert "ltp_not_live" in intent["tradable_reasons_blocking"]
