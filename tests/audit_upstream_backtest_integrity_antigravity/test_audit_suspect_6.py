import pytest
from core.fill_model import FillModel

@pytest.mark.xfail(strict=True, reason="bug confirmed")
def test_suspect_6_slippage_not_applied():
    fm = FillModel()
    order = {'side': 'BUY', 'symbol': 'TEST', 'qty': 10000, 'limit_price': 100.0}
    market = {'bid': 90.0, 'ask': 100.0, 'ask_qty': 10, 'volume': 10}
    
    res = fm.simulate(order, market, 'test')
    
    slippage_bp = res['slippage_bp']
    fill_price = res['fill_price']
    
    expected_fill_price = 100.0 * (1 + slippage_bp / 10000.0)
    
    # Intended contract: slippage must be correctly applied to the final fill price
    assert fill_price == expected_fill_price, "Intended contract: Must apply computed slippage_bp to the final fill_price"
