import pytest
from core.pairs_execution_coordinator import PairsExecutionCoordinator
from core.candidate_intent import create_candidate_intent

class MockExecutionRouter:
    def __init__(self, fail_leg_b=False):
        self.fail_leg_b = fail_leg_b
        self.executions = []
        
    def execute(self, trade, bid, ask, volume, **kwargs):
        self.executions.append(trade)
        if self.fail_leg_b and trade["instrument"] == "NIFTY_INDEX":
            return {"status": "REJECTED"}
        return {"status": "FILLED"}

def test_pairs_execution_coordinator_success():
    router = MockExecutionRouter(fail_leg_b=False)
    coordinator = PairsExecutionCoordinator(router)
    
    intent = create_candidate_intent(
        strategy_id="pairs_arbitrage_v1",
        instrument="BANKNIFTY_NIFTY",
        direction="SHORT",
        regime="RANGE",
        family="statistical_arbitrage",
        intent_type="ENTRY",
        trigger="test",
        invalidation="test",
        required_evidence_keys=()
    )
    
    current_prices = {
        "BANKNIFTY_INDEX": 45000,
        "NIFTY_INDEX": 21000
    }
    
    res = coordinator.route_pair(intent, current_prices)
    
    assert res["status"] == "FILLED"
    assert len(router.executions) == 2
    assert router.executions[0]["instrument"] == "BANKNIFTY_INDEX"
    assert router.executions[0]["direction"] == "SELL"
    assert router.executions[1]["instrument"] == "NIFTY_INDEX"
    assert router.executions[1]["direction"] == "BUY"

def test_pairs_execution_coordinator_unwind():
    router = MockExecutionRouter(fail_leg_b=True)
    coordinator = PairsExecutionCoordinator(router)
    
    intent = create_candidate_intent(
        strategy_id="pairs_arbitrage_v1",
        instrument="BANKNIFTY_NIFTY",
        direction="SHORT",
        regime="RANGE",
        family="statistical_arbitrage",
        intent_type="ENTRY",
        trigger="test",
        invalidation="test",
        required_evidence_keys=()
    )
    
    current_prices = {
        "BANKNIFTY_INDEX": 45000,
        "NIFTY_INDEX": 21000
    }
    
    res = coordinator.route_pair(intent, current_prices)
    
    assert res["status"] == "UNWOUND"
    assert len(router.executions) == 3
    # Leg A Sell
    assert router.executions[0]["instrument"] == "BANKNIFTY_INDEX"
    assert router.executions[0]["direction"] == "SELL"
    # Leg B Buy (fails)
    assert router.executions[1]["instrument"] == "NIFTY_INDEX"
    assert router.executions[1]["direction"] == "BUY"
    # Unwind Leg A (Buy back)
    assert router.executions[2]["instrument"] == "BANKNIFTY_INDEX"
    assert router.executions[2]["direction"] == "BUY"
    assert router.executions[2]["order_type"] == "MARKET"
