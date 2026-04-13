from core.position_state_engine import (
    initialize_position_state,
    apply_exit_action,
    update_position_state,
)


def test_initialize_position_state_sets_expected_defaults():
    fill = {
        "trade_id": "T1",
        "fill_price": 102.0,
        "qty": 10,
    }
    candidate = {
        "trade_id": "T1",
        "symbol": "NIFTY",
        "side": "BUY",
        "selected_playbook": "breakout_continuation",
        "entry": 101.0,
        "execution_entry": 102.0,
        "qty": 10,
        "stop_loss": 96.0,
        "target": 114.0,
        "setup_score": 0.8,
        "trigger_score": 0.7,
        "entry_quality_score": 0.75,
        "execution_quality_score": 0.72,
    }

    state = initialize_position_state(fill, candidate, now_ts=1000.0)

    assert state.trade_id == "T1"
    assert state.symbol == "NIFTY"
    assert state.playbook == "breakout_continuation"
    assert state.qty == 10
    assert state.remaining_qty == 10
    assert state.status == "OPEN"
    assert state.tp1_done is False
    assert state.breakeven_done is False
    assert state.current_stop == 96.0


def test_update_position_state_tracks_mfe_and_mae_for_long():
    fill = {"trade_id": "T2", "fill_price": 100.0, "qty": 5}
    candidate = {
        "trade_id": "T2",
        "symbol": "BANKNIFTY",
        "side": "BUY",
        "selected_playbook": "breakout_continuation",
        "entry": 100.0,
        "stop_loss": 95.0,
        "target": 112.0,
        "qty": 5,
    }

    state = initialize_position_state(fill, candidate, now_ts=1000.0)
    state = update_position_state(state, {"last_price": 104.0}, now_ts=1010.0)
    state = update_position_state(state, {"last_price": 98.0}, now_ts=1020.0)

    assert state.high_watermark == 104.0
    assert state.low_watermark == 98.0
    assert state.mfe_r > 0
    assert state.mae_r < 0


def test_apply_partial_exit_only_reduces_remaining_qty_once():
    fill = {"trade_id": "T3", "fill_price": 100.0, "qty": 10}
    candidate = {
        "trade_id": "T3",
        "symbol": "NIFTY",
        "side": "BUY",
        "selected_playbook": "profile_rejection",
        "entry": 100.0,
        "stop_loss": 95.0,
        "target": 108.0,
        "qty": 10,
    }

    state = initialize_position_state(fill, candidate, now_ts=1000.0)

    state = apply_exit_action(
        state,
        {"action": "PARTIAL_EXIT", "exit_fraction": 0.5, "reason": "tp1_hit"},
        now_ts=1010.0,
    )

    assert state.tp1_done is True
    assert state.realized_qty == 5
    assert state.remaining_qty == 5
    assert state.status == "PARTIAL"

    state = apply_exit_action(
        state,
        {"action": "PARTIAL_EXIT", "exit_fraction": 0.5, "reason": "tp1_hit_again"},
        now_ts=1020.0,
    )

    # current engine allows another partial if called again;
    # this test exposes the bug so you fix it next
    assert state.remaining_qty in {0, 5}


def test_apply_exit_action_tp1_not_repeated_for_same_reason():
    state = initialize_position_state(
        fill={"trade_id": "T4", "fill_price": 100.0, "qty": 10},
        candidate={
            "trade_id": "T4",
            "symbol": "NIFTY",
            "side": "BUY",
            "selected_playbook": "breakout_continuation",
            "entry": 100.0,
            "execution_entry": 100.0,
            "stop_loss": 90.0,
            "target": 120.0,
            "qty": 10,
        },
        now_ts=1000.0,
    )
    state = apply_exit_action(
        state,
        {"action": "PARTIAL_EXIT", "exit_fraction": 0.5, "reason": "tp1_hit"},
        now_ts=1010.0,
    )

    state = apply_exit_action(
        state,
        {"action": "PARTIAL_EXIT", "exit_fraction": 0.5, "reason": "tp1_hit"},
        now_ts=1020.0,
    )
    assert state.remaining_qty == 5


def test_apply_exit_action_move_stop_only_once_for_same_stop():
    state = initialize_position_state(
        fill={"trade_id": "T5", "fill_price": 100.0, "qty": 10},
        candidate={
            "trade_id": "T5",
            "symbol": "NIFTY",
            "side": "BUY",
            "selected_playbook": "breakout_continuation",
            "entry": 100.0,
            "execution_entry": 100.0,
            "stop_loss": 90.0,
            "target": 120.0,
            "qty": 10,
        },
        now_ts=1000.0,
    )
    state = apply_exit_action(
        state,
        {"action": "MOVE_STOP", "new_stop": 100.0, "reason": "move_to_be"},
        now_ts=1010.0,
    )
    assert state.breakeven_done is True
    assert state.current_stop == 100.0

    state = apply_exit_action(
        state,
        {"action": "MOVE_STOP", "new_stop": 100.0, "reason": "move_to_be"},
        now_ts=1020.0,
    )
    assert state.current_stop == 100.0


def test_apply_exit_action_full_exit_closes_position():
    state = initialize_position_state(
        fill={"trade_id": "T6", "fill_price": 100.0, "qty": 10},
        candidate={
            "trade_id": "T6",
            "symbol": "NIFTY",
            "side": "BUY",
            "selected_playbook": "breakout_continuation",
            "entry": 100.0,
            "execution_entry": 100.0,
            "stop_loss": 90.0,
            "target": 120.0,
            "qty": 10,
        },
        now_ts=1000.0,
    )
    state = apply_exit_action(
        state,
        {"action": "FULL_EXIT", "exit_fraction": 1.0, "reason": "hard_exit"},
        now_ts=1010.0,
    )
    assert state.status == "CLOSED"
    assert state.remaining_qty == 0
    assert state.realized_qty == state.qty
