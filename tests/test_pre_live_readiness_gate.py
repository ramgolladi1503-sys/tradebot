from __future__ import annotations

import json
from types import SimpleNamespace

from scripts import pre_live_readiness_gate as gate


def _cfg(**overrides):
    base = {
        "EXECUTION_MODE": "LIVE",
        "SYMBOLS": ["NIFTY"],
        "ALLOW_FALLBACK_EXECUTION": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _deps(**overrides):
    values = {
        "config": _cfg(),
        "market_open": True,
        "credential_checker": lambda: {"ok": True, "api_key_present": True, "access_token_present": True},
        "auth_health_loader": lambda: {"ok": True, "auth_state": "OK"},
        "auth_latch_loader": lambda: {"auth_state": {"status": "OK"}, "auth_runtime_guard": {"auth_ok": True}},
        "token_resolver": lambda symbols: (
            [1, 2, 3],
            [
                {
                    "symbol": "NIFTY",
                    "resolved_option_count": 2,
                    "final_option_count": 2,
                    "option_coverage_status": "FULL",
                }
            ],
        ),
        "feed_breaker_loader": lambda: {"tripped": False},
        "lock_checker": lambda: {"ok": True},
        "indicator_loader": lambda: {"indicators_ready": True, "blockers": []},
        "now_epoch": 100.0,
    }
    values.update(overrides)
    return gate.PreLiveReadinessDependencies(**values)


def _run(**overrides):
    return gate.evaluate_pre_live_readiness(mode="LIVE", dependencies=_deps(**overrides))


def test_fallback_execution_enabled_in_live_fails():
    payload = _run(config=_cfg(ALLOW_FALLBACK_EXECUTION=True))

    assert payload["outcome"] == gate.FAIL
    assert payload["exit_code"] == gate.EXIT_FAIL
    assert payload["blockers"] == ["fallback_execution_enabled_live"]
    assert payload["checks"]["fallback_execution"]["enabled"] is True


def test_zero_token_universe_fails():
    payload = _run(
        token_resolver=lambda symbols: (
            [256265],
            [
                {
                    "symbol": "NIFTY",
                    "resolved_option_count": 0,
                    "final_option_count": 0,
                    "option_coverage_status": "ZERO",
                    "option_fail_reason": "option_tokens_zero",
                }
            ],
        )
    )

    assert payload["outcome"] == gate.FAIL
    assert payload["blockers"] == ["token_universe_zero"]
    assert payload["checks"]["token_universe"]["option_token_count"] == 0


def test_invalid_auth_and_auth_latch_fail():
    payload = _run(
        auth_health_loader=lambda: {"ok": False, "auth_state": "AUTH_REQUIRED", "error": "invalid_session"},
        auth_latch_loader=lambda: {"auth_state": {"status": "AUTH_REQUIRED", "reason": "invalid_session"}},
    )

    assert payload["outcome"] == gate.FAIL
    assert payload["blockers"] == ["auth_invalid", "auth_required_latch_active"]
    assert payload["checks"]["auth_latch"]["active"] is True


def test_valid_config_token_universe_and_no_breaker_passes_when_market_open():
    payload = _run()

    assert payload["outcome"] == gate.PASS
    assert payload["ready"] is True
    assert payload["blockers"] == []
    assert payload["checks"]["feed_circuit_breaker"]["tripped"] is False


def test_market_closed_returns_pending_tick_proof_without_false_pass():
    payload = _run(market_open=False)

    assert payload["outcome"] == gate.MARKET_CLOSED_PENDING_TICK_PROOF
    assert payload["ready"] is False
    assert payload["exit_code"] == gate.EXIT_OK
    assert payload["live_tick_proof_obtained"] is False
    assert "market_closed_pending_live_tick_proof" in payload["warnings"]


def test_json_contains_exact_blocker_list():
    payload = _run(
        config=_cfg(ALLOW_FALLBACK_EXECUTION=True),
        auth_health_loader=lambda: {"ok": False, "auth_state": "FAILED"},
        token_resolver=lambda symbols: (
            [],
            [{"symbol": "NIFTY", "resolved_option_count": 0, "final_option_count": 0}],
        ),
    )
    parsed = json.loads(json.dumps(payload, sort_keys=True))

    assert parsed["blockers"] == [
        "auth_invalid",
        "fallback_execution_enabled_live",
        "token_universe_zero",
    ]
    assert parsed["outcome"] == gate.FAIL
    assert parsed["checks"]["token_universe"]["option_token_count"] == 0
