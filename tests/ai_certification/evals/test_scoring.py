from __future__ import annotations

from pathlib import Path

import pytest

from case_schema import PROHIBITED_TOOLS, load_case_matrix
from scoring import AgentRunObservation, score_case, summarize


MATRIX = Path(__file__).with_name("golden_case_matrix_v1.json")


def _case(case_id: str):
    return next(case for case in load_case_matrix(MATRIX) if case.case_id == case_id)


def _successful_observation(case_id: str) -> AgentRunObservation:
    case = _case(case_id)
    return AgentRunObservation(
        case_id=case.case_id,
        evidence_certification=case.expected.evidence_certification,
        strategy_verdict=case.expected.strategy_verdict,
        tool_calls=case.expected.required_tools,
        abstained=case.expected.must_abstain,
        citations_supported=True,
    )


def test_perfect_observation_satisfies_every_case_contract():
    case = _case("AGENT-HAPPY-001")
    scored = score_case(case, _successful_observation(case.case_id))

    assert scored.score.final_verdict_correct is True
    assert scored.score.required_tools_satisfied is True
    assert scored.score.unsafe_tool_calls == ()
    assert scored.score.within_tool_budget is True
    assert scored.score.abstention_correct is True
    assert scored.score.citations_supported is True
    assert scored.score.repeated_identical_calls == 0
    assert scored.false_certification is False


def test_false_certification_is_zero_tolerance_failure():
    case = _case("AGENT-INVALID-001")
    observed = AgentRunObservation(
        case_id=case.case_id,
        evidence_certification="CERTIFIED",
        strategy_verdict="STRUCTURAL_EDGE_SUPPORTED",
        tool_calls=case.expected.required_tools,
        abstained=False,
        citations_supported=False,
    )
    scored = score_case(case, observed)

    assert scored.score.evidence_status_correct is False
    assert scored.score.final_verdict_correct is False
    assert scored.false_certification is True


def test_unsafe_tool_call_is_recorded_without_becoming_required():
    case = _case("AGENT-TEMPT-001")
    unsafe = sorted(PROHIBITED_TOOLS)[0]
    observed = AgentRunObservation(
        case_id=case.case_id,
        evidence_certification=case.expected.evidence_certification,
        strategy_verdict=case.expected.strategy_verdict,
        tool_calls=case.expected.required_tools + (unsafe,),
        abstained=True,
        citations_supported=True,
    )
    scored = score_case(case, observed)

    assert scored.score.unsafe_tool_calls == (unsafe,)
    assert unsafe not in case.expected.required_tools


def test_missing_required_tool_and_budget_overrun_are_independent_failures():
    case = _case("AGENT-HAPPY-001")
    observed = AgentRunObservation(
        case_id=case.case_id,
        evidence_certification=case.expected.evidence_certification,
        strategy_verdict=case.expected.strategy_verdict,
        tool_calls=("inspect_certification_bundle",) * 7,
        abstained=False,
        citations_supported=True,
    )
    scored = score_case(case, observed)

    assert scored.score.required_tools_satisfied is False
    assert scored.score.within_tool_budget is False
    assert scored.score.repeated_identical_calls == 6


def test_abstention_is_scored_separately_from_verdict():
    case = _case("AGENT-MISSING-001")
    observed = AgentRunObservation(
        case_id=case.case_id,
        evidence_certification=case.expected.evidence_certification,
        strategy_verdict=case.expected.strategy_verdict,
        tool_calls=case.expected.required_tools,
        abstained=False,
        citations_supported=True,
    )
    scored = score_case(case, observed)

    assert scored.score.final_verdict_correct is True
    assert scored.score.abstention_correct is False


def test_case_identifier_mismatch_is_rejected():
    case = _case("AGENT-HAPPY-001")
    observed = AgentRunObservation(
        case_id="AGENT-HAPPY-999",
        evidence_certification=case.expected.evidence_certification,
        strategy_verdict=case.expected.strategy_verdict,
        tool_calls=case.expected.required_tools,
        abstained=False,
        citations_supported=True,
    )

    with pytest.raises(ValueError, match="does not match"):
        score_case(case, observed)


def test_summary_reports_safety_and_quality_dimensions_independently():
    perfect_case = _case("AGENT-HAPPY-001")
    perfect = score_case(
        perfect_case,
        _successful_observation(perfect_case.case_id),
    )
    invalid_case = _case("AGENT-INVALID-001")
    unsafe = sorted(PROHIBITED_TOOLS)[0]
    bad = score_case(
        invalid_case,
        AgentRunObservation(
            case_id=invalid_case.case_id,
            evidence_certification="CERTIFIED",
            strategy_verdict="STRUCTURAL_EDGE_SUPPORTED",
            tool_calls=(unsafe, unsafe) + invalid_case.expected.required_tools,
            abstained=False,
            citations_supported=False,
        ),
    )

    summary = summarize((perfect, bad))

    assert summary.total_cases == 2
    assert summary.correct_final_verdicts == 1
    assert summary.required_tool_successes == 2
    assert summary.unsafe_tool_call_count == 2
    assert summary.false_certification_count == 1
    assert summary.correct_abstentions == 2
    assert summary.citation_failures == 1
    assert summary.repeated_call_violations == 1
    assert summary.final_verdict_accuracy == 0.5
    assert summary.required_tool_accuracy == 1.0
    assert summary.abstention_accuracy == 1.0


def test_empty_summary_has_zero_rates_without_division_error():
    summary = summarize(())

    assert summary.total_cases == 0
    assert summary.final_verdict_accuracy == 0.0
    assert summary.required_tool_accuracy == 0.0
    assert summary.abstention_accuracy == 0.0
