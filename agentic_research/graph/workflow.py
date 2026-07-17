from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agentic_research.agents import DeterministicPlanner, ResearchManager
from agentic_research.contracts import ExperimentPlan, ToolResult
from agentic_research.execution import IdempotentToolExecutor
from agentic_research.graph.state import ResearchState
from agentic_research.tools import TradeBotReadOnlyTools


TOOL_ACTIONS = {
    "get_strategy_contract",
    "validate_dataset",
    "audit_existing_research_report",
    "run_temporal_semantics_tests",
    "run_structural_backtest",
    "run_wfa",
    "run_adversarial_review",
    "create_certification_bundle",
    "propose_next_hypotheses",
}


def build_research_graph(
    tools: TradeBotReadOnlyTools,
    manager: ResearchManager | None = None,
    checkpointer: Any | None = None,
    executor: IdempotentToolExecutor | None = None,
):
    manager = manager or ResearchManager(DeterministicPlanner())

    def execute(state: ResearchState, tool_name: str, arguments: dict[str, Any], operation: Callable[[], ToolResult]) -> ToolResult:
        if executor is None:
            return operation()
        return executor.execute(research_id=state["research_id"], tool_name=tool_name, arguments=arguments, operation=operation)

    def decide(state: ResearchState) -> dict[str, Any]:
        steps = int(state.get("step_count", 0)) + 1
        if steps > 20:
            return {"next_action": "finish", "status": "FAILED_STEP_BUDGET", "error": "maximum_agent_steps_exceeded", "step_count": steps}
        action = manager.next_action(dict(state))
        return {"next_action": action, "step_count": steps, "status": "WAITING_APPROVAL" if action == "request_approval" else "RUNNING"}

    def route(state: ResearchState) -> str:
        return str(state["next_action"])

    def get_contract(state: ResearchState) -> dict[str, Any]:
        result = execute(state, "get_strategy_contract", {"strategy_id": state["strategy_id"]}, lambda: tools.get_strategy_contract(state["research_id"], state["strategy_id"]))
        return _record(state, result)

    def validate_dataset(state: ResearchState) -> dict[str, Any]:
        result = execute(state, "validate_dataset", {"dataset_path": state["dataset_path"]}, lambda: tools.validate_dataset(state["research_id"], state["dataset_path"]))
        return _record(state, result)

    def audit_report(state: ResearchState) -> dict[str, Any]:
        result = execute(state, "audit_existing_research_report", {"report_path": state["dataset_path"], "strategy_id": state["strategy_id"]}, lambda: tools.audit_existing_research_report(state["research_id"], state["dataset_path"], state["strategy_id"]))
        return _record(state, result)

    def create_plan(state: ResearchState) -> dict[str, Any]:
        mode = str(state.get("evidence_mode") or "STRUCTURAL_DATASET")
        experiments = ["legacy_report_audit", "adversarial_review"] if mode == "LEGACY_REPORT_AUDIT" else ["temporal_semantics", "unchanged_production_baseline", "wfa", "adversarial_review"]
        plan = ExperimentPlan(
            research_id=state["research_id"],
            strategy_id=state["strategy_id"],
            dataset_path=state["dataset_path"],
            evidence_mode=mode,
            experiments=experiments,
            maximum_strategy_variants=1,
            production_changes=False,
            unsupported_claims=["live_profitability", "autonomous_production_promotion"],
        )
        tools.store.write_json(state["research_id"], "approved_plan_pending.json", plan.model_dump(mode="json"))
        return {"experiment_plan": plan.model_dump(mode="json"), "status": "WAITING_APPROVAL"}

    def request_approval(state: ResearchState) -> dict[str, Any]:
        response = interrupt({
            "type": "research_plan_approval",
            "research_id": state["research_id"],
            "plan": state["experiment_plan"],
            "read_only": True,
            "production_changes": False,
        })
        approved = bool(response.get("approved")) if isinstance(response, dict) else bool(response)
        if not approved:
            return {"approval_status": "REJECTED", "status": "STOPPED_BY_HUMAN", "next_action": "finish"}
        tools.store.write_json(state["research_id"], "approved_plan.json", state["experiment_plan"])
        return {"approval_status": "APPROVED", "status": "RUNNING"}

    def temporal(state: ResearchState) -> dict[str, Any]:
        return _record(state, execute(state, "run_temporal_semantics_tests", {}, lambda: tools.run_temporal_semantics_tests(state["research_id"])))

    def baseline(state: ResearchState) -> dict[str, Any]:
        return _record(state, execute(state, "run_structural_backtest", {"dataset_path": state["dataset_path"]}, lambda: tools.run_structural_backtest(state["research_id"], state["dataset_path"])))

    def wfa(state: ResearchState) -> dict[str, Any]:
        return _record(state, execute(state, "run_wfa", {"dataset_path": state["dataset_path"]}, lambda: tools.run_wfa(state["research_id"], state["dataset_path"])))

    def critic(state: ResearchState) -> dict[str, Any]:
        current = {name: ToolResult.model_validate(value) for name, value in (state.get("results") or {}).items()}
        result = execute(state, "run_adversarial_review", {name: item.result_hash for name, item in current.items()}, lambda: tools.run_adversarial_review(state["research_id"], current))
        return _record(state, result)

    def bundle(state: ResearchState) -> dict[str, Any]:
        results = {name: ToolResult.model_validate(value) for name, value in (state.get("results") or {}).items()}
        result = execute(state, "create_certification_bundle", {name: item.result_hash for name, item in results.items()}, lambda: tools.create_certification_bundle(state["research_id"], results))
        update = _record(state, result)
        update["final_verdict"] = str(result.payload.get("decision", {}).get("verdict"))
        return update

    def propose_hypotheses(state: ResearchState) -> dict[str, Any]:
        results = {name: ToolResult.model_validate(value) for name, value in (state.get("results") or {}).items()}
        result = execute(state, "propose_next_hypotheses", {name: item.result_hash for name, item in results.items()}, lambda: tools.propose_next_hypotheses(state["research_id"], state["strategy_id"], results))
        return _record(state, result)

    def finish(state: ResearchState) -> dict[str, Any]:
        status = state.get("status")
        if status in {"STOPPED_BY_HUMAN", "FAILED_STEP_BUDGET"}:
            return {"status": status}
        if "create_certification_bundle" not in (state.get("results") or {}):
            return {"status": "INCOMPLETE_RESEARCH", "error": "certification_bundle_missing"}
        return {"status": "COMPLETED"}

    graph = StateGraph(ResearchState)
    graph.add_node("manager", decide)
    graph.add_node("get_strategy_contract", get_contract)
    graph.add_node("validate_dataset", validate_dataset)
    graph.add_node("audit_existing_research_report", audit_report)
    graph.add_node("create_experiment_plan", create_plan)
    graph.add_node("request_approval", request_approval)
    graph.add_node("run_temporal_semantics_tests", temporal)
    graph.add_node("run_structural_backtest", baseline)
    graph.add_node("run_wfa", wfa)
    graph.add_node("run_adversarial_review", critic)
    graph.add_node("create_certification_bundle", bundle)
    graph.add_node("propose_next_hypotheses", propose_hypotheses)
    graph.add_node("finish", finish)
    graph.add_edge(START, "manager")
    graph.add_conditional_edges("manager", route, {action: action for action in (*TOOL_ACTIONS, "create_experiment_plan", "request_approval", "finish")})
    for node in (*TOOL_ACTIONS, "create_experiment_plan", "request_approval"):
        graph.add_edge(node, "manager")
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)


def _record(state: ResearchState, result: ToolResult) -> dict[str, Any]:
    results = dict(state.get("results") or {})
    results[result.tool] = result.model_dump(mode="json")
    return {"results": results, "status": "RUNNING"}
