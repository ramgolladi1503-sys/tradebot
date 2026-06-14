from core.sim_pnl import simulate_pnl, simulate_row, delta_key


def test_sim_pnl_buy():
    pnl = simulate_pnl(entry=100.0, side="BUY", lot_size=50, deltas=[-20, 10])
    assert pnl[delta_key(-20)] == -1000.0
    assert pnl[delta_key(10)] == 500.0


def test_sim_pnl_sell():
    pnl = simulate_pnl(entry=100.0, side="SELL", lot_size=25, deltas=[-10, 20])
    assert pnl[delta_key(-10)] == 250.0
    assert pnl[delta_key(20)] == -500.0


def test_unresolved_contract_returns_na():
    row = {
        "symbol": "BANKNIFTY",
        "side": "BUY",
        "entry": 100.0,
        "expiry_date": None,
        "instrument_token": None,
        "instrument_id": None,
        "status": "PLANNING",
    }
    out = simulate_row(row, meta_map=None, deltas=[-5, 5])
    assert out["sim_reason"] == "unresolved_contract"
    assert out[delta_key(-5)] is None
    assert out[delta_key(5)] is None


def test_simulation_only_when_active():
    row = {
        "symbol": "NIFTY",
        "side": "BUY",
        "entry": 100.0,
        "fill_price": 100.0,
        "expiry_date": "2026-02-27",
        "instrument_token": 12345,
        "instrument_id": "NIFTY26FEB100CE",
        "status": "PLANNING",
    }
    out = simulate_row(row, meta_map=None, deltas=[-5, 5])
    assert out["sim_reason"] == "waiting_for_entry"
    assert out[delta_key(-5)] is None
    row["status"] = "ACTIVE"
    out_active = simulate_row(row, meta_map=None, deltas=[-5, 5])
    assert out_active["sim_reason"] is None
    assert out_active[delta_key(-5)] == -325.0
