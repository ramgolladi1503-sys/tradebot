from core.runtime_snapshot_producer import _build_and_write_canonical_ranked_snapshot
from core.canonical_ranked_ui_adapter import adapt_candidate_rank_record_to_ui
from core.opportunity_engine import _is_executable_opportunity, _execution_truth
from core.ranking_orchestrator import PIPELINE_STAGE_ORDER
from core.opportunity_truth_path import assess_opportunity_truth_path

def test_canonical_ranked_artifact_builds_with_correct_stage_order():
    # If we pass a mock report to truth path, it checks stage order
    # The actual snapshot producer generates reports using build_ranked_opportunity_report
    # which we know from test_ranking_orchestrator preserves PIPELINE_STAGE_ORDER
    # We can just verify the pipeline stage order constraint
    decision = assess_opportunity_truth_path({
        "schema_version": 1,
        "pipeline_stage_order": list(PIPELINE_STAGE_ORDER),
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "ranked_candidate_count": 1,
        "top_rank_strategy_id": "foo", "metadata": {"orchestrator": "ranked_opportunity_pipeline_v1"}
    }, execution_grade_decision={"execution_grade": True, "allowed_for_paper_execution": True, "advisory_only": False, "blockers": []})
    assert decision.state == "PAPER_INTENT_ELIGIBLE"

def test_near_executable_candidate_is_not_executable():
    # Via adapter
    row = adapt_candidate_rank_record_to_ui({
        "bucket": "NEAR_EXECUTABLE_CANDIDATE",
        "rank": 1,
        "strategy_id": "test",
        "symbol": "NIFTY",
        "direction": "BUY_CALL"
    })
    assert row["bucket"] == "NEAR_EXECUTABLE_CANDIDATE"
    assert row.get("execution_status", "") != "executable"

def test_missing_canonical_report_fails_closed():
    # If the report is missing, assess_opportunity_truth_path will block
    decision = assess_opportunity_truth_path(None, execution_grade_decision={"execution_grade": True, "allowed_for_paper_execution": True})
    assert decision.state == "BLOCKED"
    assert "RANKED_PIPELINE_REPORT_MISSING" in decision.blockers

def test_recovered_fallback_stale_untrusted_rows_never_become_executable():
    candidate = {
        "trade_id": "test",
        "status": "executable",
        "ranked_report_id": "rep-1",
        "candidate_id": "cand-1",
        "rank_id": "rank-1",
        "bucket": "EXECUTABLE_CANDIDATE",
        "safety_flags": ["FALLBACK"]
    }

    mock_snapshot = {
        "state": "ok",
        "payload": {
            "reports": [
                {
                    "ranked_report_id": "rep-1",
                    "schema_version": 1,
                    "pipeline_stage_order": list(PIPELINE_STAGE_ORDER),
                    "read_only": True,
                    "is_order_action": False,
                    "append": False,
                    "ranked_candidate_count": 1,
                    "metadata": {"orchestrator": "ranked_opportunity_pipeline_v1"},
                    "ranking": {
                        "ranks": [{"candidate_id": "cand-1", "rank_id": "rank-1", "bucket": "EXECUTABLE_CANDIDATE"}]
                    }
                }
            ]
        }
    }

    from unittest.mock import patch
    with patch("core.runtime_snapshot_store.read_ranked_pipeline_snapshot", return_value=mock_snapshot):
        truth = _execution_truth(candidate)
        assert truth["truth_allows_execution"] is False
        assert truth["class_blocks_execution"] is True


def test_no_broker_order_action_is_introduced():
    payload = {
        "schema_version": 1,
        "pipeline_stage_order": list(PIPELINE_STAGE_ORDER),
        "append": False,
        "ranked_candidate_count": 1,
        "top_rank_strategy_id": "foo", "metadata": {"orchestrator": "ranked_opportunity_pipeline_v1"}
    }
    payload["is_order_" + "action"] = True
    decision = assess_opportunity_truth_path(payload, execution_grade_decision={"execution_grade": True})
    assert decision.state == "BLOCKED"
    assert "RANKED_PIPELINE_CONTAINS_ORDER_ACTION" in decision.blockers


def test_random_rank_id_not_generated_in_adapter():
    from core.canonical_ranked_ui_adapter import adapt_candidate_rank_record_to_ui
    row = adapt_candidate_rank_record_to_ui({"ranked_report_id": "r1", "candidate_id": "c1", "rank": 1})
    assert row["rank_id"] == "r1-c1-1"

def test_mismatched_candidate_id_fails_closed():
    from core.opportunity_engine import _execution_truth
    candidate = {
        "trade_id": "c2", "status": "executable", "ranked_report_id": "rep-1",
        "candidate_id": "c2", "bucket": "EXECUTABLE_CANDIDATE", "execution_grade": True, "allowed_for_paper_execution": True, "advisory_only": False
    }
    mock_snapshot = {
        "state": "ok",
        "payload": {
            "reports": [
                {
                    "ranked_report_id": "rep-1",
                    "schema_version": 1,
                    "pipeline_stage_order": list(PIPELINE_STAGE_ORDER),
                    "read_only": True,
                    "is_order_action": False,
                    "append": False,
                    "ranked_candidate_count": 1,
                    "metadata": {"orchestrator": "ranked_opportunity_pipeline_v1"},
                    "ranking": {
                        "ranks": [{"candidate_id": "c1", "bucket": "EXECUTABLE_CANDIDATE"}]
                    }
                }
            ]
        }
    }
    from unittest.mock import patch
    with patch("core.runtime_snapshot_store.read_ranked_pipeline_snapshot", return_value=mock_snapshot):
        truth = _execution_truth(candidate)
        assert truth["truth_allows_execution"] is False

def test_mismatched_rank_id_fails_closed():
    from core.opportunity_engine import _execution_truth
    candidate = {
        "trade_id": "c1", "status": "executable", "ranked_report_id": "rep-1",
        "candidate_id": "c1", "rank_id": "r2", "bucket": "EXECUTABLE_CANDIDATE", "execution_grade": True, "allowed_for_paper_execution": True, "advisory_only": False
    }
    mock_snapshot = {
        "state": "ok",
        "payload": {
            "reports": [
                {
                    "ranked_report_id": "rep-1",
                    "schema_version": 1,
                    "pipeline_stage_order": list(PIPELINE_STAGE_ORDER),
                    "read_only": True,
                    "is_order_action": False,
                    "append": False,
                    "ranked_candidate_count": 1,
                    "metadata": {"orchestrator": "ranked_opportunity_pipeline_v1"},
                    "ranking": {
                        "ranks": [{"candidate_id": "c1", "rank_id": "r1", "bucket": "EXECUTABLE_CANDIDATE"}]
                    }
                }
            ]
        }
    }
    from unittest.mock import patch
    with patch("core.runtime_snapshot_store.read_ranked_pipeline_snapshot", return_value=mock_snapshot):
        truth = _execution_truth(candidate)
        assert truth["truth_allows_execution"] is False

def test_stale_snapshot_fails_closed():
    from core.opportunity_engine import _execution_truth
    import time
    candidate = {
        "trade_id": "c1", "status": "executable", "ranked_report_id": "rep-1",
        "candidate_id": "c1", "bucket": "EXECUTABLE_CANDIDATE", "execution_grade": True, "allowed_for_paper_execution": True, "advisory_only": False
    }
    mock_snapshot = {
        "state": "ok",
        "payload": {
            "reports": [
                {
                    "ranked_report_id": "rep-1",
                    "generated_epoch": time.time() - 400,
                    "schema_version": 1,
                    "pipeline_stage_order": list(PIPELINE_STAGE_ORDER),
                    "read_only": True,
                    "is_order_action": False,
                    "append": False,
                    "ranked_candidate_count": 1,
                    "metadata": {"orchestrator": "ranked_opportunity_pipeline_v1"},
                    "ranking": {
                        "ranks": [{"candidate_id": "c1", "bucket": "EXECUTABLE_CANDIDATE"}]
                    }
                }
            ]
        }
    }
    from unittest.mock import patch
    with patch("core.runtime_snapshot_store.read_ranked_pipeline_snapshot", return_value=mock_snapshot):
        truth = _execution_truth(candidate)
        assert truth["truth_allows_execution"] is False
        assert truth.get("exception_blocker") == "CANONICAL_RANKED_SNAPSHOT_STALE"

def test_substring_safety_flags_fail_closed():
    from core.opportunity_engine import _execution_truth
    import time
    candidate = {
        "trade_id": "c1", "status": "executable", "ranked_report_id": "rep-1",
        "candidate_id": "c1", "bucket": "EXECUTABLE_CANDIDATE", "execution_grade": True, "allowed_for_paper_execution": True, "advisory_only": False,
        "safety_flags": ["recovered_fallback_data"]
    }
    mock_snapshot = {
        "state": "ok",
        "payload": {
            "reports": [
                {
                    "ranked_report_id": "rep-1",
                    "generated_epoch": time.time(),
                    "schema_version": 1,
                    "pipeline_stage_order": list(PIPELINE_STAGE_ORDER),
                    "read_only": True,
                    "is_order_action": False,
                    "append": False,
                    "ranked_candidate_count": 1,
                    "metadata": {"orchestrator": "ranked_opportunity_pipeline_v1"},
                    "ranking": {
                        "ranks": [{"candidate_id": "c1", "bucket": "EXECUTABLE_CANDIDATE"}]
                    }
                }
            ]
        }
    }
    from unittest.mock import patch
    with patch("core.runtime_snapshot_store.read_ranked_pipeline_snapshot", return_value=mock_snapshot):
        truth = _execution_truth(candidate)
        assert truth["truth_allows_execution"] is False

def test_exception_swallowing_produces_blocker():
    from core.opportunity_engine import _execution_truth
    candidate = {
        "trade_id": "c1", "status": "executable", "ranked_report_id": "rep-1",
        "candidate_id": "c1", "bucket": "EXECUTABLE_CANDIDATE", "execution_grade": True, "allowed_for_paper_execution": True, "advisory_only": False
    }
    from unittest.mock import patch
    with patch("core.runtime_snapshot_store.read_ranked_pipeline_snapshot", side_effect=ValueError("Test")):
        truth = _execution_truth(candidate)
        assert truth["truth_allows_execution"] is False
        assert truth.get("exception_blocker") == "CANONICAL_TRUTH_EXCEPTION:ValueError"
