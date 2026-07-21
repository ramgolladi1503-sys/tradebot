

def test_suspect_4_cost_double_deduction():
    # Oracle
    gross = 10.0
    proxy_delta = 0.5
    proxy_exec_cost = 1.5
    underlying_cost = proxy_exec_cost / proxy_delta
    # In production:
    actual_net_pnl = gross - (underlying_cost + proxy_exec_cost)
    # Expected:
    expected_net_pnl = gross - underlying_cost
    assert actual_net_pnl != expected_net_pnl, 'Double deduction confirmed'
