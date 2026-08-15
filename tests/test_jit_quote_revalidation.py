import time
import pytest
from unittest.mock import patch, MagicMock

from config import config as cfg
from core.orchestrator import Orchestrator
from core.trade_schema import Trade
import core.market_data
import core.tick_store


@pytest.fixture
def orchestrator():
    orch = Orchestrator()
    orch.execution_guard = MagicMock()
    orch.execution_guard.evaluate.return_value = MagicMock(allowed=True, reason="ok", reason_code="ok", planning_only=False, context={})
    orch.portfolio = {"capital": 100000}
    orch.risk_engine = MagicMock()
    orch.risk_engine.size_trade.return_value = 1
    orch.risk_state = MagicMock()
    orch.execution_engine = MagicMock()
    orch._build_trade_ticket = MagicMock()

    # Mock heavy operations
    orch._update_decision_breakers = MagicMock()
    orch._update_pilot_unlock_clean_cycles = MagicMock()
    orch._evaluate_suggestions = MagicMock()
    orch._run_v2_shadow_pipeline = MagicMock()
    orch._maybe_run_suggestion_reliability_check = MagicMock()
    orch._refresh_decay_report = MagicMock()
    orch._apply_cycle_indicator_readiness_truth = MagicMock()
    orch._pilot_exec_degradation = MagicMock()
    return orch


@patch("core.tick_store.get_last_tick")
@patch("core.market_data.get_token_for_symbol")
@patch("core.orchestrator.update_execution")
@patch("core.orchestrator.send_trade_ticket")
@patch("core.orchestrator.fetch_live_market_data")
@patch("core.orchestrator.evaluate_slo_status")
@patch("core.orchestrator.risk_halt.is_halted")
@patch("core.orchestrator.build_live_indicator_readiness_report")
@patch("core.orchestrator.produce_and_store_market_snapshot")
@patch("core.orchestrator.produce_and_store_runtime_snapshots")
@patch("core.orchestrator._read_json_dict")
@patch("core.orchestrator._build_top_opportunities_payload")
@patch("core.orchestrator.evaluate_decision")
@patch("core.orchestrator._prepare_trade_for_review_queue")
def test_jit_quote_revalidation_blocks_stale_quote(
    mock_prepare,
    mock_eval_decision,
    mock_build_top,
    mock_read_json,
    mock_runtime_snap,
    mock_market_snap,
    mock_indicator_report,
    mock_is_halted,
    mock_slo_status,
    mock_fetch_live,
    mock_send_ticket,
    mock_update_exec,
    mock_get_token,
    mock_get_last_tick,
    orchestrator,
    monkeypatch,
):
    """A stale final quote is vetoed by the JIT quote guard."""
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_PILOT_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "EXEC_SLIPPAGE_BUDGET_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_OPTIMIZER_ENABLE", False, raising=False)

    trade = Trade(
        trade_id="test_stale_quote",
        symbol="NIFTY",
        direction="BUY",
        entry_price=100.0,
        stop_loss=90.0,
        target=120.0,
        qty=1,
        regime="TREND_BULL",
        timestamp=time.time(),
        instrument="OPT",
        instrument_token="123",
        strike=100.0,
        expiry="2023-12-28",
        side="BUY",
        capital_at_risk=1000.0,
        expected_slippage=1.0,
        confidence=0.9,
        strategy="TEST",
    )
    object.__setattr__(trade, "contract_resolved", True)

    mock_fetch_live.return_value = [{"symbol": "NIFTY", "market_open": True, "ltp": 100.0, "quote_age_sec": 0.5, "timestamp_epoch": time.time(), "latest_option_tick_age_sec": 0.5, "ws_connected": True}]
    mock_read_json.return_value = {"feed_runtime_state": "HEALTHY", "canonical_feed_truth": {"state": "HEALTHY", "reason_code": "OK"}, "feed_ok": True, "feed_fresh": True}
    mock_indicator_report.return_value = {"feed_runtime_state": "HEALTHY", "canonical_feed_truth": {"state": "HEALTHY", "reason_code": "OK"}}

    orchestrator._build_cycle_market_data = MagicMock(return_value=[{"symbol": "NIFTY", "market_open": True, "ltp": 100.0, "quote_age_sec": 0.5, "timestamp_epoch": time.time(), "latest_option_tick_age_sec": 0.5, "ws_connected": True}])
    orchestrator.trade_builder.evaluate_cycle_candidates = MagicMock(return_value=[trade])
    orchestrator.trade_builder.build_with_trace = MagicMock(return_value=(trade, {}))
    orchestrator.trade_builder._last_ranked_candidates = [trade]
    orchestrator._validate_market_snapshot = MagicMock(return_value=(True, False))
    orchestrator._immutable_cycle_snapshot = MagicMock(return_value={"symbol": "NIFTY", "market_open": True, "ltp": 100.0, "quote_age_sec": 0.5, "timestamp_epoch": time.time(), "latest_option_tick_age_sec": 0.5, "ws_connected": True})

    mock_gate = MagicMock()
    mock_gate.allowed = True
    mock_gate.blockers = []
    mock_eval_decision.return_value = mock_gate
    mock_is_halted.return_value = False
    mock_slo_status.return_value = {"allowed": True}
    mock_prepare.return_value = (trade, True, [])

    orchestrator.strategy_allocator = MagicMock()
    orchestrator.strategy_allocator.should_trade = MagicMock(return_value=True)

    alloc_mock = MagicMock()
    alloc_mock.allowed = True
    alloc_mock.max_qty = 1
    alloc_mock.reason = None
    alloc_mock.report = {}
    orchestrator.portfolio_allocator = MagicMock()
    orchestrator.portfolio_allocator.allocate = MagicMock(return_value=alloc_mock)

    orchestrator.risk_engine = MagicMock()
    orchestrator.risk_engine.size_trade = MagicMock(return_value=1)

    mock_get_token.return_value = 123
    mock_get_last_tick.return_value = {"ts_epoch": time.time() - 3.0}

    # This test is about the final executable-quote guard.  Feed lifecycle
    # fatality is independently covered by feed-state tests; suppress that
    # unrelated outer-loop short-circuit while retaining the canonical feed
    # truth gate and all downstream JIT logic.
    with patch("core.orchestrator.is_fatal_state", return_value=False), patch("core.orchestrator.time.sleep"), patch("core.orchestrator._pace_loop"), patch("core.orchestrator.write_pipeline_funnel"), patch("core.orchestrator.audit_append"), patch("core.orchestrator.write_candidate_handoff_root_cause_latest"), patch("core.orchestrator.write_live_indicator_readiness_latest"), patch("core.orchestrator.write_notrade_reason_truth_latest"), patch("core.orchestrator.write_ranking_quality_latest"), patch("core.orchestrator.write_live_workload_latest"), patch("core.orchestrator.write_candidate_flow_trace_latest"), patch("core.orchestrator.write_strategy_no_qualified_reasons_latest"), patch("core.orchestrator.write_candidate_lineage_ledger"), patch("core.orchestrator.write_top_opportunities_snapshots"), patch("core.orchestrator.write_runtime_health_snapshot"):
        orchestrator._legacy_live_monitoring(run_once=True)

    mock_update_exec.assert_any_call(
        "test_stale_quote",
        {
            "exec_guard_allowed": 0,
            "exec_guard_reason": "stale_final_executable_quote",
            "exec_guard_reason_code": "stale_quote",
            "veto_reasons": ["stale_quote"],
        },
    )


@patch("core.tick_store.get_last_tick")
@patch("core.market_data.get_token_for_symbol")
@patch("core.orchestrator.update_execution")
@patch("core.orchestrator.send_trade_ticket")
@patch("core.orchestrator.fetch_live_market_data")
@patch("core.orchestrator.evaluate_slo_status")
@patch("core.orchestrator.risk_halt.is_halted")
@patch("core.orchestrator.build_live_indicator_readiness_report")
@patch("core.orchestrator.produce_and_store_market_snapshot")
@patch("core.orchestrator.produce_and_store_runtime_snapshots")
@patch("core.orchestrator._read_json_dict")
@patch("core.orchestrator._build_top_opportunities_payload")
@patch("core.orchestrator.evaluate_decision")
@patch("core.orchestrator._prepare_trade_for_review_queue")
def test_jit_quote_revalidation_allows_fresh_quote(
    mock_prepare,
    mock_eval_decision,
    mock_build_top,
    mock_read_json,
    mock_runtime_snap,
    mock_market_snap,
    mock_indicator_report,
    mock_is_halted,
    mock_slo_status,
    mock_fetch_live,
    mock_send_ticket,
    mock_update_exec,
    mock_get_token,
    mock_get_last_tick,
    orchestrator,
    monkeypatch,
):
    """A fresh final quote reaches the allowed JIT execution-guard record."""
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_PILOT_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "EXEC_SLIPPAGE_BUDGET_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_OPTIMIZER_ENABLE", False, raising=False)

    trade = Trade(
        trade_id="test_fresh_quote",
        symbol="NIFTY",
        direction="BUY",
        entry_price=100.0,
        stop_loss=90.0,
        target=120.0,
        qty=1,
        regime="TREND_BULL",
        timestamp=time.time(),
        instrument="OPT",
        instrument_token="123",
        strike=100.0,
        expiry="2023-12-28",
        side="BUY",
        capital_at_risk=1000.0,
        expected_slippage=1.0,
        confidence=0.9,
        strategy="TEST",
    )
    object.__setattr__(trade, "contract_resolved", True)

    mock_fetch_live.return_value = [{"symbol": "NIFTY", "market_open": True, "ltp": 100.0, "quote_age_sec": 0.5, "timestamp_epoch": time.time(), "latest_option_tick_age_sec": 0.5, "ws_connected": True}]
    mock_read_json.return_value = {"feed_runtime_state": "HEALTHY", "canonical_feed_truth": {"state": "HEALTHY", "reason_code": "OK"}, "feed_ok": True, "feed_fresh": True}
    mock_indicator_report.return_value = {"feed_runtime_state": "HEALTHY", "canonical_feed_truth": {"state": "HEALTHY", "reason_code": "OK"}}

    orchestrator._build_cycle_market_data = MagicMock(return_value=[{"symbol": "NIFTY", "market_open": True, "ltp": 100.0, "quote_age_sec": 0.5, "timestamp_epoch": time.time(), "latest_option_tick_age_sec": 0.5, "ws_connected": True}])
    orchestrator.trade_builder.evaluate_cycle_candidates = MagicMock(return_value=[trade])
    orchestrator.trade_builder.build_with_trace = MagicMock(return_value=(trade, {}))
    orchestrator.trade_builder._last_ranked_candidates = [trade]
    orchestrator._validate_market_snapshot = MagicMock(return_value=(True, False))
    orchestrator._immutable_cycle_snapshot = MagicMock(return_value={"symbol": "NIFTY", "market_open": True, "ltp": 100.0, "quote_age_sec": 0.5, "timestamp_epoch": time.time(), "latest_option_tick_age_sec": 0.5, "ws_connected": True})

    mock_gate = MagicMock()
    mock_gate.allowed = True
    mock_gate.blockers = []
    mock_eval_decision.return_value = mock_gate
    mock_is_halted.return_value = False
    mock_slo_status.return_value = {"allowed": True}
    mock_prepare.return_value = (trade, True, [])

    orchestrator.strategy_allocator = MagicMock()
    orchestrator.strategy_allocator.should_trade = MagicMock(return_value=True)

    alloc_mock = MagicMock()
    alloc_mock.allowed = True
    alloc_mock.max_qty = 1
    alloc_mock.reason = None
    alloc_mock.report = {}
    orchestrator.portfolio_allocator = MagicMock()
    orchestrator.portfolio_allocator.allocate = MagicMock(return_value=alloc_mock)

    orchestrator.risk_engine = MagicMock()
    orchestrator.risk_engine.size_trade = MagicMock(return_value=1)

    mock_get_token.return_value = 123
    mock_get_last_tick.return_value = {"ts_epoch": time.time() - 1.0}

    with patch("core.orchestrator.is_fatal_state", return_value=False), patch("core.orchestrator.time.sleep"), patch("core.orchestrator._pace_loop"), patch("core.orchestrator.write_pipeline_funnel"), patch("core.orchestrator.audit_append"), patch("core.orchestrator.write_candidate_handoff_root_cause_latest"), patch("core.orchestrator.write_live_indicator_readiness_latest"), patch("core.orchestrator.write_notrade_reason_truth_latest"), patch("core.orchestrator.write_ranking_quality_latest"), patch("core.orchestrator.write_live_workload_latest"), patch("core.orchestrator.write_candidate_flow_trace_latest"), patch("core.orchestrator.write_strategy_no_qualified_reasons_latest"), patch("core.orchestrator.write_candidate_lineage_ledger"), patch("core.orchestrator.write_top_opportunities_snapshots"), patch("core.orchestrator.write_runtime_health_snapshot"):
        orchestrator._legacy_live_monitoring(run_once=True)

    from unittest.mock import ANY
    mock_update_exec.assert_any_call(
        "test_fresh_quote",
        {
            "exec_guard_allowed": 1,
            "exec_guard_reason": "ok",
            "exec_guard_reason_code": "ok",
            "planning_only": False,
            "cycle_processing_latency_ms": ANY,
            "final_quote_revalidation_age_ms": ANY,
        },
    )


def test_observability_ordering_is_at_end():
    """Ensure runtime snapshot generation remains after decision truth logging."""
    with open("core/orchestrator.py", "r") as f:
        content = f.read()

    heavy_io_idx = content.find("produce_and_store_runtime_snapshots(")
    assert heavy_io_idx != -1, "produce_and_store_runtime_snapshots not found!"

    top_opps_idx = content.find("write_notrade_reason_truth_latest(")
    assert top_opps_idx != -1, "write_notrade_reason_truth_latest not found!"

    assert heavy_io_idx > top_opps_idx, "Observability snapshot generation must be at the end, after trade decisions and truth logging."
