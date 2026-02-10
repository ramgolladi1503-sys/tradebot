from core.fill_model import FillModel


def test_same_inputs_same_run_id_identical_results():
    model = FillModel()
    order = {"side": "BUY", "symbol": "NIFTY", "qty": 20, "limit_price": 101.5}
    snap = {"bid": 100.0, "ask": 101.0, "bid_qty": 200, "ask_qty": 180, "volume": 10000, "vol_z": 0.8}
    run_id = "RUN-FILL-DET-1"

    r1 = model.simulate(order, snap, run_id)
    r2 = model.simulate(order, snap, run_id)

    assert r1 == r2


def test_limit_buy_above_ask_fills_below_bid_nofill():
    model = FillModel()
    snap = {"bid": 100.0, "ask": 101.0, "bid_qty": 300, "ask_qty": 300, "volume": 50000, "vol_z": 0.2}

    buy_cross = model.simulate(
        {"side": "BUY", "symbol": "NIFTY", "qty": 10, "limit_price": 102.0},
        snap,
        "RUN-FILL-BUY-CROSS",
    )
    buy_below_bid = model.simulate(
        {"side": "BUY", "symbol": "NIFTY", "qty": 10, "limit_price": 99.0},
        snap,
        "RUN-FILL-BUY-NOFILL",
    )

    assert buy_cross["status"] in ("FILLED", "PARTIAL")
    assert buy_cross["fill_qty"] > 0
    assert buy_below_bid["status"] == "NOFILL"
    assert buy_below_bid["fill_qty"] == 0


def test_large_order_partial_fill_is_deterministic():
    model = FillModel()
    order = {"side": "BUY", "symbol": "BANKNIFTY", "qty": 2000, "limit_price": 505.0}
    snap = {
        "bid": 500.0,
        "ask": 501.0,
        "bid_qty": 20,
        "ask_qty": 25,
        "volume": 1200,
        "oi": 8000,
        "volatility": 1.4,
    }

    r1 = model.simulate(order, snap, "RUN-PARTIAL-1")
    r2 = model.simulate(order, snap, "RUN-PARTIAL-1")

    assert r1 == r2
    assert r1["status"] == "PARTIAL"
    assert 0 < r1["fill_qty"] < order["qty"]
    assert r1["fill_price"] is not None
