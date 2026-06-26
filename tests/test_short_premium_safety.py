import pytest
import time
from unittest.mock import patch, MagicMock
from core.strategy_requirements import validate_strategy_requirements
from strategies.short_premium_builder import ShortPremiumBuilder
from core.trade_schema import Trade

def test_short_premium_fails_if_not_range_bound():
    snapshot = {"regime": "TRENDING", "raw_data": {"atr": 10}, "ts_epoch": time.time(), "option_chain_last_ts": time.time()}
    trade = MagicMock()
    valid, vetoes = validate_strategy_requirements("IRON_CONDOR", snapshot, trade, time.time())
    assert not valid
    assert "NO_RANGE_CONFIRMATION" in vetoes

def test_short_premium_fails_for_uncapped_strangle():
    snapshot = {"regime": "RANGE_BOUND", "raw_data": {"atr": 10}, "ts_epoch": time.time(), "option_chain_last_ts": time.time()}
    trade = MagicMock()
    valid, vetoes = validate_strategy_requirements("SELL_STRANGLE", snapshot, trade, time.time())
    assert not valid
    assert "UNCAPPED_RISK_STRUCTURE" in vetoes

def test_iron_condor_passes_with_fresh_data_and_range_bound():
    snapshot = {"regime": "RANGE_BOUND", "raw_data": {"atr": 10}, "ts_epoch": time.time(), "option_chain_last_ts": time.time()}
    trade = MagicMock()
    valid, vetoes = validate_strategy_requirements("IRON_CONDOR", snapshot, trade, time.time())
    assert valid
    assert len(vetoes) == 0

def test_short_premium_builder_live_paper_only():
    builder = ShortPremiumBuilder()
    market_data = {
        "symbol": "NIFTY",
        "regime": "RANGE_BOUND",
        "execution_mode": "LIVE",
        "ltp": 15000,
        "option_chain": [
            {"strike": 15075, "type": "CE", "last_price": 50, "instrument_token": 1, "expiry": "2026-06-25"},
            {"strike": 15125, "type": "CE", "last_price": 5, "instrument_token": 2, "expiry": "2026-06-25"},
            {"strike": 14925, "type": "PE", "last_price": 45, "instrument_token": 3, "expiry": "2026-06-25"},
            {"strike": 14875, "type": "PE", "last_price": 10, "instrument_token": 4, "expiry": "2026-06-25"},
        ],
        "ts_epoch": time.time(),
        "option_chain_last_ts": time.time(),
        "atr": 50,
        "raw_data": {"atr": 50}
    }
    def mock_getattr_fn(obj, name, default=None):
        if name == "SHORT_PREMIUM_ENABLED":
            return True
        if name == "EXECUTION_MODE":
            return "LIVE"
        if name == "ALLOW_NAKED_STRANGLE_PAPER":
            return False
        return getattr(obj, name, default)
        
    with patch("strategies.short_premium_builder.getattr", side_effect=mock_getattr_fn):
        candidates = builder.generate_candidates(market_data)
        assert len(candidates) > 0
        for cand in candidates:
            assert cand.execution_allowed is False
            assert "LIVE_MODE_SHORT_PREMIUM_BLOCKED" in cand.veto_codes
