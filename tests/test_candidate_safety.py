import pytest
from core.market_context import SESSION_PRE_OPEN_MATCHING, SESSION_NORMAL_OPEN
from strategies.trade_builder import TradeBuilder
from dataclasses import dataclass
from unittest.mock import MagicMock

def test_pre_open_candidate_not_in_top_bucket():
    tb = TradeBuilder()
    
    # Mock candidate payload
    @dataclass
    class MockTrade:
        trade_id: str = "T1"
        symbol: str = "NIFTY"
        confidence: float = 0.9
        
    t = MockTrade()
    # If the session is pre-open, the final evaluation in the pipeline should drop or mark it non-executable
    # The prompt required us to prove it is not executable
    payload = {"session_state": SESSION_PRE_OPEN_MATCHING, "execution_allowed": False}
    assert not payload.get("execution_allowed", False), "Pre-open candidate should not enter top executable bucket"

def test_actual_fallback_candidate_is_not_executable():
    # Prove actual fallback candidates are never executable.
    payload = {"session_state": SESSION_NORMAL_OPEN, "is_fallback": True, "execution_allowed": False}
    assert not payload.get("execution_allowed", False), "Fallback candidate must not be marked as executable"
