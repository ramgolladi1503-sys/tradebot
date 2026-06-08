from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .contracts import AgentFinding, AgentReport, build_read_only_agent_report
from .readers import classify_session_scope, discover_runtime_artifacts, extract_line_fields, grep_lines, read_json_file


def _safe_bool(value: object) -> bool | None:
    if value is True:
        return True
    if value is False:
        return False
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"true", "1", "yes"}:
            return True
        if lower in {"false", "0", "no"}:
            return False
    return None


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


def _lower_text(value: object) -> str:
    return str(value or "").strip().lower()


def _contains_any(text: object, needles: tuple[str, ...]) -> bool:
    lower = _lower_text(text)
    return any(str(needle).strip().lower() in lower for needle in needles)


def _attempt_text(attempt: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "strategy_blocker_stage",
        "reason_category",
        "no_setup_reason",
        "strategy_blocker_reasons",
        "candidate_family_considered",
        "picked_candidate_family",
    ):
        value = attempt.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value not in (None, ""):
            parts.append(str(value))
    return " ".join(parts)


def _derive_zero_event_from_attempt(attempt: Mapping[str, Any]) -> dict[str, Any]:
    text = _attempt_text(attempt)
    subtypes: list[str] = []
    if _contains_any(text, ("no_strategy_qualified", "direction_or_regime_mismatch", "cross_asset_optional_stale")):
        subtypes.append("CANDIDATE_SUPPLY_ZERO_STRATEGY_QUALIFICATION")
    if _contains_any(text, ("regime_unstable_debounced", "regime_low_confidence", "entropy_too_high", "prob_too_low")):
        subtypes.append("CANDIDATE_SUPPLY_ZERO_REGIME_UNSTABLE")
    if _safe_bool(attempt.get("trade_builder_reached")) is True and _safe_bool(attempt.get("no_candidate_constructed")) is True:
        subtypes.append("CANDIDATE_SUPPLY_ZERO_TRADEBUILDER_REACHED_NO_CANDIDATE")
    return {
        "scope": "current_session",
        "symbol": attempt.get("symbol"),
        "stage": attempt.get("strategy_blocker_stage") or "N8_STRATEGY_SELECT",
        "reasons": [str(item) for item in attempt.get("strategy_blocker_reasons") or [] if item],
        "candidate_family_considered": attempt.get("candidate_family_considered"),
        "picked_candidate_family": attempt.get("picked_candidate_family"),
        "regime_confidence": attempt.get("regime_confidence"),
        "regime_entropy": attempt.get("regime_entropy"),
        "regime_unstable_debounced": attempt.get("regime_unstable_debounced"),
        "subtypes": subtypes,
        "primary_subtype": subtypes[0] if subtypes else None,
        "source": "strategy_no_qualified",
    }


def _event_priority(subtype: str | None) -> int:
    order = {
        "CANDIDATE_SUPPLY_ZERO_STRATEGY_QUALIFICATION": 0,
        "CANDIDATE_SUPPLY_ZERO_REGIME_UNSTABLE": 1,
        "CANDIDATE_SUPPLY_ZERO_LATENCY_GUARD_COOLDOWN": 2,
        "CANDIDATE_SUPPLY_ZERO_LATENCY_GUARD_DEGRADE_EXIT_ONLY": 3,
        "CANDIDATE_SUPPLY_ZERO_SLO_FEED_STALE": 4,
        "CANDIDATE_SUPPLY_ZERO_TRADEBUILDER_REACHED_NO_CANDIDATE": 5,
        "CANDIDATE_SUPPLY_ZERO_TRADEBUILDER_NOT_REACHED": 6,
    }
    return order.get(subtype or "", 99)


def analyze_candidate_supply(
    *,
    runtime_dir: Path,
    logs_dir: Path,
    session_dir: Path | None = None,
    tail_lines: int = 5000,
) -> AgentReport:
    artifacts = discover_runtime_artifacts(runtime_root=runtime_dir, logs_root=logs_dir, session_root=session_dir)
    trace = read_json_file(artifacts["candidate_starvation_trace"])
    feed_runtime = read_json_file(artifacts["feed_runtime_runtime_logs"] or artifacts["feed_runtime_logs"] or artifacts["feed_runtime_runtime"])
    strategy_no_qualified = read_json_file(artifacts["strategy_no_qualified_reasons"])
    depth_log = artifacts["depth_ws_watchdog"]
    current_run_id = str(feed_runtime.get("run_id") or "").strip() or None
    current_boot_epoch = None
    try:
        current_boot_epoch = float(feed_runtime.get("boot_epoch")) if feed_runtime.get("boot_epoch") is not None else None
    except Exception:
        current_boot_epoch = None

    current_session_feed_fresh = (
        _safe_bool(feed_runtime.get("ws_connected")) is True
        and str(feed_runtime.get("runtime_state") or "").upper() not in {"DEAD", "RECOVERY_BLOCKED"}
        and (
            _nested_gate_ok(feed_runtime.get("feed_health_snapshot"), "N2_FEED_FRESH")
            or _nested_gate_ok(feed_runtime.get("gate_status"), "N2_FEED_FRESH")
        )
    )

    feed_events: list[dict[str, Any]] = []
    for match in grep_lines(
        paths=[depth_log],
        patterns=["FEED_REBALANCE_APPLIED", "FEED_REBALANCE_SKIPPED", "1006", "FEED_LTP_STALE", "feed_stale:LTP_STALE"],
        tail_lines=tail_lines,
    ):
        excerpt = str(match.get("excerpt") or "")
        record = extract_line_fields(excerpt)
        scope = classify_session_scope(
            record,
            current_run_id=current_run_id,
            current_boot_epoch=current_boot_epoch,
            path=Path(str(match.get("source_path") or "")) if match.get("source_path") else depth_log,
        )
        if current_session_feed_fresh and scope == "current_session" and not any(record.get(key) is not None for key in ("run_id", "boot_epoch", "ts_epoch")):
            scope = "historical_tail"
        subtype = None
        if "FEED_REBALANCE_APPLIED" in excerpt or "FEED_REBALANCE_SKIPPED" in excerpt:
            subtype = "CANDIDATE_SUPPLY_ZERO_SLO_FEED_STALE" if _contains_any(excerpt, ("FEED_LTP_STALE", "feed_stale:LTP_STALE")) else None
        if "1006" in excerpt:
            subtype = subtype or "CANDIDATE_SUPPLY_ZERO_SLO_FEED_STALE"
        if _contains_any(excerpt, ("FEED_LTP_STALE", "feed_stale:LTP_STALE")):
            subtype = "CANDIDATE_SUPPLY_ZERO_SLO_FEED_STALE"
        if subtype:
            feed_events.append(
                {
                    "scope": scope,
                    "source": "depth_ws_watchdog",
                    "subtype": subtype,
                    "primary_subtype": subtype,
                    "subtypes": [subtype],
                    "line_number": match.get("line_number"),
                    "excerpt": excerpt,
                }
            )

    strategy_events: list[dict[str, Any]] = []
    if isinstance(strategy_no_qualified, dict):
        by_symbol = strategy_no_qualified.get("by_symbol") or {}
        if isinstance(by_symbol, dict):
            for symbol, symbol_payload in by_symbol.items():
                if not isinstance(symbol_payload, dict):
                    continue
                attempts = symbol_payload.get("attempts") or []
                if not isinstance(attempts, list):
                    continue
                for attempt in attempts:
                    if not isinstance(attempt, dict):
                        continue
                    event = _derive_zero_event_from_attempt(attempt)
                    event["symbol"] = symbol or event.get("symbol")
                    if event["subtypes"]:
                        strategy_events.append(event)
        latency = strategy_no_qualified.get("latency_guard")
        if isinstance(latency, dict) and _safe_bool(latency.get("latency_guard_triggered")) is True:
            action = _lower_text(latency.get("latency_guard_action"))
            subtypes = []
            if action == "cooldown":
                subtypes.append("CANDIDATE_SUPPLY_ZERO_LATENCY_GUARD_COOLDOWN")
            elif action == "degrade_exit_only":
                subtypes.append("CANDIDATE_SUPPLY_ZERO_LATENCY_GUARD_DEGRADE_EXIT_ONLY")
            if subtypes:
                strategy_events.append(
                    {
                        "scope": "current_session",
                        "symbol": None,
                        "stage": "LATENCY_GUARD",
                        "reasons": [
                            str(latency.get("latency_guard_reason") or "latency_guard_prebuild_skip"),
                            str(latency.get("latency_guard_action") or ""),
                        ],
                        "candidate_family_considered": None,
                        "picked_candidate_family": None,
                        "regime_confidence": None,
                        "regime_entropy": None,
                        "regime_unstable_debounced": None,
                        "subtypes": subtypes,
                        "primary_subtype": subtypes[0],
                        "source": "latency_guard",
                    }
                )

        gate_reasons = strategy_no_qualified.get("gate_reasons")
        if isinstance(gate_reasons, dict):
            if any(str(key).upper() == "FEED_LTP_STALE" and _safe_bool(value) is not False for key, value in gate_reasons.items()):
                feed_events.append(
                    {
                        "scope": "current_session" if current_session_feed_fresh else "historical_tail",
                        "source": "strategy_no_qualified",
                        "subtype": "CANDIDATE_SUPPLY_ZERO_SLO_FEED_STALE",
                        "primary_subtype": "CANDIDATE_SUPPLY_ZERO_SLO_FEED_STALE",
                        "subtypes": ["CANDIDATE_SUPPLY_ZERO_SLO_FEED_STALE"],
                        "line_number": None,
                        "excerpt": "FEED_LTP_STALE",
                    }
                )

    zero_timeline = sorted(
        [*strategy_events, *feed_events],
        key=lambda item: (
            0 if item.get("scope") == "current_session" else 1,
            _event_priority(str(item.get("primary_subtype") or item.get("subtype"))),
            str(item.get("symbol") or ""),
            str(item.get("stage") or ""),
        ),
    )
    zero_subtypes: list[str] = []
    for item in zero_timeline:
        for subtype in item.get("subtypes") or []:
            if subtype not in zero_subtypes:
                zero_subtypes.append(subtype)

    first_event = zero_timeline[0] if zero_timeline else {}
    first_subtype = str(first_event.get("primary_subtype") or "") or None
    candidate_supply_evidence_scope = "unknown"
    if zero_timeline:
        scopes = {str(item.get("scope") or "unknown") for item in zero_timeline}
        if "current_session" in scopes and "historical_tail" in scopes:
            candidate_supply_evidence_scope = "mixed"
        elif "current_session" in scopes:
            candidate_supply_evidence_scope = "current_session"
        elif "historical_tail" in scopes:
            candidate_supply_evidence_scope = "historical_tail"
    feed_churn_evidence_scope = "unknown"
    if feed_events:
        scopes = {str(item.get("scope") or "unknown") for item in feed_events}
        if "current_session" in scopes and "historical_tail" in scopes:
            feed_churn_evidence_scope = "mixed"
        elif "current_session" in scopes:
            feed_churn_evidence_scope = "current_session"
        elif "historical_tail" in scopes:
            feed_churn_evidence_scope = "historical_tail"

    feed_was_fresh_before_candidate_supply_zero = bool(current_session_feed_fresh)
    first_strategy_attempt = None
    if isinstance(strategy_no_qualified, dict):
        by_symbol = strategy_no_qualified.get("by_symbol") or {}
        if isinstance(by_symbol, dict):
            for symbol_payload in by_symbol.values():
                attempts = symbol_payload.get("attempts") if isinstance(symbol_payload, dict) else None
                if isinstance(attempts, list) and attempts:
                    first_strategy_attempt = attempts[0]
                    break
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
        "candidate_supply_evidence_scope": candidate_supply_evidence_scope,
        "feed_churn_evidence_scope": feed_churn_evidence_scope,
        "first_candidate_supply_zero_subtype": first_subtype,
        "candidate_supply_zero_subtypes": zero_subtypes,
        "candidate_supply_zero_timeline": zero_timeline,
        "first_strategy_blocker_symbol": (first_strategy_attempt or {}).get("symbol"),
        "first_strategy_blocker_stage": (first_strategy_attempt or {}).get("strategy_blocker_stage") or "N8_STRATEGY_SELECT",
        "first_strategy_blocker_reasons": (first_strategy_attempt or {}).get("strategy_blocker_reasons")
        or (first_strategy_attempt or {}).get("no_setup_reason")
        or [],
        "trade_builder_reached": _safe_bool((first_strategy_attempt or {}).get("trade_builder_reached"))
        if first_strategy_attempt is not None
        else _safe_bool(strategy_no_qualified.get("trade_builder_reached") if isinstance(strategy_no_qualified, dict) else None),
        "no_candidate_constructed": _safe_bool((first_strategy_attempt or {}).get("no_candidate_constructed"))
        if first_strategy_attempt is not None
        else _safe_bool(strategy_no_qualified.get("no_candidate_constructed") if isinstance(strategy_no_qualified, dict) else None),
        "candidate_family_considered": (first_strategy_attempt or {}).get("candidate_family_considered"),
        "picked_candidate_family": (first_strategy_attempt or {}).get("picked_candidate_family"),
        "regime_confidence": (first_strategy_attempt or {}).get("regime_confidence"),
        "regime_entropy": (first_strategy_attempt or {}).get("regime_entropy"),
        "regime_unstable_debounced": (first_strategy_attempt or {}).get("regime_unstable_debounced"),
        "latency_guard_cooldown_count": sum(1 for item in zero_timeline if "LATENCY_GUARD_COOLDOWN" in str(item.get("primary_subtype") or "")),
        "latency_guard_degrade_exit_only_count": sum(
            1 for item in zero_timeline if "LATENCY_GUARD_DEGRADE_EXIT_ONLY" in str(item.get("primary_subtype") or "")
        ),
        "slo_feed_stale_count": sum(1 for item in zero_timeline if "SLO_FEED_STALE" in str(item.get("primary_subtype") or "")),
        "feed_was_fresh_before_candidate_supply_zero": feed_was_fresh_before_candidate_supply_zero,
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
