from __future__ import annotations

import re
from pathlib import Path

from .contracts import AgentFinding, AgentReport, build_read_only_agent_report
from .evidence_refs import evidence_ref_from_mapping, evidence_ref_from_text
from .readers import classify_session_scope, discover_runtime_artifacts, extract_line_fields, grep_lines, read_json_file
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
        "FEED_OPTION_VERIFY_BEGIN",
        "FEED_OPTION_VERIFY_WAITING_TICKS",
        "FEED_OPTION_VERIFY_OK",
        "FEED_OPTION_VERIFY_FAILED",
        "FEED_REBALANCE_APPLIED",
        "FEED_REBALANCE_SKIPPED",
        "CONNECTION ERROR: 1006",
        "KITE_WS_ERROR CODE=1006",
        "CONNECTION CLOSED: 1006",
        "REACTORNOTRESTARTABLE",
        "RECOVERY_BLOCKED",
        "FEED_RECOVERY_BLOCKED",
        "WS1006_PROCESS_RESTART_REQUIRED",
        "FEED_WS_PROCESS_RESTART_REQUIRED",
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
        "FEED_OPTION_VERIFY_BEGIN",
        "FEED_OPTION_VERIFY_WAITING_TICKS",
        "FEED_OPTION_VERIFY_OK",
        "FEED_OPTION_VERIFY_FAILED",
        "FEED_REBALANCE_APPLIED",
        "FEED_REBALANCE_SKIPPED",
        "1006",
        "REACTORNOTRESTARTABLE",
        "RECOVERY_BLOCKED",
        "FEED_RECOVERY_BLOCKED",
        "WS1006_PROCESS_RESTART_REQUIRED",
        "FEED_WS_PROCESS_RESTART_REQUIRED",
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
    strategy_no_qualified = read_json_file(artifacts["strategy_no_qualified_reasons"])
    lines_timeline = _timeline_from_logs([depth_log], tail_lines=tail_lines)
    raw_depth_text = depth_log.read_text(encoding="utf-8", errors="replace") if depth_log and depth_log.exists() else ""
    filtered_depth_text = "\n".join(
        line for line in raw_depth_text.splitlines() if not _is_unit_test_log_line(line)
    )

    timeline_rows = [item.to_evidence_ref() for item in lines_timeline[:40]]
    current_run_id = str(feed_runtime.get("run_id") or "").strip() or None
    current_boot_epoch = None
    try:
        current_boot_epoch = float(feed_runtime.get("boot_epoch")) if feed_runtime.get("boot_epoch") is not None else None
    except Exception:
        current_boot_epoch = None

    def _nested_gate_ok(container: object, key: str) -> bool:
        if not isinstance(container, dict):
            return False
        payload = container.get(key)
        if isinstance(payload, dict):
            if "ok" in payload:
                return bool(payload.get("ok"))
            if "status" in payload:
                return str(payload.get("status") or "").strip().lower() == "ok"
        if isinstance(payload, bool):
            return payload
        return False

    current_session_feed_fresh = (
        str(feed_runtime.get("ws_connected")).lower() == "true"
        and str(feed_runtime.get("runtime_state") or "").upper() not in {"DEAD", "RECOVERY_BLOCKED"}
        and (
            _nested_gate_ok(feed_runtime.get("feed_health_snapshot"), "N2_FEED_FRESH")
            or _nested_gate_ok(feed_runtime.get("gate_status"), "N2_FEED_FRESH")
        )
    )

    current_feed_churn_count = 0
    stale_feed_churn_count = 0
    current_feed_rebalance_applied_count = 0
    current_feed_rebalance_skipped_count = 0
    stale_feed_rebalance_applied_count = 0
    stale_feed_rebalance_skipped_count = 0
    current_ws1006_count = 0
    stale_ws1006_count = 0
    current_option_subscribe_count = 0
    current_option_verify_begin_count = 0
    current_option_verify_waiting_count = 0
    current_option_verify_ok_count = 0
    current_option_verify_failed_count = 0
    current_option_verify_failure_detail = ""
    current_no_live_option_feed_after_subscribe_count = 0
    current_recovery_blocked_count = 0
    for match in grep_lines(
        paths=[depth_log],
        patterns=[
            "FEED_REBALANCE_APPLIED",
            "FEED_REBALANCE_SKIPPED",
            "1006",
            "REACTORNOTRESTARTABLE",
            "FEED_ON_CONNECT_SUBSCRIBE",
            "FEED_RESUBSCRIBE",
            "FEED_OPTION_VERIFY_BEGIN",
            "FEED_OPTION_VERIFY_WAITING_TICKS",
            "FEED_OPTION_VERIFY_OK",
            "FEED_OPTION_VERIFY_FAILED",
            "FEED_RECOVERY_BLOCKED",
            "WS1006_PROCESS_RESTART_REQUIRED",
        ],
        tail_lines=tail_lines,
    ):
        record = extract_line_fields(str(match.get("excerpt") or ""))
        scope = classify_session_scope(
            record,
            current_run_id=current_run_id,
            current_boot_epoch=current_boot_epoch,
            path=Path(str(match.get("source_path") or "")) if match.get("source_path") else depth_log,
        )
        if current_session_feed_fresh and scope == "current_session" and not any(record.get(key) is not None for key in ("run_id", "boot_epoch", "ts_epoch")):
            scope = "historical_tail"
        excerpt = str(match.get("excerpt") or "")
        is_churn = "FEED_REBALANCE_APPLIED" in excerpt or "FEED_REBALANCE_SKIPPED" in excerpt
        is_ws1006 = "1006" in excerpt or "REACTORNOTRESTARTABLE" in excerpt
        if scope == "current_session":
            if "FEED_ON_CONNECT_SUBSCRIBE" in excerpt or "FEED_RESUBSCRIBE" in excerpt:
                current_option_subscribe_count += 1
            if "FEED_OPTION_VERIFY_BEGIN" in excerpt:
                current_option_verify_begin_count += 1
            if "FEED_OPTION_VERIFY_WAITING_TICKS" in excerpt:
                current_option_verify_waiting_count += 1
            if "FEED_OPTION_VERIFY_OK" in excerpt:
                current_option_verify_ok_count += 1
            if "FEED_OPTION_VERIFY_FAILED" in excerpt:
                current_option_verify_failed_count += 1
                failure_reason = str(record.get("reason") or record.get("failure_detail") or excerpt).upper()
                current_option_verify_failure_detail = failure_reason
                if "NO_LIVE_OPTION_FEED_AFTER_SUBSCRIBE" in failure_reason:
                    current_no_live_option_feed_after_subscribe_count += 1
            if "FEED_RECOVERY_BLOCKED" in excerpt:
                current_recovery_blocked_count += 1
        if is_churn:
            if scope == "current_session":
                current_feed_churn_count += 1
                if "FEED_REBALANCE_APPLIED" in excerpt:
                    current_feed_rebalance_applied_count += 1
                if "FEED_REBALANCE_SKIPPED" in excerpt:
                    current_feed_rebalance_skipped_count += 1
            elif scope == "historical_tail":
                stale_feed_churn_count += 1
                if "FEED_REBALANCE_APPLIED" in excerpt:
                    stale_feed_rebalance_applied_count += 1
                if "FEED_REBALANCE_SKIPPED" in excerpt:
                    stale_feed_rebalance_skipped_count += 1
        if is_ws1006:
            if scope == "current_session":
                current_ws1006_count += 1
            elif scope == "historical_tail":
                stale_ws1006_count += 1
        if "FEED_RECOVERY_BLOCKED" in excerpt and scope == "current_session":
            current_recovery_blocked_count += 1

    strategy_current = False
    strategy_stale = False
    strategy_path = artifacts["strategy_no_qualified_reasons"]
    if strategy_no_qualified:
        strategy_current = (
            strategy_no_qualified.get("strategy_no_qualified_applicable") is True
            and bool(strategy_no_qualified.get("no_candidate_constructed"))
            and strategy_path is not None
            and strategy_path.exists()
            and (current_boot_epoch is None or strategy_path.stat().st_mtime >= current_boot_epoch)
        )
        strategy_stale = bool(strategy_no_qualified.get("strategy_no_qualified_applicable")) and not strategy_current

    option_verify = feed_runtime.get("option_feed_verification") if isinstance(feed_runtime.get("option_feed_verification"), dict) else {}
    option_verify_state = str(option_verify.get("state") or "").strip().upper()
    option_verify_failure_detail = str(option_verify.get("failure_detail") or "").strip().upper() or current_option_verify_failure_detail
    if option_verify_state == "PENDING":
        current_option_verify_waiting_count = max(current_option_verify_waiting_count, 1)
    if option_verify_state == "OK":
        current_option_verify_ok_count = max(current_option_verify_ok_count, 1)
    if option_verify_state == "FAILED":
        current_option_verify_failed_count = max(current_option_verify_failed_count, 1)
        if "NO_LIVE_OPTION_FEED_AFTER_SUBSCRIBE" in option_verify_failure_detail:
            current_no_live_option_feed_after_subscribe_count = max(current_no_live_option_feed_after_subscribe_count, 1)
    if str(feed_runtime.get("runtime_state") or "").upper() == "RECOVERY_BLOCKED" or str(feed_runtime.get("feed_truth_state") or "").upper() == "RECOVERY_BLOCKED":
        current_recovery_blocked_count = max(current_recovery_blocked_count, 1)

    metrics = {
        "timeline_event_count": len(lines_timeline),
        "ws1006_count": sum(1 for item in lines_timeline if item.event and "1006" in item.event),
        "reactor_not_restartable_count": sum(1 for item in lines_timeline if item.event == "REACTORNOTRESTARTABLE"),
        "feed_rebalance_applied_count": sum(1 for item in lines_timeline if item.event == "FEED_REBALANCE_APPLIED"),
        "feed_rebalance_skipped_count": sum(1 for item in lines_timeline if item.event == "FEED_REBALANCE_SKIPPED"),
        "current_session_feed_rebalance_applied_count": current_feed_rebalance_applied_count,
        "current_session_feed_rebalance_skipped_count": current_feed_rebalance_skipped_count,
        "historical_feed_rebalance_applied_count": stale_feed_rebalance_applied_count,
        "historical_feed_rebalance_skipped_count": stale_feed_rebalance_skipped_count,
        "current_session_option_subscribe_count": current_option_subscribe_count,
        "current_session_option_verify_begin_count": current_option_verify_begin_count,
        "current_session_option_verify_waiting_count": current_option_verify_waiting_count,
        "current_session_option_verify_ok_count": current_option_verify_ok_count,
        "current_session_option_verify_failed_count": current_option_verify_failed_count,
        "current_session_no_live_option_feed_after_subscribe_count": current_no_live_option_feed_after_subscribe_count,
        "current_session_recovery_blocked_count": current_recovery_blocked_count,
        "raw_candidate_count": starvation_trace.get("raw_candidate_count"),
        "phase2_input_candidate_count": starvation_trace.get("phase2_input_candidate_count"),
        "ranked_executable_count": ranked_runtime.get("executable_count"),
        "current_session_feed_fresh": current_session_feed_fresh,
        "current_session_feed_churn_count": current_feed_churn_count,
        "current_session_ws1006_count": current_ws1006_count,
        "stale_feed_evidence_count": stale_feed_churn_count + stale_ws1006_count,
        "current_session_strategy_select_count": 1 if strategy_current else 0,
        "stale_strategy_select_count": 1 if strategy_stale else 0,
        "option_verify_state": option_verify_state or "IDLE",
        "option_verify_failure_detail": option_verify_failure_detail or None,
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
    elif current_no_live_option_feed_after_subscribe_count > 0 or (
        option_verify_state == "FAILED" and "NO_LIVE_OPTION_FEED_AFTER_SUBSCRIBE" in option_verify_failure_detail
    ):
        root_cause = "NO_LIVE_OPTION_FEED_AFTER_SUBSCRIBE"
        first_failing_event = "NO_LIVE_OPTION_FEED_AFTER_SUBSCRIBE"
    elif option_verify_state == "FAILED" and "OPTION_FEED_VERIFY_TIMEOUT" in option_verify_failure_detail:
        root_cause = "OPTION_FEED_VERIFY_TIMEOUT"
        first_failing_event = "OPTION_FEED_VERIFY_TIMEOUT"
    elif current_recovery_blocked_count > 0 or (
        current_ws1006_count > 0 and (
            str(feed_runtime.get("reconnect_blocked_reason") or "").strip().lower() == "ws1006_process_restart_required"
            or str(feed_runtime.get("process_restart_required")).lower() == "true"
            or option_verify_state == "FAILED"
        )
    ):
        root_cause = "WS1006_PROCESS_RESTART_REQUIRED"
        first_failing_event = "WS1006_PROCESS_RESTART_REQUIRED"
    elif current_feed_rebalance_applied_count > 0:
        root_cause = "SUBSCRIPTION_CHURN"
        first_failing_event = "FEED_REBALANCE_APPLIED"
    elif strategy_current:
        root_cause = "STRATEGY_SELECT_NO_QUALIFIED"
        first_failing_event = "N8_STRATEGY_SELECT:NO_STRATEGY_QUALIFIED"
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
    if root_cause == "STRATEGY_SELECT_NO_QUALIFIED":
        findings = (
            AgentFinding(
                code=root_cause,
                severity="BLOCKER",
                layer="live_rca",
                message="Current-session strategy selection produced no qualified candidate.",
                confidence="HIGH",
                first_seen_ts_epoch=None,
                evidence_refs=tuple(timeline_rows[:3]),
                recommended_action="Inspect N8_STRATEGY_SELECT and current-session setup qualification before blaming feed stability.",
                files_likely_involved=("core/decision_dag.py", "core/runtime_strategy_no_qualified_reasons.py"),
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
