from core.position_state_engine import (
    apply_exit_action,
    initialize_position_state,
    update_position_state,
)


def _seed_state():
    return initialize_position_state(
        fill={"trade_id": "T1", "fill_price": 100.0, "qty": 10},
        candidate={
            "trade_id": "T1",
            "symbol": "NIFTY",
            "side": "BUY",
            "selected_playbook": "breakout_continuation",
            "entry": 100.0,
            "execution_entry": 100.0,
            "stop_loss": 90.0,
            "target": 120.0,
            "qty": 10,
        },
        now_ts=1_700_000_000.0,
    )


def test_update_position_state_tracks_mfe_and_mae():
    state = _seed_state()
    state = update_position_state(state, {"last_price": 108.0}, now_ts=1_700_000_001.0)
    assert state.mfe_r > 0.0
    assert state.high_watermark == 108.0

    state = update_position_state(state, {"last_price": 95.0}, now_ts=1_700_000_002.0)
    assert state.mae_r < 0.0
    assert state.low_watermark == 95.0


def test_apply_exit_action_tp1_not_repeated():
    state = _seed_state()
    state = apply_exit_action(
        state,
        {"action": "PARTIAL_EXIT", "exit_fraction": 0.5, "reason": "tp1_hit"},
        now_ts=1_700_000_010.0,
    )
    assert state.tp1_done is True
    assert state.realized_qty == 5
    assert state.remaining_qty == 5

    state = apply_exit_action(
        state,
        {"action": "PARTIAL_EXIT", "exit_fraction": 0.5, "reason": "tp1_hit"},
        now_ts=1_700_000_011.0,
    )
    assert state.realized_qty == 5
    assert state.remaining_qty == 5


def test_apply_exit_action_move_stop_only_once_for_same_stop():
    state = _seed_state()
    state = apply_exit_action(
        state,
        {"action": "MOVE_STOP", "new_stop": 100.0, "reason": "move_to_be"},
        now_ts=1_700_000_020.0,
    )
    assert state.breakeven_done is True
    assert state.current_stop == 100.0

    state = apply_exit_action(
        state,
        {"action": "MOVE_STOP", "new_stop": 100.0, "reason": "move_to_be"},
        now_ts=1_700_000_021.0,
    )
    assert state.current_stop == 100.0


def test_apply_exit_action_full_exit_closes_position():
    state = _seed_state()
    state = apply_exit_action(
        state,
        {"action": "FULL_EXIT", "exit_fraction": 1.0, "reason": "hard_exit"},
        now_ts=1_700_000_030.0,
    )
    assert state.status == "CLOSED"
    assert state.remaining_qty == 0
    assert state.realized_qty == state.qty

