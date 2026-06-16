import pytest
from core.orders.state_machine import OrderStateMachine, OrderState, OrderStateTransitionError

def test_order_idempotency(tmp_path):
    sm = OrderStateMachine(db_path=tmp_path / "orders.db")
    
    # Create an order
    order = sm.create_order(order_id="ord-1", idempotency_key="ik-1")
    assert order.state == OrderState.NEW
    
    # Transition to sent
    order = sm.transition(order_id="ord-1", next_state=OrderState.SENT)
    assert order.state == OrderState.SENT
    
    # Duplicate transition to sent should be safely ignored (idempotency)
    order = sm.transition(order_id="ord-1", next_state=OrderState.SENT)
    assert order.state == OrderState.SENT

def test_stale_callbacks_ignored(tmp_path):
    sm = OrderStateMachine(db_path=tmp_path / "orders.db")
    sm.create_order(order_id="ord-2", idempotency_key="ik-2")
    sm.transition(order_id="ord-2", next_state=OrderState.SENT)
    sm.transition(order_id="ord-2", next_state=OrderState.FILLED, filled_qty=100.0)
    
    # Transition to an earlier state like ACKNOWLEDGED should be ignored because FILLED is terminal
    order = sm.transition(order_id="ord-2", next_state=OrderState.ACKNOWLEDGED)
    assert order.state == OrderState.FILLED

def test_simulated_boundaries(tmp_path):
    sm = OrderStateMachine(db_path=tmp_path / "orders.db")
    sm.create_order(order_id="ord-sim", idempotency_key="ik-sim")
    
    # Cannot transition from NEW to SIM_SENT (invalid path)
    with pytest.raises(OrderStateTransitionError):
        sm.transition(order_id="ord-sim", next_state=OrderState.SIM_SENT)
        
    # Start a simulated order properly if we had a transition to SIM_NEW
    # For now, let's just test that the state machine enforces strict paths
