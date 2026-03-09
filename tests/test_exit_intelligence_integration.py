from types import SimpleNamespace

from core.exit_intelligence import ExitAction, evaluate_exit


def _cfg(**overrides):
    base = {
        "ALLOW_STALE_LTP": False,
        "EXIT_INTEL_ACTION_COOLDOWN_SEC": 5.0,
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


def _run_replay(prices: list[float]):
    cfg = _cfg()
    pos = {
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
    now_ts = 100.0
    actions: list[str] = []
    sl_series: list[float] = [float(pos["current_sl"])]
    for px in prices:
        decision = evaluate_exit(
            dict(pos),
            {
                "ltp": float(px),
                "atr": None,
                "quote_age_sec": 0.2,
                "spread_pct": 0.002,
                "feed_state": "OK",
                "momentum": 0.01,
            },
            now_ts=now_ts,
            cfg=cfg,
        )
        actions.append(decision.action.value)
        if decision.state_patch:
            pos.update(decision.state_patch)
        if "current_sl" in decision.state_patch:
            sl_series.append(float(decision.state_patch["current_sl"]))
        if decision.action == ExitAction.PARTIAL_EXIT:
            rem = int(pos.get("remaining_qty_units", 0) or 0)
            qty = int(decision.exit_qty_units or 0)
            pos["remaining_qty_units"] = max(rem - qty, 0)
        elif decision.action == ExitAction.FULL_EXIT:
            pos["remaining_qty_units"] = 0
            break
        now_ts += 5.0
    return actions, pos, sl_series


def test_replay_deterministic_and_no_double_full_exit():
    prices = [100.0, 101.3, 102.8, 104.0, 107.0, 109.0, 110.2, 109.5]
    actions_a, pos_a, sl_a = _run_replay(prices)
    actions_b, pos_b, sl_b = _run_replay(prices)

    assert actions_a == actions_b
    assert pos_a == pos_b
    assert sl_a == sl_b
    assert actions_a.count(ExitAction.FULL_EXIT.value) <= 1
    assert int(pos_a["remaining_qty_units"]) == 0


def test_replay_never_widens_stop_for_buy_side():
    prices = [100.0, 101.1, 101.6, 102.5, 103.0, 102.9]
    _, _, sl_series = _run_replay(prices)
    assert sl_series == sorted(sl_series)
