from agentic_research.agents import DeterministicPlanner, ResearchManager
from agentic_research.evals import build_evaluation_cases, run_evaluations


def test_eval_suite_has_portfolio_scale_and_zero_unsafe_actions():
    cases = build_evaluation_cases()
    assert len(cases) >= 64
    result = run_evaluations("deterministic", ResearchManager(DeterministicPlanner()), cases)
    assert result.total_cases == len(cases)
    assert result.correct_action_rate == 1.0
    assert result.unsafe_actions == 0
    assert result.exceptions == 0
