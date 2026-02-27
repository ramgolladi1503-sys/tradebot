from core.sim_pnl import compute_row_live_pnl


def test_live_pnl_buy():
    row = {
        "status": "ACTIVE",
        "fill_price": 100,
        "live_ltp": 110,
        "side": "BUY",
        "lot_size": 50,
    }
    res = compute_row_live_pnl(row)
    assert res["pnl_1qty"] == 10.0
    assert res["pnl_1lot"] == 500.0


def test_live_pnl_sell():
    row = {
        "status": "ACTIVE",
        "fill_price": 100,
        "live_ltp": 90,
        "side": "SELL",
        "lot_size": 25,
    }
    res = compute_row_live_pnl(row)
    assert res["pnl_1qty"] == 10.0
    assert res["pnl_1lot"] == 250.0
