from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from core.events import write_json_atomic
from core.paths import logs_dir as default_logs_dir, runtime_dir as default_runtime_dir

from .candidate_supply_agent import analyze_candidate_supply
from .contracts import AgentReport, CommandCenterReport
from .edge_measurement_agent import analyze_edge_measurement
from .feed_stability_agent import analyze_feed_stability
from .live_rca_agent import analyze_live_rca
from .phase2_ranking_truth_agent import analyze_phase2_ranking_truth
from .safety_regression_gate_agent import analyze_safety_regression_gate


COMMAND_CENTER_SCHEMA_VERSION = 1
AGENT_ORDER = ("live_rca", "feed_stability", "candidate_supply", "phase2_ranking_truth", "edge_measurement", "safety_regression_gate")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _render_markdown(report: CommandCenterReport) -> str:
    lines = [
        "# Tradebot Agent Command Center",
        "",
        f"- Generated at: `{report.generated_at}`",
        f"- First blocker layer: `{report.first_blocker_layer or 'UNKNOWN'}`",
        f"- Next PR recommendation: `{report.next_pr_recommendation}`",
        "",
        "## Safety Summary",
    ]
    for key, value in sorted(report.safety_summary.items()):
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Agents"])
    for agent in report.agents:
        lines.extend(
            [
                f"### {agent.agent_name}",
                f"- Verdict: `{agent.verdict}`",
                f"- Confidence: `{agent.confidence}`",
                f"- First failing event: `{agent.first_failing_event or 'UNKNOWN'}`",
                f"- Next fix: `{agent.next_fix_recommendation}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def _agent_reports(
    *,
    runtime_dir: Path,
    logs_dir: Path,
    session_dir: Path | None,
    tail_lines: int,
    agents: Sequence[str],
    offline_fixtures: Path | None,
    changed_paths: Iterable[str] | None,
) -> list[AgentReport]:
    requested = set(agents) if agents and agents != ("all",) else set(AGENT_ORDER)
    reports: list[AgentReport] = []
    if "live_rca" in requested:
        reports.append(analyze_live_rca(runtime_dir=runtime_dir, logs_dir=logs_dir, session_dir=session_dir, tail_lines=tail_lines))
    if "feed" in requested or "feed_stability" in requested:
        reports.append(analyze_feed_stability(runtime_dir=runtime_dir, logs_dir=logs_dir, session_dir=session_dir, tail_lines=tail_lines))
    if "candidate" in requested or "candidate_supply" in requested:
        reports.append(analyze_candidate_supply(runtime_dir=runtime_dir, logs_dir=logs_dir, session_dir=session_dir, tail_lines=tail_lines))
    if "phase2" in requested or "phase2_ranking_truth" in requested:
        reports.append(analyze_phase2_ranking_truth(runtime_dir=runtime_dir, logs_dir=logs_dir, session_dir=session_dir, tail_lines=tail_lines))
    if "edge" in requested or "edge_measurement" in requested:
        reports.append(analyze_edge_measurement(runtime_dir=runtime_dir, logs_dir=logs_dir, session_dir=session_dir, tail_lines=tail_lines, offline_fixtures=offline_fixtures))
    if "safety" in requested or "safety_regression_gate" in requested:
        reports.append(analyze_safety_regression_gate(runtime_dir=runtime_dir, logs_dir=logs_dir, session_dir=session_dir, tail_lines=tail_lines, changed_paths=changed_paths))
    return reports


def run_agent_command_center(
    *,
    runtime_dir: Path | None = None,
    logs_dir: Path | None = None,
    session_dir: Path | None = None,
    out_dir: Path | None = None,
    tail_lines: int = 5000,
    agents: Sequence[str] = ("all",),
    fmt: str = "both",
    fail_on_blocker: bool = False,
    offline_fixtures: Path | None = None,
    changed_paths_file: Path | None = None,
    changed_paths: Iterable[str] | None = None,
) -> CommandCenterReport:
    runtime_root = Path(runtime_dir) if runtime_dir is not None else default_runtime_dir()
    logs_root = Path(logs_dir) if logs_dir is not None else default_logs_dir()
    output_root = Path(out_dir) if out_dir is not None else (runtime_root / "agent_reports")
    output_root.mkdir(parents=True, exist_ok=True)

    agent_reports = _agent_reports(
        runtime_dir=runtime_root,
        logs_dir=logs_root,
        session_dir=session_dir,
        tail_lines=tail_lines,
        agents=agents,
        offline_fixtures=offline_fixtures,
        changed_paths=changed_paths or (_load_changed_paths(changed_paths_file) if changed_paths_file else None),
    )
    blocker_layers = [agent.agent_name for agent in agent_reports if agent.verdict == "BLOCKER"]
    first_blocker_layer = blocker_layers[0] if blocker_layers else None
    if blocker_layers:
        root_cause_summary = f"First blocker layer is {first_blocker_layer}"
        next_pr_recommendation = f"Focus the next PR on {first_blocker_layer.replace('_', ' ')}."
    else:
        root_cause_summary = "No blocker layer identified from current evidence."
        next_pr_recommendation = "Collect more evidence or extend the current runtime snapshot."

    safety_summary = {
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_allowed": False,
        "no_order_action": True,
    }
    metrics_summary = {
        "agent_count": len(agent_reports),
        "blocker_count": len(blocker_layers),
        "verdict_counts": {
            "BLOCKER": sum(1 for item in agent_reports if item.verdict == "BLOCKER"),
            "WARN": sum(1 for item in agent_reports if item.verdict == "WARN"),
            "PASS": sum(1 for item in agent_reports if item.verdict == "PASS"),
            "UNKNOWN": sum(1 for item in agent_reports if item.verdict == "UNKNOWN"),
        },
    }
    report = CommandCenterReport(
        schema_version=COMMAND_CENTER_SCHEMA_VERSION,
        generated_at=_now_iso(),
        analyzed_paths=tuple(str(path) for path in [runtime_root, logs_root] + ([Path(session_dir)] if session_dir else [])),
        agents=tuple(agent_reports),
        first_blocker_layer=first_blocker_layer,
        root_cause_summary=root_cause_summary,
        next_pr_recommendation=next_pr_recommendation,
        safety_summary=safety_summary,
        metrics_summary=metrics_summary,
    )

    json_path = output_root / "agent_command_center_latest.json"
    md_path = output_root / "agent_command_center_latest.md"
    write_json_atomic(json_path, report.to_dict())
    md_path.write_text(_render_markdown(report), encoding="utf-8")

    per_agent_paths = {
        "live_rca": output_root / "live_rca_latest.json",
        "feed_stability": output_root / "feed_stability_latest.json",
        "candidate_supply": output_root / "candidate_supply_latest.json",
        "phase2_ranking_truth": output_root / "phase2_ranking_truth_latest.json",
        "edge_measurement": output_root / "edge_measurement_latest.json",
        "safety_regression_gate": output_root / "safety_regression_gate_latest.json",
    }
    for agent in agent_reports:
        path = per_agent_paths.get(agent.agent_name)
        if path is not None:
            write_json_atomic(path, agent.to_dict())

    if fail_on_blocker and blocker_layers:
        raise SystemExit(f"agent_command_center_blocked first_blocker_layer={first_blocker_layer}")
    return report


def _load_changed_paths(path: Path | None) -> list[str]:
    if path is None or not path.exists() or not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
