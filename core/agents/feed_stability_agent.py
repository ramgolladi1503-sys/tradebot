from __future__ import annotations

import json
import re
from pathlib import Path

from .contracts import AgentFinding, AgentReport, build_read_only_agent_report
from .evidence_refs import evidence_ref_from_mapping, evidence_ref_from_text
from .readers import classify_session_scope, discover_runtime_artifacts, extract_line_fields, grep_lines, read_json_file


def analyze_feed_stability(
    *,
    runtime_dir: Path,
    logs_dir: Path,
    session_dir: Path | None = None,
    tail_lines: int = 5000,
) -> AgentReport:
    artifacts = discover_runtime_artifacts(runtime_root=runtime_dir, logs_root=logs_dir, session_root=session_dir)
    feed_runtime = read_json_file(artifacts["feed_runtime_runtime_logs"] or artifacts["feed_runtime_logs"] or artifacts["feed_runtime_runtime"])
    depth_log = artifacts["depth_ws_watchdog"]
    lines = grep_lines(paths=[depth_log], patterns=["FEED_CONNECT", "1006", "REACTORNOTRESTARTABLE", "FEED_REBALANCE_APPLIED", "FEED_REBALANCE_SKIPPED", "FEED_OPTION_PRUNE_REFRESH"], tail_lines=tail_lines)
    text = depth_log.read_text(encoding="utf-8", errors="replace") if depth_log and depth_log.exists() else ""
    subscribe_counts = []
    unsubscribe_counts = []
    fresh_ratio_values: list[float] = []
    stale_count_values: list[int] = []
    current_run_id = str(feed_runtime.get("run_id") or "").strip() or None
    current_boot_epoch = None
    try:
        current_boot_epoch = float(feed_runtime.get("boot_epoch")) if feed_runtime.get("boot_epoch") is not None else None
    except Exception:
        current_boot_epoch = None
    current_feed_fresh = False
    runtime_state = str(feed_runtime.get("runtime_state") or "").upper()
    feed_truth_state = str(feed_runtime.get("feed_truth_state") or "").upper()
    if str(feed_runtime.get("ws_connected")).lower() == "true":
        feed_health_snapshot = feed_runtime.get("feed_health_snapshot") if isinstance(feed_runtime.get("feed_health_snapshot"), dict) else {}
        gate_status = feed_runtime.get("gate_status") if isinstance(feed_runtime.get("gate_status"), dict) else {}

        def _gate_ok(container: dict[str, object], key: str) -> bool:
            payload = container.get(key)
            if isinstance(payload, dict):
                if "ok" in payload:
                    return bool(payload.get("ok"))
                if "status" in payload:
                    return str(payload.get("status") or "").strip().lower() == "ok"
            if isinstance(payload, bool):
                return payload
            return False

        current_feed_fresh = (
            runtime_state not in {"DEAD", "RECOVERY_BLOCKED"}
            and feed_truth_state not in {"DEAD", "RECOVERY_BLOCKED"}
            and (_gate_ok(feed_health_snapshot, "N2_FEED_FRESH") or _gate_ok(gate_status, "N2_FEED_FRESH"))
        )

    current_churn_count = 0
    stale_churn_count = 0
    current_rebalance_applied_count = 0
    current_rebalance_skipped_count = 0
    stale_rebalance_applied_count = 0
    stale_rebalance_skipped_count = 0
    current_ws1006_count = 0
    stale_ws1006_count = 0
    current_ltp_stale_count = 0
    stale_ltp_stale_count = 0
    current_depth_stale_count = 0
    stale_depth_stale_count = 0
    current_mutation_on_dead_ws_count = 0
    current_overreactive_stale_option_mutation_count = 0
    parsed_lines: list[tuple[str, dict[str, object]]] = []
    for line in text.splitlines():
        fields = extract_line_fields(line)
        parsed_lines.append((line, fields))
        event = str(fields.get("event") or "").upper()
        is_churn = event in {"FEED_REBALANCE_APPLIED", "FEED_REBALANCE_SKIPPED"} or "FEED_REBALANCE_APPLIED" in line or "FEED_REBALANCE_SKIPPED" in line
        is_ws1006 = "1006" in event or "1006" in line or event == "REACTORNOTRESTARTABLE"
        if is_churn:
            if "subscribe_count" in fields:
                subscribe_counts.append(int(fields["subscribe_count"]))
            elif match := re.search(r"subscribe_count=(\d+)", line):
                subscribe_counts.append(int(match.group(1)))
            if "unsubscribe_count" in fields:
                unsubscribe_counts.append(int(fields["unsubscribe_count"]))
            elif match := re.search(r"unsubscribe_count=(\d+)", line):
                unsubscribe_counts.append(int(match.group(1)))
        if "fresh_ratio" in fields:
            try:
                fresh_ratio_values.append(float(fields["fresh_ratio"]))
            except Exception:
                pass
        if "stale_count" in fields:
            try:
                stale_count_values.append(int(fields["stale_count"]))
            except Exception:
                pass
    fresh_ratio_min = None
    option_ticks = feed_runtime.get("option_ticks_received_count_by_symbol")
    subscribed = feed_runtime.get("option_tokens_subscribed_count_by_symbol")
    if isinstance(option_ticks, dict) and isinstance(subscribed, dict):
        ratios = []
        for symbol, sub_count in subscribed.items():
            try:
                sub = float(sub_count)
                ticks = float(option_ticks.get(symbol, 0))
            except Exception:
                continue
            if sub > 0:
                ratios.append(ticks / sub)
        if ratios:
            fresh_ratio_min = min(ratios)
    if fresh_ratio_values:
        fresh_ratio_min = min(fresh_ratio_values) if fresh_ratio_min is None else min(fresh_ratio_min, min(fresh_ratio_values))
    if not current_feed_fresh and fresh_ratio_min is not None and fresh_ratio_min > 0.90:
        current_feed_fresh = str(feed_runtime.get("ws_connected")).lower() == "true" and runtime_state not in {"DEAD", "RECOVERY_BLOCKED"}

    for line, fields in parsed_lines:
        event = str(fields.get("event") or "").upper()
        scope = classify_session_scope(
            fields,
            current_run_id=current_run_id,
            current_boot_epoch=current_boot_epoch,
            path=depth_log,
        )
        if current_feed_fresh and scope == "current_session" and not any(fields.get(key) is not None for key in ("run_id", "boot_epoch", "ts_epoch")):
            scope = "historical_tail"
        is_churn = event in {"FEED_REBALANCE_APPLIED", "FEED_REBALANCE_SKIPPED"} or "FEED_REBALANCE_APPLIED" in line or "FEED_REBALANCE_SKIPPED" in line
        is_ws1006 = "1006" in event or "1006" in line or event == "REACTORNOTRESTARTABLE"
        if is_churn:
            if scope == "current_session":
                current_churn_count += 1
                if event == "FEED_REBALANCE_APPLIED" or "FEED_REBALANCE_APPLIED" in line:
                    current_rebalance_applied_count += 1
                    if (not bool(feed_runtime.get("ws_connected"))) or runtime_state in {"RECOVERY_BLOCKED", "DEGRADED"} or feed_truth_state in {"DEAD", "RECOVERY_BLOCKED"}:
                        current_mutation_on_dead_ws_count += 1
                if event == "FEED_REBALANCE_SKIPPED" or "FEED_REBALANCE_SKIPPED" in line:
                    current_rebalance_skipped_count += 1
            elif scope == "historical_tail":
                stale_churn_count += 1
                if event == "FEED_REBALANCE_APPLIED" or "FEED_REBALANCE_APPLIED" in line:
                    stale_rebalance_applied_count += 1
                if event == "FEED_REBALANCE_SKIPPED" or "FEED_REBALANCE_SKIPPED" in line:
                    stale_rebalance_skipped_count += 1
        if is_ws1006:
            if scope == "current_session":
                current_ws1006_count += 1
            elif scope == "historical_tail":
                stale_ws1006_count += 1
        if "FEED_LTP_STALE" in event or "FEED_LTP_STALE" in line:
            if scope == "current_session":
                current_ltp_stale_count += 1
            elif scope == "historical_tail":
                stale_ltp_stale_count += 1
        if "FEED_DEPTH_STALE" in event or "FEED_DEPTH_STALE" in line:
            if scope == "current_session":
                current_depth_stale_count += 1
            elif scope == "historical_tail":
                stale_depth_stale_count += 1
        if current_feed_fresh and scope == "current_session" and is_churn and fresh_ratio_min is not None and fresh_ratio_min > 0.90:
            current_overreactive_stale_option_mutation_count += 1

    metrics = {
        "feed_connect_count": sum("FEED_CONNECT" in (item.get("excerpt") or "") for item in lines),
        "ws1006_count": sum("1006" in (item.get("excerpt") or "") for item in lines),
        "reactor_not_restartable_count": sum("REACTORNOTRESTARTABLE" in (item.get("excerpt") or "") for item in lines),
        "recovery_blocked_count": 1 if str(feed_runtime.get("runtime_state") or "").upper() == "RECOVERY_BLOCKED" else 0,
        "feed_close_count": sum("CONNECTION CLOSED" in (item.get("excerpt") or "").upper() for item in lines),
        "restart_attempt_count": sum("STARTING FACTORY" in (item.get("excerpt") or "").upper() for item in lines),
        "restart_blocked_count": sum("RESTART BLOCKED" in (item.get("excerpt") or "").upper() for item in lines),
        "option_prune_refresh_count": sum("FEED_OPTION_PRUNE_REFRESH" in (item.get("excerpt") or "") for item in lines),
        "rebalance_applied_count": sum("FEED_REBALANCE_APPLIED" in (item.get("excerpt") or "") for item in lines),
        "large_rebalance_count": sum(1 for count in subscribe_counts + unsubscribe_counts if count >= 10),
        "subscription_mutation_count": len(subscribe_counts) + len(unsubscribe_counts),
        "max_subscribe_count": max(subscribe_counts) if subscribe_counts else 0,
        "max_unsubscribe_count": max(unsubscribe_counts) if unsubscribe_counts else 0,
        "fresh_ratio_min": fresh_ratio_min,
        "stale_count_max": max(stale_count_values + [0]),
        "option_ticks_received_by_symbol": feed_runtime.get("option_ticks_received_count_by_symbol") or {},
        "option_feed_block_reasons": feed_runtime.get("option_feed_block_reason_by_symbol") or {},
        "current_session_feed_fresh": current_feed_fresh,
        "evidence_scope": "mixed" if (current_churn_count or current_ws1006_count) and (stale_churn_count or stale_ws1006_count) else ("current_session" if (current_churn_count or current_ws1006_count) else ("historical_tail" if (stale_churn_count or stale_ws1006_count) else "unknown")),
        "stale_evidence_ignored_count": stale_churn_count + stale_ws1006_count,
        "stale_evidence_reason": "historical_tail feed churn ignored for current-session RCA" if (stale_churn_count or stale_ws1006_count) else None,
        "current_session_churn_count": current_churn_count,
        "current_session_ws1006_count": current_ws1006_count,
        "historical_feed_churn_count": stale_churn_count,
        "historical_feed_ws1006_count": stale_ws1006_count,
        "current_session_rebalance_applied_count": current_rebalance_applied_count,
        "current_session_rebalance_skipped_count": current_rebalance_skipped_count,
        "current_session_mutation_on_dead_ws_count": current_mutation_on_dead_ws_count,
        "current_session_overreactive_stale_option_mutation_count": current_overreactive_stale_option_mutation_count,
        "current_session_slo_feed_stale_count": current_ltp_stale_count + current_depth_stale_count,
        "current_session_feed_ltp_stale_count": current_ltp_stale_count,
        "current_session_feed_depth_stale_count": current_depth_stale_count,
    }

    findings = []
    if current_churn_count and current_ws1006_count:
        findings.append(
            AgentFinding(
                code="SUBSCRIPTION_CHURN_WS1006_CORRELATION",
                severity="BLOCKER",
                layer="feed_stability",
                message="Rebalance activity is correlated with a WS1006 disconnect.",
                confidence="HIGH",
                recommended_action="Inspect stale-option refresh and mutation guard ordering.",
                files_likely_involved=("core/kite_depth_ws.py",),
                tests_needed=("tests/test_feed_stability_agent.py",),
            )
        )
    elif current_mutation_on_dead_ws_count:
        findings.append(
            AgentFinding(
                code="MUTATION_ON_DEAD_WS",
                severity="BLOCKER",
                layer="feed_stability",
                message="Subscription mutation appeared while websocket or feed truth was unavailable.",
                confidence="HIGH",
                recommended_action="Fail closed when WS is disconnected or feed truth is degraded.",
                files_likely_involved=("core/kite_depth_ws.py",),
                tests_needed=("tests/test_feed_stability_agent.py",),
            )
        )
    elif current_churn_count:
        findings.append(
            AgentFinding(
                code="SUBSCRIPTION_CHURN",
                severity="BLOCKER",
                layer="feed_stability",
                message="Current-session feed churn detected.",
                confidence="HIGH",
                recommended_action="Inspect current-session subscription mutation ordering.",
                files_likely_involved=("core/kite_depth_ws.py",),
                tests_needed=("tests/test_feed_stability_agent.py",),
            )
        )
    elif current_ws1006_count:
        findings.append(
            AgentFinding(
                code="WS1006_TERMINAL_CLOSE",
                severity="BLOCKER",
                layer="feed_stability",
                message="Current-session websocket 1006 close detected.",
                confidence="HIGH",
                recommended_action="Inspect current-session websocket lifecycle.",
                files_likely_involved=("core/kite_depth_ws.py",),
                tests_needed=("tests/test_feed_stability_agent.py",),
            )
        )
    elif stale_churn_count or stale_ws1006_count:
        findings.append(
            AgentFinding(
                code="STALE_FEED_CHURN",
                severity="WARN",
                layer="feed_stability",
                message="Historical feed churn evidence exists, but it is not current-session evidence.",
                confidence="HIGH",
                recommended_action="Keep the historical tail visible, but do not let it override current-session RCA.",
                files_likely_involved=("core/agents/readers.py",),
                tests_needed=("tests/test_feed_stability_agent.py",),
            )
        )
    if fresh_ratio_min is not None and fresh_ratio_min > 0.90 and current_churn_count:
        findings.append(
            AgentFinding(
                code="OVERREACTIVE_STALE_OPTION_MUTATION",
                severity="WARN",
                layer="feed_stability",
                message="Rebalance mutated subscriptions even though feed freshness was mostly healthy.",
                confidence="HIGH",
                recommended_action="Reduce mutation churn when the fresh ratio is already high.",
                files_likely_involved=("core/kite_depth_ws.py",),
                tests_needed=("tests/test_feed_stability_agent.py",),
            )
        )
    if metrics["max_subscribe_count"] >= 10 or metrics["max_unsubscribe_count"] >= 10:
        findings.append(
            AgentFinding(
                code="LARGE_SUBSCRIPTION_MUTATION",
                severity="WARN",
                layer="feed_stability",
                message="Large subscription churn detected in a single cycle.",
                confidence="HIGH",
                recommended_action="Gate large rebalance bursts behind explicit evidence.",
                files_likely_involved=("core/kite_depth_ws.py",),
                tests_needed=("tests/test_feed_stability_agent.py",),
            )
        )
    verdict = "BLOCKER" if any(item.severity == "BLOCKER" for item in findings) else ("WARN" if findings else "PASS")
    confidence = "HIGH" if findings else "LOW"
    if verdict != "BLOCKER" and (
        current_churn_count
        or current_ws1006_count
        or metrics["recovery_blocked_count"]
        or (fresh_ratio_min is not None and fresh_ratio_min > 0.90 and current_feed_fresh)
    ):
        verdict = "WARN"
    return build_read_only_agent_report(
        agent_name="feed_stability",
        verdict=verdict,
        confidence=confidence,
        first_failing_event=("FEED_REBALANCE_APPLIED" if current_churn_count else ("CONNECTION_ERROR:1006" if current_ws1006_count else ("FEED_REBALANCE_APPLIED" if findings else None))),
        findings=tuple(findings),
        not_root_cause=("Subscription churn is not the only possible cause of feed failure.", "Historical feed churn should not override healthy current-session feed evidence."),
        next_fix_recommendation=(
            "Tighten stale-option mutation guard ordering and keep dead-WS mutation blocked."
            if current_churn_count or current_ws1006_count
            else "Retain historical feed churn in diagnostics only; do not let it dominate current-session RCA."
        ),
        metrics=metrics,
    )
