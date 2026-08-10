from strategies.trade_builder import TradeBuilder

def _base_market_data(overrides=None):
    base = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "market_open": True,
        "market_context": {"execution_mode": "LIVE", "market_open": True, "session_state": "NORMAL_OPEN"},
        "ltp": 25100.0, # (ltp - vwap) / vwap = 100/25000 = 0.004 > 0.0015
        "vwap": 25000.0,
        "vwap_slope": 0.0,
        "atr": 50.0,
        "quote_ok": True,
        "chain_source": "live",
        "bid": 24999.0,
        "ask": 25001.0,
        "regime_day": "TREND",
        "regime_probs": {"TREND": 0.9, "RANGE": 0.1, "EVENT": 0.0, "PANIC": 0.0},
        "option_chain": [
            {
                "type": "CE",
                "strike": 25100.0,
                "expiry": "2026-04-30",
                "tradingsymbol": "NIFTY26APR25100CE",
                "instrument_token": 123456,
                "ltp": 102.0,
                "bid": 101.5,
                "ask": 102.5,
                "quote_age_sec": 1.0,
            },
            {
                "type": "PE",
                "strike": 25100.0,
                "expiry": "2026-04-30",
                "tradingsymbol": "NIFTY26APR25100PE",
                "instrument_token": 123457,
                "ltp": 98.0,
                "bid": 97.5,
                "ask": 98.5,
                "quote_age_sec": 1.0,
            }
        ],
    }
    if overrides:
        base.update(overrides)
    return base

def test_trade_builder_valid_bullish_maps_correctly(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(tb, "_signal_for_symbol", lambda *args, **kwargs: {
        "direction": "BUY_CALL", "reason": "test_bullish", "score": 0.9, "regime_day": "TREND"
    })
    monkeypatch.setattr(tb.lifecycle, "can_allocate", lambda *args, **kwargs: (True, "ok"))
    md = _base_market_data({"ltp": 25200.0, "vwap_slope": 0.05})
    trade = tb.build(md)
    assert trade is not None
    assert getattr(trade, "option_type", None) == "CE"
    # This contract tests signal-to-option-side mapping. Runtime authority is
    # intentionally fail-closed in CI, so a correctly mapped candidate remains
    # advisory rather than being promoted to executable by the test fixture.
    assert trade.candidate_status == "advisory"
    assert getattr(trade, "execution_allowed", False) is False

def test_trade_builder_valid_bearish_maps_correctly(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(tb, "_signal_for_symbol", lambda *args, **kwargs: {
        "direction": "BUY_PUT", "reason": "test_bearish", "score": 0.9, "regime_day": "TREND"
    })
    monkeypatch.setattr(tb.lifecycle, "can_allocate", lambda *args, **kwargs: (True, "ok"))
    md = _base_market_data({"ltp": 24800.0, "vwap_slope": -0.05})
    trade = tb.build(md)
    assert trade is not None
    assert getattr(trade, "option_type", None) == "PE"
    assert trade.candidate_status == "advisory"
    assert getattr(trade, "execution_allowed", False) is False

def test_trade_builder_neutral_no_trigger_blocks():
    tb = TradeBuilder()
    # neutral -> ltp = vwap
    md = _base_market_data({"ltp": 25000.0})
    trade = tb.build(md)
    if trade:
        assert type(trade) is dict or getattr(trade, "candidate_status", None) != "executable"

def test_trade_builder_nan_required_input_fails_closed():
    tb = TradeBuilder()
    md = _base_market_data({"ltp": float("nan")})
    trade = tb.build(md)
    if trade:
        assert type(trade) is dict or getattr(trade, "candidate_status", None) != "executable"

def test_trade_builder_missing_required_input_fails_closed():
    tb = TradeBuilder()
    md = _base_market_data()
    md.pop("ltp")
    trade = tb.build(md)
    if trade:
        assert type(trade) is dict or getattr(trade, "candidate_status", None) != "executable"

def test_trade_builder_stale_quote_fails_closed():
    tb = TradeBuilder()
    md = _base_market_data()
    md["option_chain"][0]["quote_age_sec"] = 999.0 # Stale
    trade = tb.build(md)
    if trade:
        status = getattr(trade, "candidate_status", None) if hasattr(trade, "candidate_status") else trade.get("candidate_status")
        assert status != "executable"

def test_trade_builder_fallback_quote_fails_closed():
    tb = TradeBuilder()
    md = _base_market_data()
    md["option_chain"][0]["quote_fallback"] = True
    trade = tb.build(md)
    if trade:
        status = getattr(trade, "candidate_status", None) if hasattr(trade, "candidate_status") else trade.get("candidate_status")
        assert status != "executable"

def test_trade_builder_advisory_candidate_cannot_become_executable():
    tb = TradeBuilder()
    md = _base_market_data()
    md["market_context"]["execution_mode"] = "PAPER"
    md["option_chain"][0]["quote_age_sec"] = 999.0
    trade = tb.build(md)
    if trade:
        status = getattr(trade, "candidate_status", None) if hasattr(trade, "candidate_status") else trade.get("candidate_status")
        assert status != "executable"
