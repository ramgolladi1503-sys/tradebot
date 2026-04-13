from core.exit_manager import evaluate_exit_action


def _base_position(playbook: str):
    return {
        "entry_price": 100.0,
        "fill_price": 100.0,
        "initial_stop": 90.0,
        "current_stop": 90.0,
        "side": "BUY",
        "playbook": playbook,
        "status": "OPEN",
        "tp1_done": False,
        "breakeven_done": False,
        "trailing_active": False,
        "remaining_qty": 10,
        "qty": 10,
        "mfe_r": 0.0,
        "mae_r": 0.0,
    }


def test_breakout_holds_before_tp1_threshold():
    action = evaluate_exit_action(
        _base_position("breakout_continuation"),
        {"last_price": 108.0, "volatility": 0.3},
    )
    assert action.action == "HOLD"


def test_profile_rejection_takes_early_tp1():
    action = evaluate_exit_action(
        _base_position("profile_rejection"),
        {"last_price": 108.0, "volatility": 0.3},
    )
    assert action.action == "PARTIAL_EXIT"
    assert action.reason == "tp1_hit"


def test_move_stop_not_repeated_after_breakeven_done():
    position = _base_position("profile_rejection")
    position["breakeven_done"] = True
    action = evaluate_exit_action(
        position,
        {"last_price": 114.0, "volatility": 0.3},
    )
    assert action.action != "MOVE_STOP"


def test_full_exit_on_stop_hit():
    action = evaluate_exit_action(
        _base_position("breakout_continuation"),
        {"last_price": 89.0, "volatility": 0.3},
    )
    assert action.action == "FULL_EXIT"
    assert action.reason == "stop_hit"

