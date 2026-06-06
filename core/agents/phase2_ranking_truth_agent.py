from __future__ import annotations

from pathlib import Path

from .contracts import AgentFinding, AgentReport, build_read_only_agent_report
from .readers import discover_runtime_artifacts, read_json_file


def analyze_phase2_ranking_truth(
    *,
    runtime_dir: Path,
    logs_dir: Path,
    session_dir: Path | None = None,
    tail_lines: int = 5000,
) -> AgentReport:
    artifacts = discover_runtime_artifacts(runtime_root=runtime_dir, logs_root=logs_dir, session_root=session_dir)
    ranked = read_json_file(artifacts["ranked_pipeline_runtime"])
    feed_runtime = read_json_file(artifacts["feed_runtime_runtime_logs"] or artifacts["feed_runtime_logs"] or artifacts["feed_runtime_runtime"])
    trace = read_json_file(artifacts["candidate_starvation_trace"])

    phase2_state = str(ranked.get("phase2_state") or trace.get("phase2_input_state") or "").strip().upper()
    ranked_count = int(ranked.get("ranked_candidate_count") or ranked.get("input_candidate_count") or 0)
    executable_count = int(ranked.get("executable_count") or 0)
    final_emit_abort_count = int(ranked.get("final_emit_abort_count") or trace.get("final_emit_abort_count") or 0)
    review_queue_execute_count = int(ranked.get("review_queue_execute_count") or 0)
    advisory_only_count = int(ranked.get("advisory_count") or 0)
    queue_only_count = int(ranked.get("queue_only_count") or 0)
    phase2_drop_reason_counts = dict(ranked.get("phase2_drop_reason_counts") or trace.get("phase2_drop_counts") or {})

    metrics = {
        "phase2_input_count": int(trace.get("phase2_input_candidate_count") or ranked.get("input_candidate_count") or 0),
        "phase2_survived_count": int(trace.get("phase2_survivor_count") or ranked.get("survivor_count") or 0),
        "phase2_drop_reason_counts": phase2_drop_reason_counts,
        "ranked_count": ranked_count,
        "executable_ranked_count": executable_count,
        "final_emit_abort_count": final_emit_abort_count,
        "review_queue_execute_count": review_queue_execute_count,
        "advisory_only_count": advisory_only_count,
        "queue_only_count": queue_only_count,
        "feed_truth_state": feed_runtime.get("feed_truth_state"),
        "runtime_state": feed_runtime.get("runtime_state"),
        "execution_truth_blockers": trace.get("blockers") or [],
    }

    findings: list[AgentFinding] = []
    first_failing_event = None
    if phase2_state == "NO_INPUT" or metrics["phase2_input_count"] == 0:
        findings.append(
            AgentFinding(
                code="PHASE2_NO_INPUT",
                severity="BLOCKER",
                layer="phase2_ranking_truth",
                message="Phase2 received no candidates.",
                confidence="HIGH",
                recommended_action="Work upstream; Phase2 cannot filter rows that do not exist.",
                files_likely_involved=("core/engine_phase2_adapter.py",),
                tests_needed=("tests/test_phase2_ranking_truth_agent.py",),
            )
        )
        first_failing_event = "PHASE2: No input candidates"
    elif metrics["phase2_drop_reason_counts"]:
        if int(metrics["phase2_drop_reason_counts"].get("hard_execution", 0)) > 0:
            findings.append(
                AgentFinding(
                    code="PHASE2_HARD_EXECUTION",
                    severity="BLOCKER",
                    layer="phase2_ranking_truth",
                    message="Phase2 dropped candidates for hard-execution reasons.",
                    confidence="HIGH",
                    recommended_action="Inspect execution-truth blockers and hard-execution gating.",
                    files_likely_involved=("core/engine_phase2_adapter.py", "core/runtime_execution_truth.py"),
                    tests_needed=("tests/test_phase2_ranking_truth_agent.py",),
                )
            )
            first_failing_event = "PHASE2: No valid candidates after filtering"
    elif executable_count == 0 and ranked_count > 0:
        findings.append(
            AgentFinding(
                code="RANKING_NO_EXECUTABLE",
                severity="WARN",
                layer="phase2_ranking_truth",
                message="Candidates reached ranking but none were executable.",
                confidence="HIGH",
                recommended_action="Inspect the runtime execution truth and final emit eligibility.",
                files_likely_involved=("core/review_queue.py",),
                tests_needed=("tests/test_phase2_ranking_truth_agent.py",),
            )
        )
        first_failing_event = "TB_RANKED_COUNT_EXECUTABLE=0"

    verdict = "BLOCKER" if any(item.severity == "BLOCKER" for item in findings) else ("WARN" if findings else "PASS")
    return build_read_only_agent_report(
        agent_name="phase2_ranking_truth",
        verdict=verdict,
        confidence="HIGH" if findings else "LOW",
        first_failing_event=first_failing_event,
        findings=tuple(findings),
        not_root_cause=("Phase2 should not be blamed when upstream feed or candidate supply is empty.",),
        next_fix_recommendation="Inspect execution truth and Phase2 drop categories before touching ranking math.",
        metrics=metrics,
    )
