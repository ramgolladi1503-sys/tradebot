import pytest

from core.ranking_authority import (
    DEFAULT_RANKING_ENGINES,
    RankingAuthority,
    RankingEngineRecord,
    ranking_authority_payload,
    resolve_execution_ranking_authority,
    validate_ranking_authorities,
)


def test_canonical_and_snapshot_rankings_are_ui_only():
    by_id = {row.engine_id: row for row in DEFAULT_RANKING_ENGINES}
    assert (
        by_id["canonical_ranked_opportunity_pipeline"].authority
        is RankingAuthority.UI_ONLY
    )
    assert by_id["runtime_ranked_snapshot"].authority is RankingAuthority.UI_ONLY


def test_default_execution_selection_authority_is_proven():
    authority = resolve_execution_ranking_authority()
    assert authority.engine_id == "legacy_opportunity_engine"
    assert authority.callable_name == "select_best_opportunity"
    assert authority.authority is RankingAuthority.EXECUTION_SELECTION


def test_missing_execution_selection_authority_fails_closed():
    rows = (
        RankingEngineRecord(
            "ui",
            "core.ranking_orchestrator",
            "build_ranked_opportunity_report",
            RankingAuthority.UI_ONLY,
            "read only",
        ),
    )
    with pytest.raises(RuntimeError, match="execution_ranking_authority_not_proven"):
        resolve_execution_ranking_authority(rows)


def test_exactly_one_proven_execution_authority_resolves():
    rows = (
        RankingEngineRecord(
            "legacy",
            "core.opportunity_engine",
            "select_best_opportunity",
            RankingAuthority.EXECUTION_SELECTION,
            "characterized runtime call-path proof",
        ),
        RankingEngineRecord(
            "ui",
            "core.ranking_orchestrator",
            "build_ranked_opportunity_report",
            RankingAuthority.UI_ONLY,
            "read only",
        ),
    )
    assert validate_ranking_authorities(rows, require_execution_authority=True) == ()
    assert resolve_execution_ranking_authority(rows).engine_id == "legacy"


def test_multiple_execution_rankers_are_rejected():
    rows = (
        RankingEngineRecord(
            "a", "a", "a", RankingAuthority.EXECUTION_SELECTION, ""
        ),
        RankingEngineRecord(
            "b", "b", "b", RankingAuthority.EXECUTION_SELECTION, ""
        ),
    )
    assert "multiple_execution_ranking_authorities" in validate_ranking_authorities(rows)


def test_payload_claim_is_backed_by_unique_authority():
    payload = ranking_authority_payload()
    assert payload["execution_authority_proven"] is True
    assert payload["validation_errors"] == []
    assert payload["is_order_action"] is False
