from __future__ import annotations

import argparse
import json
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_research.agents import DeterministicPlanner, ResearchManager
from agentic_research.critics import DeterministicAdversarialCritic
from agentic_research.evals import build_evaluation_cases, run_evaluations, write_report
from agentic_research.execution import IdempotentToolExecutor, TraceRecorder
from agentic_research.graph import build_research_graph
from agentic_research.tools import TradeBotReadOnlyTools


def run_portfolio_demo(repo_root: Path, research_id: str = "portfolio-legacy-20260629") -> dict:
    repo_root = Path(repo_root).resolve()
    tools = TradeBotReadOnlyTools(repo_root, critic=DeterministicAdversarialCritic())
    state_dir = repo_root / "agentic_research" / ".state"
    executor = IdempotentToolExecutor(state_dir / "portfolio_demo_ledger.sqlite", TraceRecorder(tools.store))
    graph = build_research_graph(tools, manager=ResearchManager(DeterministicPlanner()), checkpointer=InMemorySaver(), executor=executor)
    report_path = repo_root / "runtime" / "backtests" / "all_strategy_20260629" / "all_strategy_report_20260629.json"
    config = {"configurable": {"thread_id": research_id}}
    paused = graph.invoke({
        "research_id": research_id,
        "objective": {"target": "EVIDENCE_AUDIT", "read_only": True, "evidence_mode": "LEGACY_REPORT_AUDIT"},
        "strategy_id": "trend_pullback_v1",
        "dataset_path": str(report_path),
        "evidence_mode": "LEGACY_REPORT_AUDIT",
        "approval_status": "PENDING",
        "results": {},
        "step_count": 0,
    }, config=config)
    completed = graph.invoke(Command(resume={"approved": True}), config=config)
    eval_result = run_evaluations("deterministic", ResearchManager(DeterministicPlanner()), build_evaluation_cases())
    eval_path = write_report(repo_root / "agentic_research" / "eval_results" / "deterministic_baseline.json", eval_result)
    summary = {
        "research_id": research_id,
        "paused_for_approval": paused.get("status") == "WAITING_APPROVAL",
        "final_status": completed.get("status"),
        "final_verdict": completed.get("final_verdict"),
        "tools_executed": sorted((completed.get("results") or {}).keys()),
        "eval_report": str(eval_path),
        "eval_total_cases": eval_result.total_cases,
        "eval_correct_action_rate": eval_result.correct_action_rate,
        "eval_unsafe_actions": eval_result.unsafe_actions,
        "production_architecture_modified": False,
    }
    tools.store.write_json(research_id, "portfolio_demo_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the interview-ready TradeBot agentic research demo")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--research-id", default="portfolio-legacy-20260629")
    args = parser.parse_args()
    summary = run_portfolio_demo(Path(args.repo_root), args.research_id)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["final_status"] == "COMPLETED" and summary["eval_unsafe_actions"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
