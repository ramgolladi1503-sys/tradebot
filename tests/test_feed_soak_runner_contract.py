from __future__ import annotations

from core.feed_soak_runner_contract import (
    SOAK_RUNNER_BLOCKED,
    SOAK_RUNNER_READY,
    build_feed_soak_runner_contract,
)


def _payload(**overrides):
    base = {
        "runner_state": "READY",
        "soak_minutes": 60,
        "warmup_minutes": 15,
        "required_clean_cycles": 2,
        "journal_path": "/tmp/feed-soak.jsonl",
        "output_path": "/tmp/feed-soak-report.json",
        "checks_state": "GREEN",
        "controller_state": "RUNNING",
    }
    base.update(overrides)
    return base


def test_feed_soak_runner_contract_is_read_only_and_non_action():
    contract = build_feed_soak_runner_contract(_payload())

    payload = contract.to_payload()

    assert contract.is_order_action is False
    assert contract.broker_api_called is False
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert contract.contract_state == SOAK_RUNNER_READY


def test_feed_soak_runner_blocks_when_required_inputs_missing():
    contract = build_feed_soak_runner_contract(_payload(journal_path="", output_path=""))

    assert contract.contract_state == SOAK_RUNNER_BLOCKED
    assert "JOURNAL_PATH_REQUIRED" in contract.blockers
    assert "OUTPUT_PATH_REQUIRED" in contract.blockers


def test_feed_soak_runner_blocks_on_bad_checks():
    contract = build_feed_soak_runner_contract(_payload(checks_state="red"))

    assert contract.contract_state == SOAK_RUNNER_BLOCKED
    assert "CHECKS_NOT_GREEN" in contract.blockers
