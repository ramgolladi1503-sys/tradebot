from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_research.contracts import ToolResult
from agentic_research.graph import build_research_graph


class FakeStore:
    def write_json(self, *args, **kwargs):
        return Path("artifact.json"), "hash"


class FakeTools:
    def __init__(self):
        self.store = FakeStore()

    def _ok(self, name, payload=None):
        return ToolResult(tool=name, status="SUCCESS", payload=payload or {}).with_hash()

    def get_strategy_contract(self, research_id, strategy_id):
        return self._ok("get_strategy_contract")

    def validate_dataset(self, research_id, dataset_path):
        return self._ok("validate_dataset")

    def run_temporal_semantics_tests(self, research_id):
        return self._ok("run_temporal_semantics_tests", {"causality_violations": 0})

    def run_structural_backtest(self, research_id, dataset_path):
        return self._ok("run_structural_backtest", {"trades": 30})

    def run_wfa(self, research_id, dataset_path):
        return self._ok("run_wfa", {"holdout": {"trades": 10, "net_expectancy_bps": -1, "profit_factor": 0.8}, "positive_oos_partition_fraction": 0})

    def create_certification_bundle(self, research_id, results):
        return self._ok("create_certification_bundle", {"decision": {"verdict": "REJECTED_OVERFIT"}})


def test_graph_pauses_for_approval_and_resumes_without_repeating_tools():
    graph = build_research_graph(FakeTools(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "r1"}}
    initial = {
        "research_id": "r1",
        "strategy_id": "trend_pullback_v1",
        "dataset_path": "fixture.jsonl",
        "approval_status": "PENDING",
        "results": {},
        "step_count": 0,
    }
    paused = graph.invoke(initial, config=config)
    assert paused["status"] == "WAITING_APPROVAL"
    assert set(paused["results"]) == {"get_strategy_contract", "validate_dataset"}
    completed = graph.invoke(Command(resume={"approved": True}), config=config)
    assert completed["status"] == "COMPLETED"
    assert completed["final_verdict"] == "REJECTED_OVERFIT"
    assert set(completed["results"]) == {
        "get_strategy_contract",
        "validate_dataset",
        "run_temporal_semantics_tests",
        "run_structural_backtest",
        "run_wfa",
        "create_certification_bundle",
    }
