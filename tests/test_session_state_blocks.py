import pytest
from core.decision_dag import _node_final_decision
from core.market_context import SESSION_PRE_OPEN_MATCHING, SESSION_OPEN_WARMUP, SESSION_NORMAL_OPEN, SESSION_POST_CLOSE

def test_session_state_blocks_execution_except_normal_open():
    class DummyPayload:
        def __init__(self, state):
            self.session_state = state
            self.execution_feed_ready = True
            self.is_order_action = False
            self.broker_api_called = False
            self.symbol = "DUMMY"
            self.ts_epoch = 1234567890.0
            
    for state in [SESSION_PRE_OPEN_MATCHING, SESSION_OPEN_WARMUP, SESSION_POST_CLOSE, "CLOSED"]:
        payload = DummyPayload(state)
        decision = _node_final_decision(payload, {}, {})
        assert not decision.ok, f"Execution should be blocked for {state}"

    normal_payload = DummyPayload(SESSION_NORMAL_OPEN)
    decision = _node_final_decision(normal_payload, {}, {})
    # The session state check shouldn't raise a hard block on NORMAL_OPEN
    assert "session_state" not in str(decision.reasons)
