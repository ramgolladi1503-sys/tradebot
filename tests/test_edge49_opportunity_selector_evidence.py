from __future__ import annotations

from core.candidate_ranking import CandidateRankRecord
from core.opportunity_scoring import ADVISORY_ONLY, NEEDS_CONFIRMATION, SCORE_ELIGIBLE
from core.opportunity_selector_evidence import build_opportunity_selector_evidence


def _rank(
    rank: int,
    strategy_id: str,
    *,
    final_score: float,
    eligibility: str = SCORE_ELIGIBLE,
    executable: bool = True,
    blockers: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    safety_flags: tuple[str, ...] = (),
) -> CandidateRankRecord:
    return CandidateRankRecord(
        rank=rank,
        strategy_id=strategy_id,
        symbol="NIFTY",
        direction="BUY_CALL",
        directional_family="BULLISH",
        movement_type="breakout",
        final_score=final_score,
        bucket="EXECUTABLE_CANDIDATE" if eligibility == SCORE_ELIGIBLE else "ADVISORY_CANDIDATE",
        score_eligibility=eligibility,
        executable_candidate=executable,
        rank_reason="test_rank_reason",
        downgrade_reasons=(),
        blockers=blockers,
        warnings=warnings,
        safety_flags=safety_flags,
        directional_warnings=(),
        sort_key=(rank,),
    )


def test_selector_evidence_selects_only_score_eligible_executable_unblocked_candidates():
    report = build_opportunity_selector_evidence(
        [
            _rank(1, "selected", final_score=0.82),
            _rank(2, "blocked", final_score=0.80, blockers=("stale_quote",)),
            _rank(3, "advisory", final_score=0.49, eligibility=ADVISORY_ONLY, executable=False),
        ],
        selection_limit=3,
    )

    assert report.selected_count == 1
    assert report.not_selected_count == 2
    assert report.selected_strategy_ids == ("selected",)
    assert report.no_selection_reason is None
    assert report.records[0].selector_decision == "SELECTED"
    assert report.records[1].selector_reason == "not_selected_blocked_candidate"
    assert report.records[2].selector_reason == "not_selected_score_eligibility_advisory_only"
    assert "stale_quote" in report.rejection_reasons


def test_selector_evidence_reports_no_ranked_candidates():
    report = build_opportunity_selector_evidence([], selection_limit=3)

    assert report.source_rank_count == 0
    assert report.selected_count == 0
    assert report.no_selection_reason == "no_ranked_candidates"
    assert report.read_only is True
    assert report.is_order_action is False
    assert report.append is False
    assert report.metadata["broker_api_called"] is False


def test_selector_evidence_reports_no_score_eligible_candidates():
    report = build_opportunity_selector_evidence(
        [
            _rank(1, "needs-confirmation", final_score=0.61, eligibility=NEEDS_CONFIRMATION, executable=False),
            _rank(2, "advisory", final_score=0.49, eligibility=ADVISORY_ONLY, executable=False),
        ],
        selection_limit=3,
    )

    assert report.selected_count == 0
    assert report.no_selection_reason == "no_score_eligible_candidates"
    assert "not_selected_score_eligibility_needs_confirmation" in report.rejection_reasons


def test_selector_evidence_reports_no_executable_candidates():
    report = build_opportunity_selector_evidence(
        [
            _rank(1, "eligible-but-not-executable", final_score=0.71, eligibility=SCORE_ELIGIBLE, executable=False),
        ],
        selection_limit=3,
    )

    assert report.score_eligible_source_count == 1
    assert report.executable_source_count == 0
    assert report.no_selection_reason == "no_executable_candidates"
    assert report.records[0].selector_reason == "not_selected_not_executable_candidate"


def test_selector_evidence_selection_limit_is_explained():
    report = build_opportunity_selector_evidence(
        [
            _rank(1, "top", final_score=0.81),
            _rank(2, "second", final_score=0.79),
        ],
        selection_limit=1,
    )

    assert report.selected_strategy_ids == ("top",)
    assert report.records[0].selected is True
    assert report.records[1].selected is False
    assert report.records[1].selector_reason == "not_selected_selection_limit_or_tiebreak"


def test_selector_evidence_reports_selection_limit_zero():
    report = build_opportunity_selector_evidence(
        [_rank(1, "top", final_score=0.81)],
        selection_limit=0,
    )

    assert report.selected_count == 0
    assert report.no_selection_reason == "selection_limit_zero"
    assert report.records[0].selector_reason == "not_selected_selection_limit_or_tiebreak"
