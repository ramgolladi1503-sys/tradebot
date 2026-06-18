import pytest
from core.candidate_audits.cost_model import IndianDerivativesCostModel

def test_cost_model_option_buy_profit():
    model = IndianDerivativesCostModel()
    
    # Buy at 100, sell at 110. Lot size 50.
    cost = model.calculate_cost(entry_price=100.0, exit_price=110.0, lot_size=50, instrument="INDEX_OPTION_BUY", is_long=True)
    
    # STT should be on sell side premium: 110 * 50 * 0.000625 = 3.4375
    assert abs(cost.stt - 3.4375) < 0.01
    
    # Brokerage is 40
    assert cost.brokerage == 40.0
    
    # Stamp duty on buy side: 100 * 50 * 0.00003 = 0.15
    assert abs(cost.stamp - 0.15) < 0.01
    
    # Exchange on both: (100+110) * 50 * 0.0005 = 5.25
    assert abs(cost.exchange - 5.25) < 0.01
    
    # Total should be around 57 rupees.
    assert 50 < cost.total < 60

def test_cost_model_option_buy_loss():
    model = IndianDerivativesCostModel()
    
    # Buy at 100, sell at 95. Lot size 50.
    cost = model.calculate_cost(entry_price=100.0, exit_price=95.0, lot_size=50, instrument="INDEX_OPTION_BUY", is_long=True)
    
    # STT on sell side premium: 95 * 50 * 0.000625 = 2.96875
    assert abs(cost.stt - 2.96875) < 0.01

def test_cost_model_future_buy():
    model = IndianDerivativesCostModel()
    
    # Buy at 20000, sell at 20050. Lot size 50.
    cost = model.calculate_cost(entry_price=20000.0, exit_price=20050.0, lot_size=50, instrument="INDEX_FUTURE", is_long=True)
    
    # STT on sell side notional: 20050 * 50 * 0.000125 = 125.3125
    assert abs(cost.stt - 125.3125) < 0.01
    
    # Stamp duty on buy side: 20000 * 50 * 0.00002 = 20.0
    assert abs(cost.stamp - 20.0) < 0.01
