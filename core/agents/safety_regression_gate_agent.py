from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .contracts import AgentFinding, AgentReport, build_read_only_agent_report
from .readers import discover_runtime_artifacts, read_json_file


_FORBIDDEN_SCOPE_MARKERS = (
    "core/broker",
    "core/order",
    "strategies/",
    "dashboard/",
    "run_live.sh",
    "main.py",
)


def _collect_changed_paths(changed_paths: Iterable[str] | None) -> list[str]:
    unique: list[str] = []
    for item in changed_paths or []:
        text = str(item or "").strip()
        if text and text not in unique:
            unique.append(text)
    return unique


def analyze_safety_regression_gate(
    *,
    runtime_dir: Path,
    logs_dir: Path,
    session_dir: Path | None = None,
    tail_lines: int = 5000,
    changed_paths: Iterable[str] | None = None,
) -> AgentReport:
    artifacts = discover_runtime_artifacts(runtime_root=runtime_dir, logs_root=logs_dir, session_root=session_dir)
    feed_runtime = read_json_file(artifacts["feed_runtime_runtime_logs"] or artifacts["feed_runtime_logs"] or artifacts["feed_runtime_runtime"])
    paths = _collect_changed_paths(changed_paths)
    forbidden = [path for path in paths if any(marker in path for marker in _FORBIDDEN_SCOPE_MARKERS)]
    missing_tests = []
    if "scripts/run_tradebot_agent_command_center.py" in paths and "tests/test_agent_command_center.py" not in paths:
        missing_tests.append("tests/test_agent_command_center.py")
    findings: list[AgentFinding] = []
    if forbidden:
        findings.append(
            AgentFinding(
                code="FORBIDDEN_SCOPE_TOUCHED",
                severity="BLOCKER",
                layer="safety_regression",
                message="Forbidden runtime or broker-adjacent files are in the change set.",
                confidence="HIGH",
                recommended_action="Split the change into a narrower evidence-only PR.",
                files_likely_involved=tuple(forbidden),
                tests_needed=("tests/test_safety_regression_gate_agent.py",),
            )
        )
    if str(feed_runtime.get("runtime_state") or "").upper() == "RECOVERY_BLOCKED" and bool(feed_runtime.get("ws_reconnect_allowed", True)):
        findings.append(
            AgentFinding(
                code="RECOVERY_BLOCKED_WEAKENED",
                severity="BLOCKER",
                layer="safety_regression",
                message="Recovery-blocked feed state still reports reconnect allowed.",
                confidence="HIGH",
                recommended_action="Keep terminal recovery fail-closed.",
                files_likely_involved=("core/kite_depth_ws.py",),
                tests_needed=("tests/test_safety_regression_gate_agent.py",),
            )
        )
    if missing_tests:
        findings.append(
            AgentFinding(
                code="MISSING_REQUIRED_TESTS",
                severity="WARN",
                layer="safety_regression",
                message="The scope implies tests that are not present in the change set.",
                confidence="HIGH",
                recommended_action="Add the missing regression coverage before merge.",
                files_likely_involved=tuple(missing_tests),
                tests_needed=tuple(missing_tests),
            )
        )
    verdict = "BLOCKER" if any(item.severity == "BLOCKER" for item in findings) else ("WARN" if findings else "PASS")
    return build_read_only_agent_report(
        agent_name="safety_regression_gate",
        verdict=verdict,
        confidence="HIGH" if findings else "LOW",
        first_failing_event="FORBIDDEN_SCOPE_TOUCHED" if forbidden else None,
        findings=tuple(findings),
        not_root_cause=("A passing safety gate does not prove market edge or live readiness.",),
        next_fix_recommendation="Split or narrow the scope until it is strictly evidence-only.",
        metrics={"changed_paths": paths, "forbidden_paths": forbidden, "missing_tests": missing_tests},
    )
