from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from agentic_research.agents import DeterministicPlanner, GeminiPlanner, ResearchManager
from agentic_research.contracts import ResearchObjective
from agentic_research.graph import build_research_graph
from agentic_research.tools import TradeBotReadOnlyTools


def create_app(repo_root: Path) -> FastAPI:
    repo_root = Path(repo_root).resolve()
    tools = TradeBotReadOnlyTools(repo_root)
    state_dir = repo_root / "agentic_research" / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(state_dir / "api_checkpoints.sqlite", check_same_thread=False)
    planner_name = os.environ.get("AGENTIC_RESEARCH_PLANNER", "deterministic").strip().lower()
    planner = GeminiPlanner(model=os.environ.get("AGENTIC_RESEARCH_MODEL", "gemini-2.5-flash")) if planner_name == "gemini" else DeterministicPlanner()
    graph = build_research_graph(tools, manager=ResearchManager(planner), checkpointer=SqliteSaver(connection))
    app = FastAPI(title="TradeBot Agentic Research", version="0.1.0")
    app.state.graph = graph
    app.state.sqlite_connection = connection

    @app.on_event("shutdown")
    def close_state_store() -> None:
        connection.close()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "read_only": True, "live_trading": False, "planner": planner_name, "checkpoint_store": "sqlite"}

    @app.post("/research")
    def start(objective: ResearchObjective) -> dict[str, Any]:
        state = {
            "research_id": objective.research_id,
            "objective": objective.model_dump(mode="json"),
            "strategy_id": objective.strategy_id,
            "dataset_path": objective.dataset_path,
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

    return app
