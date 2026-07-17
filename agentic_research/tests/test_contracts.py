from pathlib import Path

import pytest

from agentic_research.contracts import ExperimentPlan, ResearchObjective, ToolResult, load_config


def test_objective_rejects_production_and_live_authority():
    with pytest.raises(ValueError, match="production_changes_forbidden"):
        ResearchObjective(research_id="abc", dataset_path="x", production_changes_allowed=True)
    with pytest.raises(ValueError, match="live_trading_forbidden"):
        ResearchObjective(research_id="abc", dataset_path="x", live_trading_allowed=True)


def test_plan_rejects_unapproved_experiment():
    with pytest.raises(ValueError, match="unapproved_experiments"):
        ExperimentPlan(research_id="abc", strategy_id="trend_pullback_v1", dataset_path="x", experiments=["optimize_everything"])


def test_tool_result_hash_is_deterministic():
    first = ToolResult(tool="x", status="SUCCESS", payload={"b": 2, "a": 1}).with_hash()
    second = ToolResult(tool="x", status="SUCCESS", payload={"a": 1, "b": 2}).with_hash()
    assert first.result_hash == second.result_hash


def test_json_compatible_yaml_contracts_load():
    root = Path(__file__).parents[1]
    assert load_config(root / "config" / "strategy_spec.yaml")["strategy_id"] == "trend_pullback_v1"
