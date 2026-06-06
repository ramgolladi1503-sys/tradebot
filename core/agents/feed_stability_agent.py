from __future__ import annotations

from pathlib import Path

from .contracts import AgentFinding, AgentReport, build_read_only_agent_report
from .evidence_refs import evidence_ref_from_mapping, evidence_ref_from_text
from .readers import discover_runtime_artifacts, grep_lines, read_json_file


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
    text = (depth_log.read_text(encoding="utf-8", errors="replace") if depth_log and depth_log.exists() else "")
    subscribe_counts = []
    unsubscribe_counts = []
    import re
    for line in text.splitlines():
        if "FEED_REBALANCE_APPLIED" in line or "FEED_REBALANCE_SKIPPED" in line:
            m1 = re.search(r"subscribe_count=(\d+)", line)
            m2 = re.search(r"unsubscribe_count=(\d+)", line)
            if m1:
                subscribe_counts.append(int(m1.group(1)))
            if m2:
                unsubscribe_counts.append(int(m2.group(1)))
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
        "stale_count_max": max(0, len([item for item in lines if "STALE" in (item.get("excerpt") or "").upper()])),
        "option_ticks_received_by_symbol": feed_runtime.get("option_ticks_received_count_by_symbol") or {},
        "option_feed_block_reasons": feed_runtime.get("option_feed_block_reason_by_symbol") or {},
    }

    findings = []
    if metrics["ws1006_count"] and metrics["rebalance_applied_count"]:
        findings.append(
            AgentFinding(
                code="SUBSCRIPTION_CHURN_WS1006_CORRELATION",
                severity="WARN",
                layer="feed_stability",
                message="Rebalance activity is correlated with a WS1006 disconnect.",
                confidence="HIGH",
                recommended_action="Inspect stale-option refresh and mutation guard ordering.",
                files_likely_involved=("core/kite_depth_ws.py",),
                tests_needed=("tests/test_feed_stability_agent.py",),
            )
        )
    if fresh_ratio_min is not None and fresh_ratio_min > 0.90 and metrics["rebalance_applied_count"]:
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
    if str(feed_runtime.get("ws_connected")).lower() == "false" and any("SUBSCRIBE" in (item.get("excerpt") or "").upper() for item in lines):
        findings.append(
            AgentFinding(
                code="MUTATION_ON_DEAD_WS",
                severity="BLOCKER",
                layer="feed_stability",
                message="Subscription mutation appeared while websocket was disconnected.",
                confidence="HIGH",
                recommended_action="Fail closed when WS is disconnected.",
                files_likely_involved=("core/kite_depth_ws.py",),
                tests_needed=("tests/test_feed_stability_agent.py",),
            )
        )

    verdict = "BLOCKER" if any(item.severity == "BLOCKER" for item in findings) else ("WARN" if findings else "PASS")
    confidence = "HIGH" if findings else "LOW"
    return build_read_only_agent_report(
        agent_name="feed_stability",
        verdict=verdict,
        confidence=confidence,
        first_failing_event="FEED_REBALANCE_APPLIED" if findings else None,
        findings=tuple(findings),
        not_root_cause=("Subscription churn is not the only possible cause of feed failure.",),
        next_fix_recommendation="Tighten stale-option mutation guard ordering and keep dead-WS mutation blocked.",
        metrics=metrics,
    )
