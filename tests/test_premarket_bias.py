import premarket


def test_premarket_bias_returns_neutral_when_required_ltp_missing(monkeypatch):
    monkeypatch.setattr(
        premarket.cfg,
        "PREMARKET_INDICES_LTP",
        {"NIFTY": "NSE:NIFTY 50", "BANKNIFTY": "NSE:NIFTY BANK", "SENSEX": "BSE:SENSEX"},
        raising=False,
    )
    monkeypatch.setattr(
        premarket.cfg,
        "PREMARKET_INDICES_CLOSE",
        {"NIFTY": 16000, "BANKNIFTY": 40000, "SENSEX": 83000},
        raising=False,
    )
    monkeypatch.setattr(
        premarket,
        "get_ltp",
        lambda symbol: None if symbol == "NIFTY" else 40100,
        raising=False,
    )

    result = premarket.calculate_premarket_bias()

    assert result["bias"] == "NEUTRAL"
    assert result["reason"] == "missing_required_ltp"
    assert result["missing_symbols"] == ["NIFTY"]


def test_premarket_bias_uses_config_thresholds(monkeypatch):
    monkeypatch.setattr(
        premarket.cfg,
        "PREMARKET_INDICES_LTP",
        {"NIFTY": "NSE:NIFTY 50", "BANKNIFTY": "NSE:NIFTY BANK"},
        raising=False,
    )
    monkeypatch.setattr(
        premarket.cfg,
        "PREMARKET_INDICES_CLOSE",
        {"NIFTY": 25000, "BANKNIFTY": 45000},
        raising=False,
    )
    prices = {"NIFTY": 25100, "BANKNIFTY": 44000}
    monkeypatch.setattr(premarket, "get_ltp", lambda symbol: prices[symbol], raising=False)

    result = premarket.calculate_premarket_bias()

    assert result["score"] == 1
    assert result["bias"] == "NEUTRAL"
    assert result["reason"] is None
