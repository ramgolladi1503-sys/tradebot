from __future__ import annotations

from collections import Counter
import re
from pathlib import Path
from typing import Any

from .contracts import AgentFinding, AgentReport, build_read_only_agent_report
from .evidence_refs import evidence_ref_from_mapping, evidence_ref_from_text
from .readers import discover_runtime_artifacts, grep_lines, read_json_file, read_jsonl_file
from .timeline import TimelineEvent, sort_timeline_events


_EXPLICIT_AUTH_FAILURE_PATTERNS = (
    "AUTH_FAILURE",
    "KITE_AUTH_FAILURE",
    "KITE_SESSION_INVALID",
    "KITE_ACCESS_TOKEN_MISSING",
    "KITE_ACCESS_TOKEN_INVALID",
    "CREDENTIAL_GUARD_BLOCKED",
    "AUTH_BLOCKED",
    "LOGIN_REQUIRED",
    "TOKEN_EXPIRED",
    "UNAUTHORIZED",
)


def _is_unit_test_log_line(text: str) -> bool:
    upper = text.upper()
    return '"SOURCE": "UNIT_TEST"' in upper or "'SOURCE': 'UNIT_TEST'" in upper or 'SOURCE=UNIT_TEST' in upper


def _has_explicit_auth_failure(text: str) -> bool:
    for line in text.splitlines():
        upper = line.upper()
        if any(pattern in upper for pattern in _EXPLICIT_AUTH_FAILURE_PATTERNS):
            return True
        if re.search(r"\b401\b", upper) and re.search(r"\b(?:AUTH|TOKEN|SESSION|UNAUTHORIZED)\b", upper):
            return True
    return False


def _event_match(line: str) -> str | None:
    text = line.upper()
    patterns = [
        "AUTH_FAILURE",
        "KITE_AUTH_FAILURE",
        "KITE_SESSION_INVALID",
        "KITE_ACCESS_TOKEN_MISSING",
        "KITE_ACCESS_TOKEN_INVALID",
        "CREDENTIAL_GUARD_BLOCKED",
        "AUTH_BLOCKED",
        "LOGIN_REQUIRED",
        "TOKEN_EXPIRED",
        "UNAUTHORIZED",
        "FEED_CONNECT_FAILURE",
        "FEED_ON_CONNECT_SUBSCRIBE",
        "FEED_OPTION_PRUNE_REFRESH",
        "FEED_REBALANCE_APPLIED",
        "FEED_REBALANCE_SKIPPED",
        "CONNECTION ERROR: 1006",
        "KITE_WS_ERROR CODE=1006",
        "CONNECTION CLOSED: 1006",
        "REACTORNOTRESTARTABLE",
        "RECOVERY_BLOCKED",
        "PHASE2: NO INPUT CANDIDATES",
        "PHASE2: NO VALID CANDIDATES AFTER FILTERING",
        "FINAL_EMIT_ABORT",
        "TB_RANKED_COUNT_EXECUTABLE",
    ]
    for pattern in patterns:
        if pattern in text:
            return pattern
    return None


def _timeline_from_logs(paths: list[Path | None], tail_lines: int) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    for match in grep_lines(paths=paths, patterns=[
        "AUTH",
        "FEED_CONNECT_FAILURE",
        "FEED_ON_CONNECT_SUBSCRIBE",
        "FEED_OPTION_PRUNE_REFRESH",
        "FEED_REBALANCE_APPLIED",
        "FEED_REBALANCE_SKIPPED",
        "1006",
        "REACTORNOTRESTARTABLE",
        "RECOVERY_BLOCKED",
        "PHASE2: No input candidates",
        "PHASE2: No valid candidates after filtering",
        "FINAL_EMIT_ABORT",
        "TB_RANKED_COUNT_EXECUTABLE",
    ], tail_lines=tail_lines):
        excerpt = str(match.get("excerpt") or "")
        if _is_unit_test_log_line(excerpt):
            continue
        events.append(
            TimelineEvent(
                source_path=str(match.get("source_path") or ""),
                line_number=match.get("line_number"),
                event=_event_match(excerpt),
                ts_epoch=None,
                excerpt=excerpt,
                fields={},
            )
        )
    return sort_timeline_events(events)


def analyze_live_rca(
    *,
    runtime_dir: Path,
    logs_dir: Path,
    session_dir: Path | None = None,
    tail_lines: int = 5000,
) -> AgentReport:
    artifacts = discover_runtime_artifacts(runtime_root=runtime_dir, logs_root=logs_dir, session_root=session_dir)
    depth_log = artifacts["depth_ws_watchdog"]
    feed_runtime = read_json_file(artifacts["feed_runtime_runtime_logs"] or artifacts["feed_runtime_logs"] or artifacts["feed_runtime_runtime"])
    ranked_runtime = read_json_file(artifacts["ranked_pipeline_runtime"])
    starvation_trace = read_json_file(artifacts["candidate_starvation_trace"])
    lines_timeline = _timeline_from_logs([depth_log], tail_lines=tail_lines)
    raw_depth_text = depth_log.read_text(encoding="utf-8", errors="replace") if depth_log and depth_log.exists() else ""
    filtered_depth_text = "\n".join(
        line for line in raw_depth_text.splitlines() if not _is_unit_test_log_line(line)
    )

    timeline_rows = [item.to_evidence_ref() for item in lines_timeline[:40]]
    metrics = {
        "timeline_event_count": len(lines_timeline),
        "ws1006_count": sum(1 for item in lines_timeline if item.event and "1006" in item.event),
        "reactor_not_restartable_count": sum(1 for item in lines_timeline if item.event == "REACTORNOTRESTARTABLE"),
        "feed_rebalance_applied_count": sum(1 for item in lines_timeline if item.event == "FEED_REBALANCE_APPLIED"),
        "feed_rebalance_skipped_count": sum(1 for item in lines_timeline if item.event == "FEED_REBALANCE_SKIPPED"),
        "raw_candidate_count": starvation_trace.get("raw_candidate_count"),
        "phase2_input_candidate_count": starvation_trace.get("phase2_input_candidate_count"),
        "ranked_executable_count": ranked_runtime.get("executable_count"),
    }

    first_failing_event = None
    root_cause = "UNKNOWN"
    if _has_explicit_auth_failure(filtered_depth_text) or any(
        item.event
        in {
            "AUTH_FAILURE",
            "KITE_AUTH_FAILURE",
            "KITE_SESSION_INVALID",
            "KITE_ACCESS_TOKEN_MISSING",
            "KITE_ACCESS_TOKEN_INVALID",
            "CREDENTIAL_GUARD_BLOCKED",
            "AUTH_BLOCKED",
            "LOGIN_REQUIRED",
            "TOKEN_EXPIRED",
            "UNAUTHORIZED",
        }
        for item in lines_timeline
    ) or any(
        item.event == "401"
        for item in lines_timeline
    ):
        root_cause = "AUTH_FAILURE"
        first_failing_event = "AUTH_FAILURE"
    elif any("FEED_CONNECT_FAILURE" in (item.event or "") for item in lines_timeline):
        root_cause = "FEED_CONNECT_FAILURE"
    elif any(item.event == "FEED_REBALANCE_APPLIED" for item in lines_timeline):
        root_cause = "SUBSCRIPTION_CHURN"
        first_failing_event = "FEED_REBALANCE_APPLIED"
    elif any("1006" in (item.event or "") for item in lines_timeline):
        root_cause = "WS1006_TERMINAL_CLOSE"
        first_failing_event = "CONNECTION_ERROR:1006"
    elif str(feed_runtime.get("feed_truth_state") or "").upper() in {"DEAD", "RECOVERY_BLOCKED"}:
        root_cause = "FEEDTRUTH_DEAD"
        first_failing_event = "FEED_TRUTH_DEAD"
    elif int(starvation_trace.get("raw_candidate_count") or 0) == 0:
        root_cause = "CANDIDATE_SUPPLY_EMPTY"
        first_failing_event = "RAW_CANDIDATE_COUNT=0"
    elif int(starvation_trace.get("phase2_input_candidate_count") or 0) == 0:
        root_cause = "PHASE2_FILTERED_ALL"
        first_failing_event = "PHASE2_NO_INPUT"
    elif int(ranked_runtime.get("executable_count") or 0) == 0:
        root_cause = "RANKING_NO_EXECUTABLE"
        first_failing_event = "TB_RANKED_COUNT_EXECUTABLE=0"

    findings = (
        AgentFinding(
            code=root_cause,
            severity="BLOCKER" if root_cause != "UNKNOWN" else "WARN",
            layer="live_rca",
            message=f"First failing layer: {root_cause}",
            confidence="HIGH" if root_cause != "UNKNOWN" else "LOW",
            first_seen_ts_epoch=None,
            evidence_refs=tuple(timeline_rows[:3]),
            recommended_action="Inspect the first failing layer and stop blaming downstream stages.",
            files_likely_involved=tuple(str(item.source_path) for item in lines_timeline[:3]),
            tests_needed=("tests/test_live_rca_agent.py",),
        ),
    )
    verdict = "BLOCKER" if root_cause != "UNKNOWN" else "UNKNOWN"
    return build_read_only_agent_report(
        agent_name="live_rca",
        verdict=verdict,
        confidence="HIGH" if root_cause != "UNKNOWN" else "LOW",
        first_failing_event=first_failing_event,
        findings=findings,
        not_root_cause=("Downstream stages are not the first failure when upstream evidence blocks earlier.",),
        next_fix_recommendation=f"Investigate {root_cause.lower()} first." if root_cause != "UNKNOWN" else "Collect more evidence.",
        metrics=metrics,
    )
