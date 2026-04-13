from core.position_state_engine import initialize_position_state
from core.position_state_store import load_position_state, save_position_state


def test_position_state_store_round_trip(tmp_path):
    state = initialize_position_state(
        fill={"trade_id": "T2", "fill_price": 210.5, "qty": 3},
        candidate={
            "trade_id": "T2",
            "symbol": "BANKNIFTY",
            "side": "BUY",
            "selected_playbook": "profile_rejection",
            "entry": 210.5,
            "stop_loss": 190.0,
            "target": 250.0,
            "qty": 3,
        },
        now_ts=1_700_000_100.0,
    )
    path = tmp_path / "position_state" / "T2.json"
    save_position_state(path, state)

    loaded = load_position_state(path)
    assert loaded is not None
    assert loaded.trade_id == "T2"
    assert loaded.symbol == "BANKNIFTY"
    assert loaded.playbook == "profile_rejection"
    assert loaded.fill_price == 210.5
    assert loaded.remaining_qty == 3

