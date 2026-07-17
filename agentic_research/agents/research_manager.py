from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol


ALLOWED_ACTIONS = (
    "get_strategy_contract",
    "validate_dataset",
    "create_experiment_plan",
    "request_approval",
    "run_temporal_semantics_tests",
    "run_structural_backtest",
    "run_wfa",
    "create_certification_bundle",
    "finish",
)


class Planner(Protocol):
    def choose_next(self, state: dict[str, Any]) -> str: ...


@dataclass
class DeterministicPlanner:
    """Fail-closed local planner used for tests and zero-cost offline demos."""

    def choose_next(self, state: dict[str, Any]) -> str:
        results = state.get("results") or {}
        if "get_strategy_contract" not in results:
            return "get_strategy_contract"
        if "validate_dataset" not in results:
            return "validate_dataset"
        if not state.get("experiment_plan"):
            return "create_experiment_plan"
        if state.get("approval_status") == "REJECTED":
            return "finish"
        if state.get("approval_status") != "APPROVED":
            return "request_approval"
        if "run_temporal_semantics_tests" not in results:
            return "run_temporal_semantics_tests"
        if "run_structural_backtest" not in results:
            return "run_structural_backtest"
        if "run_wfa" not in results:
            return "run_wfa"
        if "create_certification_bundle" not in results:
            return "create_certification_bundle"
        return "finish"


class GeminiPlanner:
    """Gemini-backed action selector. Tool execution remains deterministic and read-only."""

    def __init__(self, model: str = "gemini-2.5-flash", api_key: str | None = None):
        from google import genai
        self.client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
        self.model = model

    def choose_next(self, state: dict[str, Any]) -> str:
        prompt = {
            "role": "TradeBot read-only research manager",
            "instruction": "Choose exactly one allowed next action. Never request production mutation, broker access, parameter tuning, or live trading.",
            "allowed_actions": ALLOWED_ACTIONS,
            "state": state,
        }
        response = self.client.models.generate_content(
            model=self.model,
            contents=json.dumps(prompt, sort_keys=True, default=str),
            config={"response_mime_type": "application/json", "response_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": list(ALLOWED_ACTIONS)}}, "required": ["action"]}},
        )
        parsed = json.loads(response.text)
        action = parsed.get("action")
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"planner_returned_forbidden_action:{action}")
        return action


@dataclass
class ResearchManager:
    planner: Planner

    def next_action(self, state: dict[str, Any]) -> str:
        action = self.planner.choose_next(state)
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"forbidden_action:{action}")
        return action
