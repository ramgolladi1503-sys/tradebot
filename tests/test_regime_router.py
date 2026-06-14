import pytest
from core.regime_router import resolve_strategy_regime, _CANONICAL_REGIMES
import core.regime_router

def test_resolve_strategy_regime_clean_state():
    assert resolve_strategy_regime("TREND", bias="bullish") == "TRENDING_UP"
    assert resolve_strategy_regime("TREND", bias="bearish") == "TRENDING_DOWN"
    assert resolve_strategy_regime("VOLATILE") == "VOLATILE"
    
def test_resolve_strategy_regime_ambiguous_fails_closed():
    # If a trend lacks a direction bias, it must emit UNKNOWN instead of blindly guessing TRENDING_UP
    assert resolve_strategy_regime("TREND", bias="none") == "UNKNOWN"
    assert resolve_strategy_regime("GARBAGE") == "UNKNOWN"

def test_regime_transition_logging(monkeypatch):
    core.regime_router._last_regime_emitted = None
    
    events_logged = []
    
    def fake_append_event(event_name, payload):
        events_logged.append((event_name, payload))
        
    monkeypatch.setattr(core.regime_router, "append_event", fake_append_event)
    
    # First call sets initial state, doesn't transition
    resolve_strategy_regime("VOLATILE")
    assert len(events_logged) == 0
    
    # Second call changes regime
    resolve_strategy_regime("RANGE")
    assert len(events_logged) == 1
    assert events_logged[0][0] == "regime_transition"
    assert events_logged[0][1]["previous_regime"] == "VOLATILE"
    assert events_logged[0][1]["new_regime"] == "RANGE"
    
    # Third call same regime, no transition
    resolve_strategy_regime("RANGE")
    assert len(events_logged) == 1
