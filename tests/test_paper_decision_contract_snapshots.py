from __future__ import annotations

import json
from pathlib import Path

from core.paper_decision_orchestrator import build_paper_decision_report

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "paper_decision_contract"

EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version",
    "state",
    "read_only",
    "is_order_action",
    "append",
    "allowed_for_paper_order",
    "allowed_for_live_execution",
    "paper_intent_id",
    "selected_strategy_id",
    "symbol",
    "direction",
    "instrument_token",
    "tradingsymbol",
    "quantity",
    "entry_price",
    "estimated_notional",
    "blockers",
    "warnings",
    "reasons",
    "metadata",
}

DYNAMIC_KEYS = {"ts", "timestamp", "created_at", "updated_at", "run_id"}


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _selection(**overrides) -> dict:
    payload = {
        "schema_version": 1,
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "state": "SELECTED_FOR_PAPER",
        "selected_count": 1,
        "selected_strategy_ids": ["call_high"],
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def _intent(**overrides) -> dict:
    payload = {
        "schema_version": 1,
        "state": "PAPER_INTENT_READY",
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "paper_intent_id": "intent-clean",
        "ready_for_risk_review": True,
        "allowed_for_paper_order": False,
        "allowed_for_live_execution": False,
        "selected_strategy_id": "call_high",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "instrument_token": 12345,
        "tradingsymbol": "NIFTY26MAY22500CE",
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def _risk(**overrides) -> dict:
    payload = {
        "schema_version": 1,
        "state": "RISK_APPROVED",
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "allowed_for_paper_order": True,
        "allowed_for_live_execution": False,
        "paper_intent_id": "intent-clean",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "instrument_token": 12345,
        "tradingsymbol": "NIFTY26MAY22500CE",
        "quantity": 5,
        "entry_price": 100.0,
        "estimated_notional": 500.0,
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def _report(selection: dict | None, intent: dict | None, risk: dict | None) -> dict:
    return build_paper_decision_report(selection, intent, risk).to_dict()


def _assert_snapshot_contract(snapshot: dict) -> None:
    assert set(snapshot.keys()) == EXPECTED_TOP_LEVEL_KEYS
    assert snapshot["schema_version"] == 1
    assert snapshot["read_only"] is True
    assert snapshot["is_order_action"] is False
    assert snapshot["append"] is False
    assert snapshot["allowed_for_live_execution"] is False
    assert not DYNAMIC_KEYS.intersection(snapshot.keys())
    assert snapshot["metadata"] == {
        "orchestrator": "paper_decision_orchestrator_v1",
        "requires_paper_intent_contract": True,
        "requires_risk_decision": True,
        "requires_selection_policy": True,
        "scope": "read_only_no_order_creation_no_broker_calls_no_ledger_mutation",
    }


def test_clean_paper_ready_report_snapshot():
    actual = _report(_selection(), _intent(), _risk())

    assert actual == _fixture("clean_paper_ready_report")
    _assert_snapshot_contract(actual)
    assert actual["state"] == "PAPER_DECISION_APPROVED"
    assert actual["allowed_for_paper_order"] is True
    assert actual["quantity"] == 5


def test_fallback_blocked_report_snapshot():
    actual = _report(
        _selection(),
        _intent(
            state="PAPER_INTENT_BLOCKED",
            paper_intent_id="intent-fallback",
            ready_for_risk_review=False,
            blockers=["CONTRACT_FALLBACK_CANDIDATE", "CONTRACT_NOT_EXACT_MATCH"],
        ),
        _risk(
            state="RISK_BLOCKED",
            allowed_for_paper_order=False,
            paper_intent_id="intent-fallback",
            quantity=0,
            estimated_notional=0.0,
            blockers=["CONTRACT_FALLBACK_CANDIDATE", "RISK_QUANTITY_ZERO"],
        ),
    )

    assert actual == _fixture("fallback_blocked_report")
    _assert_snapshot_contract(actual)
    assert actual["allowed_for_paper_order"] is False
    assert "CONTRACT_FALLBACK_CANDIDATE" in actual["blockers"]


def test_risk_blocked_report_snapshot():
    actual = _report(
        _selection(),
        _intent(paper_intent_id="intent-risk-blocked"),
        _risk(
            state="RISK_BLOCKED",
            allowed_for_paper_order=False,
            paper_intent_id="intent-risk-blocked",
            quantity=0,
            estimated_notional=0.0,
            blockers=["DAILY_LOSS_LIMIT_REACHED", "RISK_SIZE_ZERO"],
        ),
    )

    assert actual == _fixture("risk_blocked_report")
    _assert_snapshot_contract(actual)
    assert actual["allowed_for_paper_order"] is False
    assert "DAILY_LOSS_LIMIT_REACHED" in actual["blockers"]


def test_empty_no_trade_report_snapshot():
    actual = _report(
        _selection(
            state="NO_TRADE",
            selected_count=0,
            selected_strategy_ids=[],
            blockers=["NO_RANKED_CANDIDATES"],
        ),
        None,
        None,
    )

    assert actual == _fixture("empty_no_trade_report")
    _assert_snapshot_contract(actual)
    assert actual["allowed_for_paper_order"] is False
    assert actual["paper_intent_id"] is None
    assert "NO_RANKED_CANDIDATES" in actual["blockers"]


def test_near_executable_wait_report_snapshot():
    actual = _report(
        _selection(
            state="WAIT",
            selected_count=0,
            selected_strategy_ids=[],
            warnings=["NEEDS_CONFIRMATION"],
        ),
        None,
        None,
    )

    assert actual == _fixture("near_executable_wait_report")
    _assert_snapshot_contract(actual)
    assert actual["allowed_for_paper_order"] is False
    assert actual["warnings"] == ["NEEDS_CONFIRMATION"]
