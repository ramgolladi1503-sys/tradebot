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
        self.calls = []

    def _ok(self, name, payload=None, blockers=None, status="SUCCESS"):
        self.calls.append(name)
        return ToolResult(tool=name, status=status, payload=payload or {}, blockers=blockers or []).with_hash()

    def get_strategy_contract(self, research_id, strategy_id): return self._ok("get_strategy_contract")
    def validate_dataset(self, research_id, dataset_path): return self._ok("validate_dataset")
    def audit_existing_research_report(self, research_id, report_path, strategy_id): return self._ok("audit_existing_research_report", status="REJECTED", blockers=["legacy_dataset_zero_volume"])
    def run_temporal_semantics_tests(self, research_id): return self._ok("run_temporal_semantics_tests", {"causality_violations": 0})
    def run_structural_backtest(self, research_id, dataset_path): return self._ok("run_structural_backtest", {"trades": 30, "candidate_rows": [], "option_execution_certified": False})
    def run_wfa(self, research_id, dataset_path): return self._ok("run_wfa", {"holdout": {"trades": 10, "net_expectancy_bps": -1, "profit_factor": 0.8}, "positive_oos_partition_fraction": 0, "purged_embargoed_option_wfa_used": False})
    def run_adversarial_review(self, research_id, results): return self._ok("run_adversarial_review", {"report": {"critic_id": "fake", "independent": True, "findings": [], "summary": "ok", "source_result_hashes": {}}})
    def create_certification_bundle(self, research_id, results): return self._ok("create_certification_bundle", {"decision": {"verdict": "REJECTED_OVERFIT"}})
    def propose_next_hypotheses(self, research_id, strategy_id, results): return self._ok("propose_next_hypotheses", {"created": [], "duplicates": []})


def test_structural_graph_pauses_resumes_and_invokes_critic():
    tools = FakeTools()
    graph = build_research_graph(tools, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "r1"}}
    paused = graph.invoke({
        "research_id": "r1",
        "strategy_id": "trend_pullback_v1",
        "dataset_path": "fixture.jsonl",
        "evidence_mode": "STRUCTURAL_DATASET",
        "approval_status": "PENDING",
        "results": {},
        "step_count": 0,
    }, config=config)
    assert paused["status"] == "WAITING_APPROVAL"
    completed = graph.invoke(Command(resume={"approved": True}), config=config)
    assert completed["status"] == "COMPLETED"
    assert "run_adversarial_review" in completed["results"]
    assert "propose_next_hypotheses" in completed["results"]
    assert tools.calls.count("get_strategy_contract") == 1
    assert tools.calls.count("validate_dataset") == 1


def test_legacy_graph_rejects_report_without_running_backtest():
    tools = FakeTools()
    graph = build_research_graph(tools, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "legacy"}}
    paused = graph.invoke({
        "research_id": "legacy",
        "strategy_id": "trend_pullback_v1",
        "dataset_path": "report.json",
        "evidence_mode": "LEGACY_REPORT_AUDIT",
        "approval_status": "PENDING",
        "results": {},
        "step_count": 0,
    }, config=config)
    assert paused["status"] == "WAITING_APPROVAL"
    completed = graph.invoke(Command(resume={"approved": True}), config=config)
    assert completed["status"] == "COMPLETED"
    assert "audit_existing_research_report" in completed["results"]
    assert "run_structural_backtest" not in completed["results"]
