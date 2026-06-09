from core.feed_soak_acceptance import (
    SOAK_ACCEPTANCE_BLOCKED,
    SOAK_ACCEPTANCE_READY,
    build_feed_soak_acceptance_contract,
)


def _payload(**overrides):
    base = {
        "runtime": {
            "feed_truth_state": "LIVE",
            "feed_truth_reason_code": "live",
            "process_restart_required": False,
            "recovery_blocked": False,
            "option_feed_block_reason_by_symbol": {},
            "feed_truth_reasons": [],
        },
        "feed_supervisor": {
            "state": "CANDIDATE_READY",
        },
    }
    base.update(overrides)
    return base


def test_soak_acceptance_is_read_only_and_non_action():
    contract = build_feed_soak_acceptance_contract(_payload())

    assert contract.acceptance_state == SOAK_ACCEPTANCE_READY
    assert contract.accepted is True
    assert contract.is_order_action is False
    assert contract.broker_api_called is False
    payload = contract.to_payload()
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False


def test_soak_acceptance_blocks_terminal_reactor_and_restart_required():
    reactor = build_feed_soak_acceptance_contract(
        _payload(runtime={
            "feed_truth_state": "RECOVERY_BLOCKED",
            "feed_truth_reason_code": "reactor_not_restartable_process_restart_required",
            "restart_failure_reason": "reactor_not_restartable_process_restart_required",
            "process_restart_required": True,
        })
    )

    assert reactor.acceptance_state == SOAK_ACCEPTANCE_BLOCKED
    assert "REACTOR_NOT_RESTARTABLE" in reactor.blockers
    assert "RESTART_REQUIRED" in reactor.blockers


def test_soak_acceptance_blocks_dead_and_stale_feed_and_bad_candidate_ready():
    dead = build_feed_soak_acceptance_contract(
        _payload(runtime={
            "feed_truth_state": "DEAD",
            "feed_truth_reason_code": "feed_unhealthy",
            "feed_truth_reasons": ["ltp_ticks_stale", "depth_ticks_stale"],
            "option_feed_block_reason_by_symbol": {"NIFTY": "NO_LIVE_OPTION_FEED"},
        })
    )

    assert dead.acceptance_state == SOAK_ACCEPTANCE_BLOCKED
    assert "DEAD_WITHOUT_RECOVERY" in dead.blockers
    assert "NO_LIVE_OPTION_FEED" in dead.blockers
    assert "PERSISTENT_STALE_FEED" in dead.blockers

    bad_ready = build_feed_soak_acceptance_contract(
        _payload(
            runtime={
                "feed_truth_state": "DEAD",
                "feed_truth_reason_code": "feed_unhealthy",
                "feed_truth_reasons": [],
                "option_feed_block_reason_by_symbol": {},
            },
            feed_supervisor={"state": "CANDIDATE_READY"},
        )
    )

    assert bad_ready.acceptance_state == SOAK_ACCEPTANCE_BLOCKED
    assert "CANDIDATE_READY_UNDER_BAD_FEED" in bad_ready.blockers
