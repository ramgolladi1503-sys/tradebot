from __future__ import annotations

import argparse
from pathlib import Path

from agentic_research.agents import DeterministicPlanner, GeminiPlanner, ResearchManager
from agentic_research.evals import build_evaluation_cases, run_evaluations, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the TradeBot research manager")
    parser.add_argument("--planner", choices=("deterministic", "gemini"), default="deterministic")
    parser.add_argument("--model", default="gemini-2.5-flash")
    parser.add_argument("--output", default="agentic_research/eval_results/latest.json")
    args = parser.parse_args()
    planner = GeminiPlanner(model=args.model) if args.planner == "gemini" else DeterministicPlanner()
    result = run_evaluations(args.planner, ResearchManager(planner), build_evaluation_cases())
    write_report(Path(args.output), result)
    print(result.model_dump_json(indent=2))
    return 0 if result.unsafe_actions == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
