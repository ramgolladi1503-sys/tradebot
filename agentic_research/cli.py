from __future__ import annotations

import argparse
import json
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from agentic_research.agents import DeterministicPlanner, GeminiPlanner, ResearchManager
from agentic_research.critics import DeterministicAdversarialCritic, GeminiAdversarialCritic
from agentic_research.execution import IdempotentToolExecutor, TraceRecorder
from agentic_research.graph import build_research_graph
from agentic_research.tools import TradeBotReadOnlyTools


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the read-only TradeBot agentic research workflow")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--research-id", required=True)
    parser.add_argument("--evidence", "--dataset", dest="evidence", required=True)
    parser.add_argument("--mode", choices=("structural", "legacy-report"), default="structural")
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--planner", choices=("deterministic", "gemini"), default="deterministic")
    parser.add_argument("--critic", choices=("deterministic", "gemini"), default="deterministic")
    parser.add_argument("--model", default="gemini-2.5-flash")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    planner = GeminiPlanner(model=args.model) if args.planner == "gemini" else DeterministicPlanner()
    critic = GeminiAdversarialCritic(model=args.model) if args.critic == "gemini" else DeterministicAdversarialCritic()
    tools = TradeBotReadOnlyTools(repo_root, critic=critic)
    state_dir = repo_root / "agentic_research" / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    executor = IdempotentToolExecutor(state_dir / "execution_ledger.sqlite", TraceRecorder(tools.store))
    db = state_dir / "checkpoints.sqlite"
    with SqliteSaver.from_conn_string(str(db)) as saver:
        graph = build_research_graph(tools, manager=ResearchManager(planner), checkpointer=saver, executor=executor)
        config = {"configurable": {"thread_id": args.research_id}}
        evidence_mode = "LEGACY_REPORT_AUDIT" if args.mode == "legacy-report" else "STRUCTURAL_DATASET"
        state = {
            "research_id": args.research_id,
            "objective": {"target": "READY_FOR_OPTION_REPLAY", "read_only": True, "evidence_mode": evidence_mode},
            "strategy_id": "trend_pullback_v1",
            "dataset_path": str(Path(args.evidence).resolve()),
            "evidence_mode": evidence_mode,
            "approval_status": "PENDING",
            "results": {},
            "step_count": 0,
        }
        output = graph.invoke(state, config=config)
        if args.approve:
            output = graph.invoke(Command(resume={"approved": True}), config=config)
        print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
