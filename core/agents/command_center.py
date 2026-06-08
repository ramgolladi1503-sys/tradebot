from __future__ import annotations

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


COMMAND_CENTER_SCHEMA_VERSION = 2
AGENT_ORDER = ("live_rca", "feed_stability", "candidate_supply", "phase2_ranking_truth", "edge_measurement", "safety_regression_gate")
DOMAIN_LAYERS = ("AUTH", "FEED_STABILITY", "FEED_TRUTH", "CANDIDATE_SUPPLY", "PHASE2_RANKING", "EDGE_MEASUREMENT", "SAFETY", "UNKNOWN")
ACTION_TYPES = (
    "FIX_AUTH",
    "FIX_FEED_LIFECYCLE",
    "FIX_FEED_TRUTH",
    "FIX_CANDIDATE_SUPPLY",
    "FIX_PHASE2_CONTEXT",
    "FIX_RANKING_TRUTH",
    "COLLECT_OUTCOMES",
    "SAFETY_BLOCKER",
    "CONTINUE_OBSERVING",
    "INSUFFICIENT_EVIDENCE",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evidence_text(agent: AgentReport) -> str:
    parts = [agent.agent_name, agent.verdict, agent.confidence, agent.first_failing_event or "UNKNOWN"]
    for finding in agent.findings:
        parts.append(finding.code)
        parts.append(finding.message)
    return " ".join(parts).upper()


def _find_agent(agent_reports: Sequence[AgentReport], name: str) -> AgentReport | None:
    for agent in agent_reports:
        if agent.agent_name == name:
            return agent
    return None


def _candidate_supply_recommendation(agent: AgentReport | None) -> str:
    if agent is None:
        return "Inspect TradeBuilder output and upstream feature readiness before Phase2 or ranking changes."
    subtype = str(agent.metrics.get("first_candidate_supply_zero_subtype") or "").strip().upper()
    if subtype == "CANDIDATE_SUPPLY_ZERO_STRATEGY_QUALIFICATION":
        return "Inspect strategy qualification and regime gate evidence before touching TradeBuilder, Phase2, or ranking."
    if subtype in {"CANDIDATE_SUPPLY_ZERO_LATENCY_GUARD_COOLDOWN", "CANDIDATE_SUPPLY_ZERO_LATENCY_GUARD_DEGRADE_EXIT_ONLY"}:
        return "Inspect latency guard prebuild skip attribution before changing strategy logic."
    if subtype == "CANDIDATE_SUPPLY_ZERO_SLO_FEED_STALE":
        return "Inspect SLO/feed stale transition after initial feed freshness before changing candidate logic."
    if subtype == "CANDIDATE_SUPPLY_ZERO_REGIME_UNSTABLE":
        return "Inspect regime confidence, entropy, and debounced instability before touching TradeBuilder or ranking."
    if subtype == "CANDIDATE_SUPPLY_ZERO_TRADEBUILDER_REACHED_NO_CANDIDATE":
        return "Inspect TradeBuilder rejection details before changing Phase2 or ranking."
    if subtype == "CANDIDATE_SUPPLY_ZERO_TRADEBUILDER_NOT_REACHED":
        return "Inspect strategy qualification before assuming TradeBuilder was reached."
    return "Inspect TradeBuilder output and upstream feature readiness before Phase2 or ranking changes."


def _evidence_scope_from_candidates(feed_scope: str, candidate_scope: str) -> str:
    feed_scope = (feed_scope or "unknown").lower()
    candidate_scope = (candidate_scope or "unknown").lower()
    if candidate_scope == "mixed" or feed_scope == "mixed":
        return "mixed"
    if candidate_scope == "current_session":
        return "current_session" if feed_scope in {"unknown", "current_session"} else "mixed"
    if candidate_scope == "historical_tail":
        return "historical_tail" if feed_scope == "historical_tail" else "mixed"
    return feed_scope if feed_scope != "unknown" else candidate_scope


def _render_markdown(report: CommandCenterReport) -> str:
    evidence_lines: list[str] = []
    for agent in report.agents:
        evidence_lines.append(
            f"- `{agent.agent_name}`: verdict=`{agent.verdict}` confidence=`{agent.confidence}` first_failing_event=`{agent.first_failing_event or 'UNKNOWN'}`"
        )
        for finding in agent.findings:
            evidence_lines.append(f"  - `{finding.code}`: {finding.message}")
    downstream_lines = [f"- {item}" for item in report.downstream_impact] or ["- None identified."]
    not_root_lines = [f"- {item}" for item in report.what_is_not_root_cause] or ["- No downstream exclusions were identified."]
    candidate_supply = _find_agent(report.agents, "candidate_supply")
    candidate_supply_lines: list[str] = []
    if candidate_supply and int(candidate_supply.metrics.get("raw_candidate_count") or 0) == 0 and candidate_supply.metrics.get("first_candidate_supply_zero_subtype"):
        candidate_supply_lines.extend(
            [
                f"- candidate_supply_evidence_scope: `{candidate_supply.metrics.get('candidate_supply_evidence_scope', 'unknown')}`",
                f"- feed_churn_evidence_scope: `{candidate_supply.metrics.get('feed_churn_evidence_scope', 'unknown')}`",
                f"- first_candidate_supply_zero_subtype: `{candidate_supply.metrics.get('first_candidate_supply_zero_subtype', 'UNKNOWN')}`",
                f"- candidate_supply_zero_subtypes: `{', '.join(candidate_supply.metrics.get('candidate_supply_zero_subtypes') or []) or 'NONE'}`",
                f"- feed_was_fresh_before_candidate_supply_zero: `{candidate_supply.metrics.get('feed_was_fresh_before_candidate_supply_zero', 'unknown')}`",
                f"- latency_guard_cooldown_count: `{candidate_supply.metrics.get('latency_guard_cooldown_count', 0)}`",
                f"- latency_guard_degrade_exit_only_count: `{candidate_supply.metrics.get('latency_guard_degrade_exit_only_count', 0)}`",
                f"- slo_feed_stale_count: `{candidate_supply.metrics.get('slo_feed_stale_count', 0)}`",
                "- candidate_supply_zero_timeline:",
            ]
        )
        for item in candidate_supply.metrics.get("candidate_supply_zero_timeline") or []:
            candidate_supply_lines.append(
                f"  - scope=`{item.get('scope', 'unknown')}` subtype=`{item.get('primary_subtype') or 'UNKNOWN'}` symbol=`{item.get('symbol') or 'UNKNOWN'}` stage=`{item.get('stage') or 'UNKNOWN'}`"
            )
    lines = [
        "# Tradebot Agent Command Center",
        "",
        "# What happened?",
        f"- first_blocker_layer: `{report.first_blocker_layer or 'UNKNOWN'}`",
        f"- first_failing_event: `{report.first_failing_event or 'UNKNOWN'}`",
        f"- root_cause_summary: `{report.root_cause_summary}`",
        f"- confidence: `{report.confidence}`",
        f"- next_action_type: `{report.next_action_type}`",
        f"- next_pr_recommendation: `{report.next_pr_recommendation}`",
        f"- evidence_scope: `{report.metrics_summary.get('evidence_scope', 'unknown')}`",
        f"- current_session_feed_fresh: `{report.metrics_summary.get('current_session_feed_fresh', 'unknown')}`",
        f"- stale_evidence_ignored_count: `{report.metrics_summary.get('stale_evidence_ignored_count', 0)}`",
        f"- stale_evidence_reason: `{report.metrics_summary.get('stale_evidence_reason', '') or 'NONE'}`",
        f"- first_current_session_blocker: `{report.metrics_summary.get('first_current_session_blocker', 'UNKNOWN')}`",
        "",
        "# Why this is first",
        f"- {report.root_cause_summary}",
        "",
        "# Evidence",
    ]
    lines.extend(evidence_lines or ["- No agent evidence available."])
    lines.extend(["", "# What is not root cause yet"])
    lines.extend(not_root_lines)
    lines.extend(["", "## Downstream Impact"])
    lines.extend(downstream_lines)
    if candidate_supply_lines:
        lines.extend(["", "## Candidate Supply Zero Attribution"])
        lines.extend(candidate_supply_lines)
    lines.extend(["", "## Metadata", f"- Generated at: `{report.generated_at}`", "", "## Safety Summary"])
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


def _derive_command_center_summary(agent_reports: Sequence[AgentReport]) -> dict[str, object]:
    live_rca = _find_agent(agent_reports, "live_rca")
    feed_stability = _find_agent(agent_reports, "feed_stability")
    candidate_supply = _find_agent(agent_reports, "candidate_supply")
    phase2 = _find_agent(agent_reports, "phase2_ranking_truth")
    edge = _find_agent(agent_reports, "edge_measurement")
    safety = _find_agent(agent_reports, "safety_regression_gate")

    summary: dict[str, object] = {
        "first_blocker_layer": "UNKNOWN",
        "first_failing_event": None,
        "root_cause_summary": "No blocker layer identified from current evidence.",
        "confidence": "LOW",
        "next_action_type": "INSUFFICIENT_EVIDENCE",
        "next_pr_recommendation": "Collect more evidence or extend the current runtime snapshot.",
        "downstream_impact": (),
        "what_is_not_root_cause": (),
        "evidence_scope": "unknown",
        "current_session_feed_fresh": "unknown",
        "stale_evidence_ignored_count": 0,
        "stale_evidence_reason": "",
        "first_current_session_blocker": "UNKNOWN",
    }

    if safety and (safety.verdict == "BLOCKER" or any(f.severity == "BLOCKER" for f in safety.findings)):
        summary.update(
            first_blocker_layer="SAFETY",
            first_failing_event=safety.first_failing_event or "SAFETY_BLOCKER",
            root_cause_summary="Safety evidence blocks progression before trading or runtime changes.",
            confidence="HIGH",
            next_action_type="SAFETY_BLOCKER",
            next_pr_recommendation="Resolve the safety blocker before touching feed, candidate supply, or ranking paths.",
            downstream_impact=(
                "Candidate Supply is downstream until safety blockers are cleared.",
                "Phase2 is downstream until safety allows normal runtime progression.",
                "Edge Measurement is not actionable while safety blocks remain.",
            ),
            what_is_not_root_cause=(
                "Candidate Supply is downstream until safety is cleared.",
                "Phase2 is downstream until safety is cleared.",
                "Edge Measurement is not evaluable until safety permits normal progression.",
            ),
            first_current_session_blocker="SAFETY",
        )
        return summary

    def _metric_bool(agent: AgentReport | None, key: str) -> bool | None:
        if agent is None:
            return None
        value = agent.metrics.get(key)
        if value in (True, False):
            return bool(value)
        if isinstance(value, str):
            lower = value.strip().lower()
            if lower in {"true", "false"}:
                return lower == "true"
            if lower == "unknown":
                return None
        return None

    current_session_feed_fresh = _metric_bool(feed_stability, "current_session_feed_fresh")
    feed_stability_scope = str((feed_stability.metrics.get("evidence_scope") if feed_stability else None) or "unknown") if feed_stability else "unknown"
    stale_evidence_ignored_count = int(feed_stability.metrics.get("stale_evidence_ignored_count") or 0) if feed_stability else 0
    stale_evidence_reason = str(feed_stability.metrics.get("stale_evidence_reason") or "") if feed_stability else ""
    current_feed_stability_blocker = False
    if feed_stability:
        current_feed_stability_blocker = (
            int(feed_stability.metrics.get("current_session_churn_count") or 0) > 0
            or int(feed_stability.metrics.get("current_session_ws1006_count") or 0) > 0
            or any(item.severity == "BLOCKER" and item.code != "STALE_FEED_CHURN" for item in feed_stability.findings)
        )
    stale_only_feed_evidence = bool(feed_stability and current_session_feed_fresh is True and stale_evidence_ignored_count > 0 and not current_feed_stability_blocker)

    feed_truth_dead = False
    if feed_stability:
        feed_runtime_state = str(feed_stability.metrics.get("feed_truth_state") or feed_stability.metrics.get("runtime_state") or "").upper()
        feed_truth_dead = feed_runtime_state in {"DEAD", "RECOVERY_BLOCKED"}
        block_reason_text = str(feed_stability.metrics.get("option_feed_block_reasons") or feed_stability.metrics.get("option_feed_block_reason_by_symbol") or "").upper()
        feed_truth_dead = feed_truth_dead or "NO_LIVE_OPTION_FEED" in block_reason_text or "DEAD" in block_reason_text or "RECOVERY_BLOCKED" in block_reason_text

    if feed_stability and current_feed_stability_blocker and not stale_only_feed_evidence:
        execution_blocked_by_feed_truth = bool(candidate_supply and int(candidate_supply.metrics.get("raw_candidate_count") or 0) > 0 and ranked and int(ranked.metrics.get("executable_count") or 0) == 0)
        summary.update(
            first_blocker_layer="FEED_STABILITY",
            first_failing_event=feed_stability.first_failing_event or "FEED_REBALANCE_APPLIED",
            root_cause_summary="Feed lifecycle churn and websocket recovery state are the first observable blocker.",
            confidence="HIGH" if feed_stability.verdict == "BLOCKER" or feed_stability.findings else "MEDIUM",
            next_action_type="FIX_FEED_LIFECYCLE",
            next_pr_recommendation="Feed Lifecycle Stabilization — prevent stale-option refresh and subscription rebalance mutation when freshness guard says mutation is ineligible; keep dead-WS mutation blocked.",
            downstream_impact=(
                "Candidate Supply is downstream until feed truth is stable.",
                "Phase2 is downstream until real candidates enter the pipeline.",
                "Edge Measurement is not evaluable until executable or paper outcomes exist.",
            ),
            what_is_not_root_cause=(
                "Candidate Supply is downstream until feed is stable.",
                "Phase2 is downstream until real candidates enter Phase2.",
                "Edge Measurement is not evaluable until executable or paper outcomes exist.",
            ),
            evidence_scope=feed_stability_scope,
            current_session_feed_fresh=current_session_feed_fresh if current_session_feed_fresh is not None else "unknown",
            stale_evidence_ignored_count=stale_evidence_ignored_count,
            stale_evidence_reason=stale_evidence_reason,
            first_current_session_blocker="FEED_STABILITY",
        )
        if execution_blocked_by_feed_truth:
            summary["root_cause_summary"] = "Candidates existed, but execution was blocked by feed runtime truth."
            summary["next_pr_recommendation"] = "Feed Lifecycle Stabilization — prevent stale-option refresh and subscription rebalance mutation when freshness guard says mutation is ineligible; keep dead-WS mutation blocked."
        return summary

    if feed_truth_dead or (live_rca and any(finding.code == "FEEDTRUTH_DEAD" for finding in live_rca.findings)):
        summary.update(
            first_blocker_layer="FEED_TRUTH",
            first_failing_event=(feed_stability.first_failing_event if feed_stability else None) or (live_rca.first_failing_event if live_rca else None) or "FEED_TRUTH_DEAD",
            root_cause_summary="Canonical feed truth is dead or recovery-blocked and must be restored before downstream analysis.",
            confidence="HIGH",
            next_action_type="FIX_FEED_TRUTH",
            next_pr_recommendation="Fix canonical feed truth serialization and blocked-state consistency before looking at downstream candidates.",
            downstream_impact=(
                "Candidate Supply is downstream until feed truth is coherent.",
                "Phase2 is downstream until a stable feed produces real candidates.",
                "Edge Measurement is not evaluable until executable outcomes exist.",
            ),
            what_is_not_root_cause=(
                "Candidate Supply is downstream until feed truth is stable.",
                "Phase2 is downstream until feed truth allows real candidates.",
                "Edge Measurement is not evaluable until feed truth is coherent.",
            ),
            first_current_session_blocker="FEED_TRUTH",
        )
        return summary

    if (
        current_session_feed_fresh is True
        and feed_stability is not None
        and not current_feed_stability_blocker
        and live_rca is not None
        and any(finding.code == "STRATEGY_SELECT_NO_QUALIFIED" for finding in live_rca.findings)
    ):
        candidate_scope = str(candidate_supply.metrics.get("candidate_supply_evidence_scope") or "unknown") if candidate_supply else "unknown"
        feed_scope = str(feed_stability.metrics.get("evidence_scope") or "unknown") if feed_stability else "unknown"
        summary.update(
            first_blocker_layer="CANDIDATE_SUPPLY",
            first_failing_event=live_rca.first_failing_event or "N8_STRATEGY_SELECT:NO_STRATEGY_QUALIFIED",
            root_cause_summary="Current-session feed is fresh, but strategy selection produced no qualified candidate.",
            confidence="HIGH",
            next_action_type="FIX_CANDIDATE_SUPPLY",
            next_pr_recommendation=_candidate_supply_recommendation(candidate_supply),
            downstream_impact=(
                "Phase2 is downstream until strategy selection produces candidates.",
                "Edge Measurement is not evaluable until candidates exist.",
            ),
            what_is_not_root_cause=(
                "Feed lifecycle is not the first blocker when current-session feed freshness is healthy.",
                "Edge Measurement is not evaluable until candidates exist.",
            ),
            evidence_scope=_evidence_scope_from_candidates(feed_scope, candidate_scope),
            current_session_feed_fresh=True,
            stale_evidence_ignored_count=stale_evidence_ignored_count,
            stale_evidence_reason=stale_evidence_reason,
            first_current_session_blocker="CANDIDATE_SUPPLY",
        )
        return summary

    feed_healthy = bool(feed_stability) and current_session_feed_fresh is True and not current_feed_stability_blocker
    if candidate_supply and candidate_supply.findings and int(candidate_supply.metrics.get("raw_candidate_count") or 0) == 0 and feed_healthy:
        candidate_scope = str(candidate_supply.metrics.get("candidate_supply_evidence_scope") or "unknown")
        feed_scope = str(feed_stability.metrics.get("evidence_scope") or "unknown") if feed_stability else "unknown"
        summary.update(
            first_blocker_layer="CANDIDATE_SUPPLY",
            first_failing_event=candidate_supply.first_failing_event or "RAW_CANDIDATE_COUNT=0",
            root_cause_summary="Feed is stable enough, but no real candidates were generated before Phase2.",
            confidence="HIGH",
            next_action_type="FIX_CANDIDATE_SUPPLY",
            next_pr_recommendation=_candidate_supply_recommendation(candidate_supply),
            downstream_impact=(
                "Phase2 is downstream until real candidates are produced.",
                "Edge Measurement is not evaluable until executable or paper outcomes exist.",
            ),
            what_is_not_root_cause=(
                "Phase2 is downstream until candidates exist.",
                "Edge Measurement is not evaluable until candidates exist.",
            ),
            evidence_scope=_evidence_scope_from_candidates(feed_scope, candidate_scope),
            current_session_feed_fresh=current_session_feed_fresh if current_session_feed_fresh is not None else "unknown",
            stale_evidence_ignored_count=stale_evidence_ignored_count,
            stale_evidence_reason=stale_evidence_reason,
            first_current_session_blocker="CANDIDATE_SUPPLY",
        )
        return summary

    if phase2 and phase2.findings and (
        any(f.code == "PHASE2_NO_INPUT" for f in phase2.findings)
        or int(phase2.metrics.get("phase2_input_count") or 0) == 0
        or int((phase2.metrics.get("phase2_drop_reason_counts") or {}).get("hard_execution", 0)) > 0
    ):
        summary.update(
            first_blocker_layer="PHASE2_RANKING",
            first_failing_event=phase2.first_failing_event or "PHASE2: No input candidates",
            root_cause_summary="Real candidates reached the ranking boundary, but Phase2 filtered them out or received none.",
            confidence="HIGH",
            next_action_type="FIX_PHASE2_CONTEXT",
            next_pr_recommendation="Inspect execution-truth blockers and Phase2 context before changing ranking math.",
            downstream_impact=("Edge Measurement is not evaluable until Phase2 emits executable or paper outcomes.",),
            what_is_not_root_cause=(
                "Candidate Supply is upstream of this failure when the feed is stable.",
                "Edge Measurement is not evaluable until Phase2 produces outcomes.",
            ),
            evidence_scope=feed_stability_scope,
            current_session_feed_fresh=current_session_feed_fresh if current_session_feed_fresh is not None else "unknown",
            stale_evidence_ignored_count=stale_evidence_ignored_count,
            stale_evidence_reason=stale_evidence_reason,
            first_current_session_blocker="PHASE2_RANKING",
        )
        return summary

    if edge and edge.findings:
        summary.update(
            first_blocker_layer="EDGE_MEASUREMENT",
            first_failing_event=edge.first_failing_event or "EDGE_MEASUREMENT",
            root_cause_summary="Executable or paper outcomes are not available for edge measurement yet.",
            confidence="HIGH",
            next_action_type="COLLECT_OUTCOMES",
            next_pr_recommendation="Collect offline outcomes before trying to measure edge.",
            downstream_impact=("Safety checks remain separate from outcome measurement.",),
            what_is_not_root_cause=(
                "Candidate Supply is upstream of edge measurement.",
                "Phase2 is upstream of edge measurement.",
            ),
            evidence_scope=feed_stability_scope,
            current_session_feed_fresh=current_session_feed_fresh if current_session_feed_fresh is not None else "unknown",
            stale_evidence_ignored_count=stale_evidence_ignored_count,
            stale_evidence_reason=stale_evidence_reason,
            first_current_session_blocker="EDGE_MEASUREMENT",
        )

    return summary


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
    summary = _derive_command_center_summary(agent_reports)

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
        "evidence_scope": summary["evidence_scope"],
        "current_session_feed_fresh": summary["current_session_feed_fresh"],
        "stale_evidence_ignored_count": summary["stale_evidence_ignored_count"],
        "stale_evidence_reason": summary["stale_evidence_reason"],
        "first_current_session_blocker": summary["first_current_session_blocker"],
    }
    report = CommandCenterReport(
        schema_version=COMMAND_CENTER_SCHEMA_VERSION,
        generated_at=_now_iso(),
        analyzed_paths=tuple(str(path) for path in [runtime_root, logs_root] + ([Path(session_dir)] if session_dir else [])),
        agents=tuple(agent_reports),
        first_blocker_layer=str(summary["first_blocker_layer"]),
        first_failing_event=summary["first_failing_event"],
        root_cause_summary=str(summary["root_cause_summary"]),
        confidence=str(summary["confidence"]),
        next_action_type=str(summary["next_action_type"]),
        next_pr_recommendation=str(summary["next_pr_recommendation"]),
        downstream_impact=tuple(summary["downstream_impact"]),
        what_is_not_root_cause=tuple(summary["what_is_not_root_cause"]),
        safety_summary=safety_summary,
        metrics_summary=metrics_summary,
    )

    json_path = output_root / "agent_command_center_latest.json"
    md_path = output_root / "agent_command_center_latest.md"
    write_json_outputs = fmt in {"json", "both"}
    write_markdown_output = fmt in {"markdown", "both"}
    if write_json_outputs:
        write_json_atomic(json_path, report.to_dict())
    if write_markdown_output:
        md_path.write_text(_render_markdown(report), encoding="utf-8")

    per_agent_paths = {
        "live_rca": output_root / "live_rca_latest.json",
        "feed_stability": output_root / "feed_stability_latest.json",
        "candidate_supply": output_root / "candidate_supply_latest.json",
        "phase2_ranking_truth": output_root / "phase2_ranking_truth_latest.json",
        "edge_measurement": output_root / "edge_measurement_latest.json",
        "safety_regression_gate": output_root / "safety_regression_gate_latest.json",
    }
    if write_json_outputs:
        for agent in agent_reports:
            path = per_agent_paths.get(agent.agent_name)
            if path is not None:
                write_json_atomic(path, agent.to_dict())

    if fail_on_blocker and blocker_layers:
        raise SystemExit(f"agent_command_center_blocked first_blocker_layer={summary['first_blocker_layer']}")
    return report


def _load_changed_paths(path: Path | None) -> list[str]:
    if path is None or not path.exists() or not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
