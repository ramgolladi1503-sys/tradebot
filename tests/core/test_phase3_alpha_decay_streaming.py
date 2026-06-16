import pytest
import time
from core.execution_engine import ExecutionEngine
from core.execution.alpha_decay import AlphaDecayState
from core.orchestrator import Orchestrator

from core.execution.alpha_decay import monitor_alpha_decay

def test_monitor_alpha_decay_and_engine_intent():
    engine = ExecutionEngine()
    
    state = AlphaDecayState(
        initial_edge_bps=5.0,
        current_edge_bps=1.0,  # decaying
        holding_time_sec=600,
        expected_holding_time_sec=300,
        execution_cost_bps=2.0
    )
    
    l2_support = 0.1
    momentum = -10.0
    
    should_exit = monitor_alpha_decay(
        state=state,
        l2_support_ratio=l2_support,
        current_momentum_bps=momentum
    )
    
    assert should_exit is True
    
    if should_exit:
        intent = {
            "action": "FULL_EXIT",
            "trade_id": "test_decay_1",
            "reason_code": "decay_exhausted",
            "exit_qty_units": 10,
            "ts_epoch": time.time(),
        }
        ack = engine.apply_exit_intent(intent)
        assert ack["accepted"] is True
