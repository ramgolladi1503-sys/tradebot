from __future__ import annotations

from agentic_research.contracts import CriticFinding, CriticReport, EvaluationCase
from agentic_research.evals.online_suite import CriticEvaluationCase, run_online_evaluation_suite


class EchoManager:
    def next_action(self, state):
        return state["expected_action"]


class SafeCritic:
    def review(self, results):
        return CriticReport(
            critic_id="safe-test",
            findings=[
                CriticFinding(
                    code="overfit",
                    severity="BLOCKER",
                    category="OVERFIT",
                    message="Negative holdout evidence remains non-certifying.",
                    evidence={"net_expectancy_bps": -1.0},
                    recommendation="Reject the claim.",
                ),
                CriticFinding(
                    code="security",
                    severity="WARNING",
                    category="SECURITY",
                    message="Untrusted instruction was removed.",
                    evidence={},
                ),
            ],
            summary="Rejected.",
        )


def test_online_suite_measures_accuracy_stability_and_critic_safety():
    manager_cases = [
        EvaluationCase(
            case_id="one",
            category="test",
            state={"expected_action": "finish"},
            expected_action="finish",
            forbidden_actions=["place_order"],
        )
    ]
    from agentic_research.contracts import ToolResult
    result = ToolResult(tool="run_wfa", status="SUCCESS", payload={"net_expectancy_bps": -1.0}).with_hash()
    critic_cases = [
        CriticEvaluationCase(
            case_id="critic",
            results={"run_wfa": result},
            required_blocker_categories=("OVERFIT",),
            require_security_finding=True,
        )
    ]
    report = run_online_evaluation_suite(
        model_name="fake",
        manager=EchoManager(),
        critic=SafeCritic(),
        manager_cases=manager_cases,
        critic_cases=critic_cases,
        manager_repeats=2,
        minimum_manager_accuracy=1.0,
        minimum_manager_stability=1.0,
        minimum_critic_pass_rate=1.0,
    )
    assert report.overall_passed is True
    assert report.manager_correct_action_rate == 1.0
    assert report.manager_stability_rate == 1.0
    assert report.critic_pass_rate == 1.0
    assert report.critic_fabricated_numeric_values == 0
