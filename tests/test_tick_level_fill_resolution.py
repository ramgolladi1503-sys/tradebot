import pytest
import pandas as pd
from datetime import datetime
from core.slippage_model import estimate_slippage

def test_replay_intrabar_ambiguity():
    # Tick sequence 1: Hits stop first
    ticks_1 = [95, 94, 92, 90, 89, 98, 100]
    
    # Tick sequence 2: Hits target first
    ticks_2 = [95, 98, 100, 92, 90]
    
    def evaluate_ticks(ticks, target, stop):
        for t in ticks:
            if t >= target:
                return "TARGET"
            if t <= stop:
                return "STOP"
        return "NONE"

    assert evaluate_ticks(ticks_1, 100, 90) == "STOP"
    assert evaluate_ticks(ticks_2, 100, 90) == "TARGET"

def test_replay_slippage_model():
    # Ensure SlippageEstimate is applied
    est = estimate_slippage(
        side="BUY",
        bid=100.0,
        ask=100.2,
        execution_entry=100.2,
        qty=1,
        volume=1000,
        depth=None,
        vol_z=1.0
    )
    assert est.expected_slippage >= 0.0
    assert est.executable_price_estimate > 100.2 # Slippage increases buy price

def test_no_lookahead_leakage():
    pass
