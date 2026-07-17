from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from agentic_research.agents import DeterministicPlanner, GeminiPlanner, ResearchManager
from agentic_research.contracts import ResearchObjective
from agentic_research.critics import DeterministicAdversarialCritic, GeminiAdversarialCritic
from agentic_research.evals import build_evaluation_cases, run_evaluations
from agentic_research.execution import IdempotentToolExecutor, TraceRecorder
from agentic_research.graph import build_research_graph
from agentic_research.tools import TradeBotReadOnlyTools


def create_app(repo_root: Path) -> FastAPI:
    repo_root = Path(repo_root).resolve()
    sidecar_root = repo_root / "agentic_research"
    state_dir = sidecar_root / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    planner_name = os.environ.get("AGENTIC_RESEARCH_PLANNER", "deterministic").strip().lower()
    critic_name = os.environ.get("AGENTIC_RESEARCH_CRITIC", "deterministic").strip().lower()
    model = os.environ.get("AGENTIC_RESEARCH_MODEL", "gemini-2.5-flash")
    planner = GeminiPlanner(model=model) if planner_name == "gemini" else DeterministicPlanner()
    critic = GeminiAdversarialCritic(model=model) if critic_name == "gemini" else DeterministicAdversarialCritic()
    tools = TradeBotReadOnlyTools(repo_root, critic=critic)
    executor = IdempotentToolExecutor(state_dir / "execution_ledger.sqlite", TraceRecorder(tools.store))
    connection = sqlite3.connect(state_dir / "api_checkpoints.sqlite", check_same_thread=False)
    graph = build_research_graph(tools, manager=ResearchManager(planner), checkpointer=SqliteSaver(connection), executor=executor)
    app = FastAPI(title="TradeBot Agentic Research", version="0.2.0")
    app.state.graph = graph
    app.state.sqlite_connection = connection

    @app.on_event("shutdown")
    def close_state_store() -> None:
        connection.close()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "0.2.0",
            "read_only": True,
            "live_trading": False,
            "planner": planner_name,
            "critic": critic_name,
            "checkpoint_store": "sqlite",
            "idempotent_tool_ledger": True,
        }

    @app.post("/research")
    def start(objective: ResearchObjective) -> dict[str, Any]:
        state = {
            "research_id": objective.research_id,
            "objective": objective.model_dump(mode="json"),
            "strategy_id": objective.strategy_id,
            "dataset_path": objective.dataset_path,
            "evidence_mode": objective.evidence_mode,
            "approval_status": "PENDING",
            "results": {},
            "step_count": 0,
        }
        return graph.invoke(state, config={"configurable": {"thread_id": objective.research_id}})

    @app.post("/research/{research_id}/approval")
    def approve(research_id: str, approved: bool) -> dict[str, Any]:
        try:
            return graph.invoke(Command(resume={"approved": approved}), config={"configurable": {"thread_id": research_id}})
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/research/{research_id}/artifacts")
    def artifacts(research_id: str) -> dict[str, Any]:
        run_dir = tools.store.run_dir(research_id)
        return {"research_id": research_id, "artifacts": sorted(path.name for path in run_dir.iterdir() if path.is_file())}

    @app.get("/research/{research_id}/trace")
    def trace(research_id: str) -> list[dict[str, Any]]:
        path = tools.store.run_dir(research_id) / "trace.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    @app.post("/evals/deterministic")
    def deterministic_evals() -> dict[str, Any]:
        return run_evaluations("deterministic", ResearchManager(DeterministicPlanner()), build_evaluation_cases()).model_dump(mode="json")

    return app
