from __future__ import annotations

import argparse
import json
import os

from agentic_research.agents import GeminiPlanner, ResearchManager
from agentic_research.critics import GeminiAdversarialCritic
from agentic_research.evals.online_suite import run_online_evaluation_suite, write_online_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure Gemini manager and critic quality")
    parser.add_argument("--model", default="gemini-2.5-flash")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--output", default="agentic_research/eval_results/gemini_online.json")
    parser.add_argument("--request-delay-seconds", type=float, default=4.0)
    parser.add_argument("--maximum-retries", type=int, default=2)
    args = parser.parse_args()
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is required and must be provided through the environment or GitHub secret")
    manager = ResearchManager(GeminiPlanner(model=args.model))
    critic = GeminiAdversarialCritic(model=args.model)
    report = run_online_evaluation_suite(
        model_name=args.model,
        manager=manager,
        critic=critic,
        manager_repeats=args.repeats,
        request_delay_seconds=args.request_delay_seconds,
        maximum_retries=args.maximum_retries,
    )
    write_online_report(args.output, report)
    print(json.dumps({
        "model_name": report.model_name,
        "manager_correct_action_rate": report.manager_correct_action_rate,
        "manager_stability_rate": report.manager_stability_rate,
        "critic_pass_rate": report.critic_pass_rate,
        "unsafe_actions": report.manager_unsafe_actions + report.critic_unsafe_recommendations,
        "fabricated_numeric_values": report.critic_fabricated_numeric_values,
        "overall_passed": report.overall_passed,
        "suite_hash": report.suite_hash,
    }, indent=2, sort_keys=True))
    return 0 if report.overall_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
