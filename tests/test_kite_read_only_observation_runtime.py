import json
import sys

import pytest

from core.kite_read_only_observation_runtime import (
    BrokerWriteFirewall,
    assert_import_boundary,
    safety_contract,
    safe_environment,
)


def test_safe_environment_overwrites_inherited_live_values():
    env = safe_environment({
        "TRADING_MODE": "LIVE",
        "EXECUTION_MODE": "LIVE",
        "LIVE_BROKER_ADAPTER_ACTIVE": "1",
        "ALLOW_LIVE_ORDERS": "1",
    })
    contract = safety_contract(env, child_command=[sys.executable])
    assert contract["resolved_trading_mode"] == "SIM"
    assert contract["resolved_execution_mode"] == "SIM"
    assert contract["live_broker_adapter_active"] is False
    assert contract["broker_write_authority"] is False
    assert contract["order_authority"] is False
    assert "TRADING_MODE" in contract["unsafe_inherited_values"]


def test_import_boundary_has_no_broker_or_execution_modules():
    assert_import_boundary()


def test_broker_write_firewall_records_and_rejects(tmp_path):
    firewall = BrokerWriteFirewall(tmp_path / "safety.jsonl")
    with pytest.raises(RuntimeError, match="SAFETY_BLOCKER_BROKER_WRITE_ATTEMPT"):
        firewall.reject("place_order")
    row = json.loads((tmp_path / "safety.jsonl").read_text().strip())
    assert row["method"] == "place_order"


def test_safe_environment_disables_paper_and_live_execution():
    env = safe_environment({})
    contract = safety_contract(env, child_command=[sys.executable])
    assert contract["paper_execution_allowed"] is False
    assert contract["live_execution_allowed"] is False
    assert contract["manual_approval_cannot_route_orders"] is True
