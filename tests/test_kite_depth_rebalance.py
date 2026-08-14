import core.kite_depth_ws as ws


def test_exact_registry_rejects_same_count_wrong_identity_and_partial_state():
    assert ws._reconcile_rebalance_intended_tokens(
        reason="atm_shift_steps=1.00",
        current_tokens=[1, 2, 3],
        desired_tokens=[1, 2, 3],
        actual_tokens=[1, 2, 4],
        pending_tokens=False,
    ) == ([1, 2, 3], False)
    assert ws._reconcile_rebalance_intended_tokens(
        reason="atm_shift_steps=1.00",
        current_tokens=[1, 2, 3],
        desired_tokens=[1, 2, 3],
        actual_tokens=[1, 2],
        pending_tokens=False,
    ) == ([1, 2, 3], False)
    assert ws._reconcile_rebalance_intended_tokens(
        reason="atm_shift_steps=1.00",
        current_tokens=[1, 2, 3],
        desired_tokens=[1, 2, 3],
        actual_tokens=[1, 2, 3],
        pending_tokens=False,
    ) == ([1, 2, 3], True)


def test_freshness_addition_commits_exact_desired_registry_after_success():
    assert ws._reconcile_rebalance_intended_tokens(
        reason="stale_option_prune_refresh",
        current_tokens=[1, 2, 3],
        desired_tokens=[1, 2, 3, 4, 5],
        actual_tokens=[1, 2, 3, 4, 5],
        pending_tokens=False,
    ) == ([1, 2, 3, 4, 5], True)
    assert ws._reconcile_rebalance_intended_tokens(
        reason="stale_option_prune_refresh",
        current_tokens=[1, 2, 3],
        desired_tokens=[1, 2, 3, 4, 5],
        actual_tokens=[1, 2, 3, 4],
        pending_tokens=True,
    ) == ([1, 2, 3], False)


def test_freshness_refresh_reconciliation_uses_post_apply_actual_set():
    actual = [1, 2, 3, 215731205, 216159237]
    assert ws._reconcile_rebalance_intended_tokens(
        reason="stale_option_prune_refresh",
        current_tokens=[1, 2, 3],
        desired_tokens=actual,
        actual_tokens=actual,
        pending_tokens=False,
    ) == (actual, True)


def test_rebalance_triggers_on_second_build_when_atm_shifts():
    first = ws._compute_rebalance_decision(
        current_tokens={256265, 101, 102, 777001},
        desired_tokens={256265, 101, 102},
        sticky_tokens={777001},
        underlying_tokens={256265},
        last_rebalance_ts=0.0,
        now_ts=60.0,
        cooldown_sec=60.0,
        threshold_steps=1.0,
        last_atm_by_symbol={"NIFTY": 22000},
        next_atm_by_symbol={"NIFTY": 22000},
        step_by_symbol={"NIFTY": 50.0},
    )
    assert first["should_rebalance"] is False

    decision = ws._compute_rebalance_decision(
        current_tokens={256265, 101, 102, 777001},
        desired_tokens={256265, 103, 104},
        sticky_tokens={777001},
        underlying_tokens={256265},
        last_rebalance_ts=0.0,
        now_ts=120.0,
        cooldown_sec=60.0,
        threshold_steps=1.0,
        last_atm_by_symbol={"NIFTY": 22000},
        next_atm_by_symbol={"NIFTY": 22050},
        step_by_symbol={"NIFTY": 50.0},
    )

    assert decision["should_rebalance"] is True
    assert decision["subscribe_tokens"] == [103, 104]
    assert decision["unsubscribe_tokens"] == [101, 102]
    assert 256265 in decision["final_tokens"]
    assert 777001 in decision["final_tokens"]


def test_rebalance_is_blocked_by_cooldown_within_ttl():
    decision = ws._compute_rebalance_decision(
        current_tokens={256265, 101, 102},
        desired_tokens={256265, 103, 104},
        sticky_tokens=set(),
        underlying_tokens={256265},
        last_rebalance_ts=100.0,
        now_ts=120.0,
        cooldown_sec=60.0,
        threshold_steps=1.0,
        last_atm_by_symbol={"NIFTY": 22000},
        next_atm_by_symbol={"NIFTY": 22050},
        step_by_symbol={"NIFTY": 50.0},
    )

    assert decision["should_rebalance"] is False
    assert "cooldown_blocked" in decision["reason"]
    assert decision["cooldown_ok"] is False


def test_underlying_and_sticky_tokens_are_never_unsubscribed():
    decision = ws._compute_rebalance_decision(
        current_tokens={256265, 900001, 101, 102},
        desired_tokens={103, 104},
        sticky_tokens={900001},
        underlying_tokens={256265},
        last_rebalance_ts=0.0,
        now_ts=120.0,
        cooldown_sec=60.0,
        threshold_steps=1.0,
        last_atm_by_symbol={"NIFTY": 22000},
        next_atm_by_symbol={"NIFTY": 22050},
        step_by_symbol={"NIFTY": 50.0},
    )

    assert 256265 not in decision["unsubscribe_tokens"]
    assert 900001 not in decision["unsubscribe_tokens"]
    assert 256265 in decision["final_tokens"]
    assert 900001 in decision["final_tokens"]
