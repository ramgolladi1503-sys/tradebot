from pathlib import Path

import pytest

from core.runtime_call_path_audit import (
    audit_repository_runtime_call_path,
    audit_runtime_call_path,
)


_VALID_ORCHESTRATOR = """
def cycle(self, market_data):
    trade, trace = self.trade_builder.build_with_trace(market_data)
    self.risk_state.approve(trade)
    approval_status(trade.trade_id)
    self.risk_engine.evaluate_trade({}, trade=trade)
    self.execution_guard.evaluate(trade, {})
    self.execution_router.execute(trade, 1, 2, 3)
"""

_VALID_TRADE_BUILDER = """
def build(candidates):
    best, ranked = select_best_opportunity(candidates)
    annotate_ranked_opportunities(candidates)
    return best
"""


def test_valid_runtime_call_path_passes():
    audit = audit_runtime_call_path(_VALID_ORCHESTRATOR, _VALID_TRADE_BUILDER)
    assert audit.passed is True
    assert audit.errors == ()
    assert [item.call_name for item in audit.ordered_execution_path] == [
        "self.trade_builder.build_with_trace",
        "self.risk_state.approve",
        "approval_status",
        "self.risk_engine.evaluate_trade",
        "self.execution_guard.evaluate",
        "self.execution_router.execute",
    ]
    assert audit.selector_call_count == 1
    assert audit.canonical_ui_ranker_called_by_orchestrator is False
    assert audit.to_payload()["broker_api_called"] is False
    assert audit.to_payload()["is_order_action"] is False


def test_execution_before_manual_approval_is_rejected():
    unsafe_source = """
def cycle(self, market_data):
    trade, trace = self.trade_builder.build_with_trace(market_data)
    self.risk_state.approve(trade)
    self.execution_router.execute(trade, 1, 2, 3)
    approval_status(trade.trade_id)
    self.risk_engine.evaluate_trade({}, trade=trade)
    self.execution_guard.evaluate(trade, {})
"""
    audit = audit_runtime_call_path(unsafe_source, _VALID_TRADE_BUILDER)
    assert audit.passed is False
    assert "runtime_call_order_invalid" in audit.errors


def test_missing_trade_builder_selector_is_rejected():
    audit = audit_runtime_call_path(
        _VALID_ORCHESTRATOR,
        "def build(candidates):\n    return candidates[0]\n",
    )
    assert audit.passed is False
    assert "trade_builder_execution_selector_missing" in audit.errors


def test_ui_ranker_in_execution_orchestrator_is_rejected():
    source = _VALID_ORCHESTRATOR + "\nbuild_ranked_opportunity_report({})\n"
    audit = audit_runtime_call_path(source, _VALID_TRADE_BUILDER)
    assert audit.passed is False
    assert "ui_only_canonical_ranker_called_from_execution_orchestrator" in audit.errors


def test_repository_runtime_call_path_is_proven():
    if not Path("core/orchestrator.py").exists():
        pytest.skip("repository orchestrator fixture unavailable")
    audit = audit_repository_runtime_call_path(".")
    assert audit.passed is True
    assert audit.errors == ()
    assert audit.selector_call_count >= 1
    assert audit.advisory_rank_call_count >= 1
    assert audit.canonical_ui_ranker_called_by_orchestrator is False
    line_numbers = [item.line_number for item in audit.ordered_execution_path]
    assert line_numbers == sorted(line_numbers)
