import time
from core.ranking_orchestrator import PIPELINE_STAGE_ORDER
from core.opportunity_engine import (
    _is_advisory_opportunity,
    _is_executable_opportunity,
    _candidate_class,
    _execution_truth,
    build_opportunity_score,
    annotate_ranked_opportunities,
    select_top_opportunities,
)


def _candidate(**overrides):
    base = {
        "trade_id": "t1",
        "symbol": "NIFTY",
        "execution_grade": True,
        "allowed_for_paper_execution": True,
        "advisory_only": False,
        "ranked_report_id": "report-123", "generated_epoch": time.time(),
        "candidate_id": "t1",
        "rank_id": "rank-1",
        "bucket": "EXECUTABLE_CANDIDATE",
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "execution_allowed": True,
        "tradable": True,
        "execution_ok": True,
        "display_entry": 100.0,
        "display_entry_status": "displayable",
        "builder_confidence": 0.82,
        "permission_confidence": 0.82,
        "gating_final_confidence": 0.82,
        "source_flags": {},
    }
    base.update(overrides)
    return base



from unittest.mock import patch


from unittest.mock import patch


def test_real_executable_candidate_stays_executable():
    candidate = _candidate(trade_id="exec-real")
    candidate["candidate_id"] = "c1"
    candidate["lineage_id"] = "l1"
    candidate["rank_id"] = "r1"
    candidate["ranked_report_id"] = "rr1"

    import time
    mock_snapshot = {
        "state": "ok",
        "payload": {
            "reports": [
                {
                    "schema_version": 1,
                    "pipeline_stage_order": list(PIPELINE_STAGE_ORDER),
                    "read_only": True,
                    "is_order_action": False,
                    "append": False,
                    "ranked_candidate_count": 1,
                    "top_rank_strategy_id": "exec-real",
                    "ranked_report_id": "rr1",
                    "generated_epoch": time.time(),
                    "metadata": {"orchestrator": "ranked_opportunity_pipeline_v1"},
                    "ranking": {
                        "ranks": [{"strategy_id": "exec-real", "candidate_id": "c1", "lineage_id": "l1", "rank_id": "r1", "bucket": "EXECUTABLE_CANDIDATE"}]
                    }
                }
            ]
        }
    }

    with patch("core.runtime_snapshot_store.read_ranked_pipeline_snapshot", return_value=mock_snapshot):
        assert _is_executable_opportunity(candidate) is True
        ranked = annotate_ranked_opportunities([candidate], scope="unit", top_n=1)
        assert ranked[0]["selected_for_execution"] is True
        assert ranked[0]["selection_reason"] == "selected_top_rank"

def test_fallback_candidate_never_becomes_executable():
    candidate = _candidate(
        trade_id="fallback-row",
        row_kind="recovered_fallback",
        source_flags={"candidate_origin": "fallback"},
    )
    assert _is_executable_opportunity(candidate) is False
    assert _is_advisory_opportunity(candidate) is True
    pools = select_top_opportunities([candidate], executable_top_n=3, advisory_top_n=3)
    assert pools["top_executable_opportunities"] == []
    assert [row["trade_id"] for row in pools["top_advisory_opportunities"]] == ["fallback-row"]


def test_rest_fallback_quote_source_never_becomes_executable():
    candidate = _candidate(
        trade_id="fallback-quote-source",
        quote_source="REST_FALLBACK",
        option_ltp_source="REST_FALLBACK",
    )
    assert _candidate_class(candidate) == "fallback"
    assert _is_executable_opportunity(candidate) is False
    assert _is_advisory_opportunity(candidate) is True
    pools = select_top_opportunities([candidate], executable_top_n=3, advisory_top_n=3)
    assert pools["top_executable_opportunities"] == []
    assert [row["trade_id"] for row in pools["top_advisory_opportunities"]] == ["fallback-quote-source"]


def test_softrej_trade_id_never_becomes_executable():
    candidate = _candidate(
        trade_id="softrej_trade-1",
        quote_source="live",
        option_ltp_source="live",
    )
    assert _candidate_class(candidate) == "fallback"
    assert _is_executable_opportunity(candidate) is False
    assert _is_advisory_opportunity(candidate) is True
    ranked = annotate_ranked_opportunities([candidate], scope="unit", top_n=1)
    assert ranked[0]["selected_for_execution"] is False
    assert ranked[0]["truth_allows_execution"] is False
    assert ranked[0]["selection_reason"] in {"not_execution_eligible", "execution_truth_blocked"}
    pools = select_top_opportunities(ranked, executable_top_n=3, advisory_top_n=3)
    assert pools["top_executable_opportunities"] == []
    assert [row["trade_id"] for row in pools["top_advisory_opportunities"]] == ["softrej_trade-1"]


def test_subscription_failed_quote_source_never_becomes_executable():
    candidate = _candidate(
        trade_id="subscription-failed",
        quote_source="SUBSCRIPTION_FAILED",
        option_ltp_source="SUBSCRIPTION_FAILED",
    )
    assert _candidate_class(candidate) == "fallback"
    assert _is_executable_opportunity(candidate) is False
    pools = select_top_opportunities([candidate], executable_top_n=3, advisory_top_n=3)
    assert pools["top_executable_opportunities"] == []


def test_planning_only_candidate_is_blocked_even_with_execution_fields():
    candidate = _candidate(
        trade_id="planning-only",
        planning_only=True,
        source_flags={"candidate_origin": "planning_only"},
    )
    ranked = annotate_ranked_opportunities([candidate], scope="unit", top_n=1)
    assert ranked[0]["selected_for_execution"] is False
    assert ranked[0]["selection_reason"] == "execution_truth_blocked"
    assert ranked[0]["truth_allows_execution"] is False


def test_softened_candidate_stays_advisory_only():
    candidate = _candidate(
        trade_id="softened-row",
        row_kind="soft_reject",
        source_flags={"candidate_tags": ["softened"]},
    )
    assert _is_executable_opportunity(candidate) is False
    assert _is_advisory_opportunity(candidate) is True


def test_candidate_class_inference_detects_fallback_and_planning():
    assert _candidate_class(_candidate(row_kind="recovered_fallback", source_flags={"candidate_origin": "fallback"})) == "fallback"
    assert _candidate_class(_candidate(planning_only=True, source_flags={"candidate_origin": "planning_only"})) == "planning_only"


def test_execution_truth_blocks_non_real_candidate_classes():
    fallback = _execution_truth(_candidate(row_kind="recovered_fallback", source_flags={"candidate_origin": "fallback"}))
    planning = _execution_truth(_candidate(planning_only=True, source_flags={"candidate_origin": "planning_only"}))
    assert fallback["truth_allows_execution"] is False
    assert planning["truth_allows_execution"] is False


def test_non_executable_classes_are_score_capped_for_ranking_separation():
    fallback = _candidate(trade_id="fallback-score", row_kind="recovered_fallback", source_flags={"candidate_origin": "fallback"})
    planning = _candidate(trade_id="planning-score", planning_only=True, source_flags={"candidate_origin": "planning_only"})
    softened = _candidate(trade_id="soft-score", row_kind="soft_reject", source_flags={"candidate_tags": ["softened"]})
    fallback_score = build_opportunity_score(fallback)["opportunity_score"]
    planning_score = build_opportunity_score(planning)["opportunity_score"]
    softened_score = build_opportunity_score(softened)["opportunity_score"]
    assert fallback_score <= 0.39
    assert planning_score <= 0.34
    assert softened_score <= 0.44


def test_real_executable_scores_above_class_capped_rows():
    real = _candidate(trade_id="real-score")
    fallback = _candidate(trade_id="fallback-score", row_kind="recovered_fallback", source_flags={"candidate_origin": "fallback"})
    assert build_opportunity_score(real)["opportunity_score"] > build_opportunity_score(fallback)["opportunity_score"]
