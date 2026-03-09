from types import SimpleNamespace

from core.exit_intelligence import ExitAction, evaluate_exit


def _cfg(**overrides):
    base = {
        "ALLOW_STALE_LTP": False,
        "EXIT_INTEL_ACTION_COOLDOWN_SEC": 15.0,
        "EXIT_INTEL_MAX_QUOTE_AGE_SEC": 2.5,
        "EXIT_INTEL_PROFIT_PROTECT_TRIGGER_PCT": 0.01,
        "EXIT_INTEL_BREAK_EVEN_BUFFER_PCT": 0.0005,
        "EXIT_INTEL_TRAIL_USE_ATR": False,
        "EXIT_INTEL_TRAIL_ATR_MULT": 0.8,
        "EXIT_INTEL_TRAIL_OFFSET_PCT": 0.005,
        "EXIT_INTEL_TRAIL_STEP_PCT": 0.002,
        "EXIT_INTEL_STALL_TARGET_PCT": 0.90,
        "EXIT_INTEL_STALL_SECONDS": 45.0,
        "EXIT_INTEL_STALL_MOMENTUM_BREAK": -0.001,
        "EXIT_INTEL_STALL_ACTION": "PARTIAL_EXIT",
        "EXIT_INTEL_PARTIAL_EXIT_FRACTION": 0.5,
        "MAX_HOLD_MINUTES": 60,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _position(**overrides):
    base = {
        "side": "BUY",
        "entry_price": 100.0,
        "current_sl": 95.0,
        "current_tp": 110.0,
        "best_price_seen": 100.0,
        "best_price_ts": 0.0,
        "exit_intel_phase": "INIT",
        "stall_counter": 0,
        "last_action_ts": 0.0,
        "remaining_qty_units": 10,
        "qty_units": 10,
        "entry_time": 0.0,
        "max_hold_sec": 3600.0,
        "reason_codes": [],
        "last_price": 100.0,
    }
    base.update(overrides)
    return base


def _snapshot(**overrides):
    base = {
        "ltp": 100.0,
        "atr": None,
        "quote_age_sec": 0.5,
        "spread_pct": 0.002,
        "feed_state": "OK",
        "momentum": 0.01,
        "momentum_break": False,
    }
    base.update(overrides)
    return base


def test_profit_protect_tightens_stop_to_break_even_plus_buffer():
    decision = evaluate_exit(
        _position(),
        _snapshot(ltp=101.4),
        now_ts=100.0,
        cfg=_cfg(),
    )
    assert decision.action == ExitAction.MODIFY_PLAN
    assert "profit_protect_be" in decision.reason_codes
    assert float(decision.state_patch["current_sl"]) > 95.0


def test_profit_protect_not_triggered_below_threshold():
    decision = evaluate_exit(
        _position(),
        _snapshot(ltp=100.7),
        now_ts=100.0,
        cfg=_cfg(EXIT_INTEL_TRAIL_STEP_PCT=1.0),
    )
    assert decision.action == ExitAction.NOOP
    assert "profit_protect_be" not in decision.reason_codes


def test_trail_upgrades_stop_when_new_best_exceeds_step():
    decision = evaluate_exit(
        _position(),
        _snapshot(ltp=103.0),
        now_ts=100.0,
        cfg=_cfg(EXIT_INTEL_PROFIT_PROTECT_TRIGGER_PCT=0.50),
    )
    assert decision.action == ExitAction.MODIFY_PLAN
    assert "trail_upgrade" in decision.reason_codes
    assert float(decision.state_patch["current_sl"]) > 95.0


def test_trail_noop_when_best_delta_below_step_threshold():
    decision = evaluate_exit(
        _position(),
        _snapshot(ltp=100.1),
        now_ts=100.0,
        cfg=_cfg(EXIT_INTEL_PROFIT_PROTECT_TRIGGER_PCT=0.50),
    )
    assert decision.action == ExitAction.NOOP
    assert "trail_upgrade" not in decision.reason_codes


def test_stall_detection_triggers_partial_exit():
    decision = evaluate_exit(
        _position(best_price_seen=109.5, best_price_ts=10.0),
        _snapshot(ltp=109.2, momentum=-0.01),
        now_ts=100.0,
        cfg=_cfg(
            EXIT_INTEL_STALL_ACTION="PARTIAL_EXIT",
            EXIT_INTEL_PROFIT_PROTECT_TRIGGER_PCT=0.50,
            EXIT_INTEL_TRAIL_STEP_PCT=1.0,
        ),
    )
    assert decision.action == ExitAction.PARTIAL_EXIT
    assert decision.exit_qty_units > 0
    assert "stall_near_target" in decision.reason_codes


def test_stall_detection_triggers_full_exit_when_configured():
    decision = evaluate_exit(
        _position(best_price_seen=109.5, best_price_ts=10.0),
        _snapshot(ltp=109.2, momentum=-0.01),
        now_ts=100.0,
        cfg=_cfg(
            EXIT_INTEL_STALL_ACTION="FULL_EXIT",
            EXIT_INTEL_PROFIT_PROTECT_TRIGGER_PCT=0.50,
            EXIT_INTEL_TRAIL_STEP_PCT=1.0,
        ),
    )
    assert decision.action == ExitAction.FULL_EXIT
    assert decision.exit_qty_units == 10
    assert "stall_near_target" in decision.reason_codes
