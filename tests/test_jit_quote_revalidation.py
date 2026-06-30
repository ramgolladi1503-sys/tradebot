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
@patch("core.orchestrator.build_live_indicator_readiness_report")
@patch("core.orchestrator.produce_and_store_market_snapshot")
@patch("core.orchestrator.produce_and_store_runtime_snapshots")
@patch("core.orchestrator._read_json_dict")
def test_jit_quote_revalidation_blocks_stale_quote(
    mock_read_json,
    mock_runtime_snap,
    mock_market_snap,
    mock_indicator_report,
    mock_fetch_live,
    mock_send_ticket,
    mock_update_exec,
    mock_get_token,
    mock_get_last_tick,
    orchestrator,
    monkeypatch
):
    """Test Case 1: Quote is older than 2.5s at execution time, should be blocked."""
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_PILOT_MODE", False, raising=False)
    
    trade = Trade(
        trade_id="test_stale_quote",
        symbol="NIFTY",
        direction="BUY",
        entry_price=100.0,
        stop_loss=90.0,
        target=120.0,
        qty=1,
        regime="TREND_BULL"
    )
    
    mock_fetch_live.return_value = [{"symbol": "NIFTY", "market_open": True, "ltp": 100.0}]
    mock_read_json.return_value = {}
    
    orchestrator._build_cycle_market_data = MagicMock(return_value=[{"symbol": "NIFTY", "market_open": True, "ltp": 100.0}])
    orchestrator.trade_builder.produce_candidates = MagicMock(return_value=[])
    orchestrator._rank_cycle_candidates = MagicMock(return_value=[trade])
    orchestrator._validate_market_snapshot = MagicMock(return_value=(True, False))
    orchestrator._immutable_cycle_snapshot = MagicMock(return_value={"symbol": "NIFTY", "market_open": True, "ltp": 100.0})
    
    # Tick is 3s old
    mock_get_token.return_value = 123
    mock_get_last_tick.return_value = {"ts_epoch": time.time() - 3.0}
    
    # Mock loop delay to avoid infinite loops and sleeping
    with patch("core.orchestrator.time.sleep"), patch("core.orchestrator._pace_loop"), patch("core.orchestrator.write_pipeline_funnel"), patch("core.orchestrator.audit_append"), patch("core.orchestrator.write_candidate_handoff_root_cause_latest"), patch("core.orchestrator.write_live_indicator_readiness_latest"), patch("core.orchestrator.write_notrade_reason_truth_latest"), patch("core.orchestrator.write_ranking_quality_latest"), patch("core.orchestrator.write_live_workload_latest"), patch("core.orchestrator.write_candidate_flow_trace_latest"), patch("core.orchestrator.write_strategy_no_qualified_reasons_latest"), patch("core.orchestrator.write_candidate_lineage_ledger"), patch("core.orchestrator.write_top_opportunities_snapshots"), patch("core.orchestrator.write_runtime_health_snapshot"):
        orchestrator._legacy_live_monitoring(run_once=True)
        
    mock_update_exec.assert_called_with(
        "test_stale_quote",
        {
            "exec_guard_allowed": 0,
            "exec_guard_reason": "stale_final_executable_quote",
            "exec_guard_reason_code": "stale_quote",
            "veto_reasons": ["stale_quote"]
        }
    )

@patch("core.tick_store.get_last_tick")
@patch("core.market_data.get_token_for_symbol")
@patch("core.orchestrator.update_execution")
@patch("core.orchestrator.send_trade_ticket")
@patch("core.orchestrator.fetch_live_market_data")
@patch("core.orchestrator.build_live_indicator_readiness_report")
@patch("core.orchestrator.produce_and_store_market_snapshot")
@patch("core.orchestrator.produce_and_store_runtime_snapshots")
@patch("core.orchestrator._read_json_dict")
def test_jit_quote_revalidation_allows_fresh_quote(
    mock_read_json,
    mock_runtime_snap,
    mock_market_snap,
    mock_indicator_report,
    mock_fetch_live,
    mock_send_ticket,
    mock_update_exec,
    mock_get_token,
    mock_get_last_tick,
    orchestrator,
    monkeypatch
):
    """Test Case 2: Quote is fresh (<=2.5s) at execution time, should be allowed."""
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_PILOT_MODE", False, raising=False)
    
    trade = Trade(
        trade_id="test_fresh_quote",
        symbol="NIFTY",
        direction="BUY",
        entry_price=100.0,
        stop_loss=90.0,
        target=120.0,
        qty=1,
        regime="TREND_BULL"
    )
    
    mock_fetch_live.return_value = [{"symbol": "NIFTY", "market_open": True, "ltp": 100.0}]
    mock_read_json.return_value = {}
    
    orchestrator._build_cycle_market_data = MagicMock(return_value=[{"symbol": "NIFTY", "market_open": True, "ltp": 100.0}])
    orchestrator.trade_builder.produce_candidates = MagicMock(return_value=[])
    orchestrator._rank_cycle_candidates = MagicMock(return_value=[trade])
    orchestrator._validate_market_snapshot = MagicMock(return_value=(True, False))
    orchestrator._immutable_cycle_snapshot = MagicMock(return_value={"symbol": "NIFTY", "market_open": True, "ltp": 100.0})
    
    # Tick is 1s old
    mock_get_token.return_value = 123
    mock_get_last_tick.return_value = {"ts_epoch": time.time() - 1.0}
    
    with patch("core.orchestrator.time.sleep"), patch("core.orchestrator._pace_loop"), patch("core.orchestrator.write_pipeline_funnel"), patch("core.orchestrator.audit_append"), patch("core.orchestrator.write_candidate_handoff_root_cause_latest"), patch("core.orchestrator.write_live_indicator_readiness_latest"), patch("core.orchestrator.write_notrade_reason_truth_latest"), patch("core.orchestrator.write_ranking_quality_latest"), patch("core.orchestrator.write_live_workload_latest"), patch("core.orchestrator.write_candidate_flow_trace_latest"), patch("core.orchestrator.write_strategy_no_qualified_reasons_latest"), patch("core.orchestrator.write_candidate_lineage_ledger"), patch("core.orchestrator.write_top_opportunities_snapshots"), patch("core.orchestrator.write_runtime_health_snapshot"):
        orchestrator._legacy_live_monitoring(run_once=True)
        
    mock_update_exec.assert_any_call(
        "test_fresh_quote",
        {
            "exec_guard_allowed": 1,
            "exec_guard_reason": "ok",
            "exec_guard_reason_code": "ok",
            "planning_only": False,
            "cycle_processing_latency_ms": mock_update_exec.call_args[0][1].get("cycle_processing_latency_ms"),
            "final_quote_revalidation_age_ms": mock_update_exec.call_args[0][1].get("final_quote_revalidation_age_ms"),
        }
    )

def test_observability_ordering_is_at_end():
    """Test Case 3: Ensure `produce_and_store_runtime_snapshots` is called after decision phases."""
    with open("core/orchestrator.py", "r") as f:
        content = f.read()
    
    # Check that it's moved from around line 4975 to after write_candidate_flow_trace_latest or at least near the end of the loop
    # We can check that `produce_and_store_runtime_snapshots` is strictly after `write_top_opportunities_snapshots` or `write_candidate_handoff_root_cause_latest`
    
    heavy_io_idx = content.find("produce_and_store_runtime_snapshots(")
    assert heavy_io_idx != -1, "produce_and_store_runtime_snapshots not found!"
    
    top_opps_idx = content.find("write_notrade_reason_truth_latest(")
    assert top_opps_idx != -1, "write_notrade_reason_truth_latest not found!"
    
    # Ensure the heavy IO observability call is placed far down in the file
    assert heavy_io_idx > top_opps_idx, "Observability snapshot generation must be at the end, after trade decisions and truth logging."

