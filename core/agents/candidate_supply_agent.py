from __future__ import annotations

from pathlib import Path

from core.runtime_candidate_starvation_trace import RUNTIME_CANDIDATE_STARVATION_TRACE_FILENAME
from .contracts import AgentFinding, AgentReport, build_read_only_agent_report
from .readers import discover_runtime_artifacts, read_json_file


def analyze_candidate_supply(
    *,
    runtime_dir: Path,
    logs_dir: Path,
    session_dir: Path | None = None,
    tail_lines: int = 5000,
) -> AgentReport:
    artifacts = discover_runtime_artifacts(runtime_root=runtime_dir, logs_root=logs_dir, session_root=session_dir)
    trace = read_json_file(artifacts["candidate_starvation_trace"])
    metrics = {
        "raw_candidate_count": int(trace.get("raw_candidate_count") or 0),
        "real_candidate_count": int(trace.get("real_candidate_count") or 0),
        "soft_reject_count": int(trace.get("post_soft_reject_count") or 0),
        "synthetic_count": int(trace.get("synthetic_count") or 0),
        "fallback_count": int(trace.get("fallback_count") or 0),
        "option_scan_considered": int(trace.get("option_scan_considered") or 0),
        "option_scan_survivors": int(trace.get("post_scan_survivor_count") or 0),
        "ranked_candidate_count": int(trace.get("ranked_candidate_count") or 0),
        "real_ranked_candidate_count": int(trace.get("real_ranked_candidate_count") or 0),
        "top_reject_reasons": trace.get("top_blockers") or trace.get("top_reject_reasons") or {},
    }
    findings: list[AgentFinding] = []
    if metrics["raw_candidate_count"] == 0:
        findings.append(
            AgentFinding(
                code="CANDIDATE_SUPPLY_EMPTY",
                severity="BLOCKER",
                layer="candidate_supply",
                message="No real candidates were generated before Phase2.",
                confidence="HIGH",
                recommended_action="Inspect feed truth, regime readiness, and TradeBuilder output.",
                files_likely_involved=("strategies/trade_builder.py", "core/runtime_candidate_starvation_trace.py"),
                tests_needed=("tests/test_candidate_supply_agent.py",),
            )
        )
    elif metrics["real_candidate_count"] == 0 and metrics["raw_candidate_count"] > 0:
        findings.append(
            AgentFinding(
                code="NO_REAL_CANDIDATES_SURVIVED",
                severity="WARN",
                layer="candidate_supply",
                message="Candidate-shaped objects existed, but none were real executable opportunities.",
                confidence="HIGH",
                recommended_action="Separate advisory or synthetic rows from real opportunities.",
                files_likely_involved=("strategies/trade_builder.py",),
                tests_needed=("tests/test_candidate_supply_agent.py",),
            )
        )
    verdict = "BLOCKER" if any(item.severity == "BLOCKER" for item in findings) else ("WARN" if findings else "PASS")
    return build_read_only_agent_report(
        agent_name="candidate_supply",
        verdict=verdict,
        confidence="HIGH" if findings else "LOW",
        first_failing_event="RAW_CANDIDATE_COUNT=0" if metrics["raw_candidate_count"] == 0 else None,
        findings=tuple(findings),
        not_root_cause=("Ranking and Phase2 cannot be blamed until real candidates exist.",),
        next_fix_recommendation="Inspect TradeBuilder output and upstream feed/regime readiness.",
        metrics=metrics,
    )
