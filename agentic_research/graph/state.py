from __future__ import annotations

from typing import Any, TypedDict


class ResearchState(TypedDict, total=False):
    research_id: str
    objective: dict[str, Any]
    strategy_id: str
    dataset_path: str
    evidence_mode: str
    experiment_plan: dict[str, Any]
    approval_status: str
    next_action: str
    results: dict[str, dict[str, Any]]
    status: str
    final_verdict: str
    error: str
    step_count: int
