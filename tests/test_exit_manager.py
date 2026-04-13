from core.exit_manager import evaluate_exit_action


def test_exit_manager_takes_tp1_at_one_r():
    position = {
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "playbook": "breakout_continuation",
        "tp1_done": False,
    }
    market = {"last_price": 105.0, "volatility": 0.5}

    action = evaluate_exit_action(position, market)

    assert action.action == "PARTIAL_EXIT"
    assert action.reason == "tp1_hit"
    assert action.exit_fraction == 0.5


def test_exit_manager_moves_stop_to_breakeven_after_1_2r():
    position = {
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "playbook": "breakout_continuation",
        "tp1_done": True,
    }
    market = {"last_price": 106.0, "volatility": 0.5}

    action = evaluate_exit_action(position, market)

    assert action.action == "MOVE_STOP"
    assert action.new_stop == 100.0
    assert action.reason == "move_to_be"


def test_exit_manager_stall_exit_on_low_volatility_profit():
    position = {
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "playbook": "profile_rejection",
        "tp1_done": True,
    }
    market = {"last_price": 103.0, "volatility": 0.1}

    action = evaluate_exit_action(position, market)

    assert action.action == "PARTIAL_EXIT"
    assert action.reason == "stall_exit"


def test_exit_manager_full_exit_on_stop_breach():
    position = {
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "playbook": "breakout_continuation",
        "tp1_done": False,
    }
    market = {"last_price": 94.0, "volatility": 0.5}

    action = evaluate_exit_action(position, market)

    assert action.action == "FULL_EXIT"
    assert action.reason == "stop_hit"

