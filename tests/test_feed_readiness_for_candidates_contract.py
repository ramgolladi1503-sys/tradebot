import json

from core.feed_readiness_for_candidates import (
    READINESS_STATE_BLOCKED,
    READINESS_STATE_READY,
    READINESS_STATE_WARMING_UP,
    build_feed_readiness_for_candidates_contract,
)


def _supervisor(**overrides):
    payload = {
        "state": "WARMING_UP",
        "reason_code": "WARMING_UP",
        "warmup_clean_cycles": 0,
        "warmup_required_clean_cycles": 3,
    }
    payload.update(overrides)
    return payload


def _fresh_token():
    return {
        "symbol": "NIFTY",
        "expected_token": "12345",
        "observed_token": "12345",
        "tick_age_sec": 0.4,
    }


def test_candidate_contract_reports_warming_up_until_clean_cycles_complete():
    contract = build_feed_readiness_for_candidates_contract(_supervisor())

    assert contract.readiness_state == READINESS_STATE_WARMING_UP
    assert contract.ready is False
    assert contract.candidate_generation_allowed is False
    assert contract.clean_cycles_remaining == 3
    assert contract.is_order_action is False
    assert contract.broker_api_called is False


def test_candidate_contract_reports_ready_once_supervisor_is_candidate_ready():
    contract = build_feed_readiness_for_candidates_contract(
        _supervisor(
            state="CANDIDATE_READY",
            reason_code="CANDIDATE_READY",
            warmup_clean_cycles=3,
            warmup_required_clean_cycles=3,
        )
    )

    payload = contract.to_payload()

    assert contract.readiness_state == READINESS_STATE_READY
    assert contract.ready is True
    assert contract.candidate_generation_allowed is True
    assert contract.clean_cycles_remaining == 0
    assert payload["ready"] is True
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False


def test_candidate_contract_blocks_auth_and_restart_immediately():
    auth = build_feed_readiness_for_candidates_contract(
        _supervisor(state="AUTH_REQUIRED", reason_code="AUTH_REQUIRED")
    )
    restart = build_feed_readiness_for_candidates_contract(
        _supervisor(state="RESTART_REQUIRED", reason_code="RESTART_REQUIRED")
    )

    assert auth.readiness_state == READINESS_STATE_BLOCKED
    assert restart.readiness_state == READINESS_STATE_BLOCKED
    assert "AUTH_REQUIRED" in auth.blockers
    assert "RESTART_REQUIRED" in restart.blockers


def test_candidate_contract_serializes_as_read_only_non_action():
    contract = build_feed_readiness_for_candidates_contract(
        _supervisor(state="CANDIDATE_READY", warmup_clean_cycles=3, warmup_required_clean_cycles=3)
    )
    payload = json.loads(json.dumps(contract.to_payload(), sort_keys=True))

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["metadata"]["does_not_score_edge"] is True


def test_candidate_contract_blocks_stale_token_evidence():
    contract = build_feed_readiness_for_candidates_contract(
        {
            "feed_supervisor": _supervisor(state="CANDIDATE_READY", warmup_clean_cycles=3, warmup_required_clean_cycles=3),
            "token_evidence": dict(_fresh_token(), tick_age_sec=9.0),
        }
    )

    assert contract.readiness_state == READINESS_STATE_BLOCKED
    assert contract.candidate_generation_allowed is False
    assert any("EXACT_OPTION_TOKEN_FRESHNESS" in blocker for blocker in contract.blockers)


def test_candidate_contract_allows_fresh_token_evidence():
    contract = build_feed_readiness_for_candidates_contract(
        {
            "feed_supervisor": _supervisor(state="CANDIDATE_READY", warmup_clean_cycles=3, warmup_required_clean_cycles=3),
            "token_evidence": _fresh_token(),
        }
    )

    assert contract.readiness_state == READINESS_STATE_READY
    assert contract.candidate_generation_allowed is True
    assert contract.metadata["uses_exact_option_token_freshness"] is True
