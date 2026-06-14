import pytest
from core.regime_router import resolve_strategy_regime, _CANONICAL_REGIMES
import core.regime_router

def test_resolve_strategy_regime_clean_state():
    assert resolve_strategy_regime("TREND", bias="bullish") == "TRENDING_UP"
    assert resolve_strategy_regime("TREND", bias="bearish") == "TRENDING_DOWN"
    assert resolve_strategy_regime("VOLATILE") == "VOLATILE"
    assert resolve_strategy_regime("RANGE") == "RANGE"
    
def test_resolve_strategy_regime_ambiguous_fails_closed():
    # If a trend lacks a direction bias, it must emit UNKNOWN instead of blindly guessing TRENDING_UP
    assert resolve_strategy_regime("TREND", bias="none") == "UNKNOWN"
    assert resolve_strategy_regime("GARBAGE") == "UNKNOWN"
    assert resolve_strategy_regime("TREND", bias="") == "UNKNOWN"

def test_regime_transition_logging(monkeypatch):
    core.regime_router._last_regime_emitted = None
    
    events_logged = []
    
    def fake_append_event(event_name, payload):
        events_logged.append((event_name, payload))
        
    monkeypatch.setattr(core.regime_router, "append_event", fake_append_event)
    
    # First call sets initial state, doesn't transition
    assert resolve_strategy_regime("VOLATILE") == "VOLATILE"
    assert events_logged == []
    
    # Second call changes regime
    assert resolve_strategy_regime("RANGE") == "RANGE"
    assert events_logged == [
        (
            "regime_transition",
            {"previous_regime": "VOLATILE", "new_regime": "RANGE", "raw_input": "RANGE", "bias_input": "None"}
        )
    ]
    
    # Third call same regime, no transition
    assert resolve_strategy_regime("RANGE") == "RANGE"
    assert events_logged == [
        (
            "regime_transition",
            {"previous_regime": "VOLATILE", "new_regime": "RANGE", "raw_input": "RANGE", "bias_input": "None"}
        )
    ]
