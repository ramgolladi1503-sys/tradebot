from __future__ import annotations

import ast
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from core.feed_truth_contract import build_feed_truth_contract


AUDIT_SCHEMA_VERSION = 1
_CANDIDATE_EVENTS = {
    "TB_TOP_REAL_CANDIDATE",
    "TB_TOP_EXECUTABLE_CANDIDATE",
    "TB_TOP_BLOCKED_CANDIDATE",
    "TB_TOP_ADVISORY_CANDIDATE",
    "TB_TOP_SYNTH_CANDIDATE",
}
_FEED_DIAGNOSTIC_EVENTS = {"REGIME_UNSTABLE_DIAGNOSTIC"}
_LATENCY_GUARD_EVENTS = {"latency_guard_background_maintenance_skip"}
_OK_MARKERS = {"", "OK", "LIVE", "FRESH", "HEALTHY", "NONE"}
_BLOCKED_STATES = {"DISCONNECTED", "RECOVERY_BLOCKED", "STALE", "AUTH_BLOCKED", "IMPORT_MISSING", "UNKNOWN"}
_SEVERITY_ERROR = "error"
_SEVERITY_WARNING = "warning"


@dataclass(frozen=True)
class AuditIssue:
    severity: str
    code: str
    message: str
    line_number: int | None = None
    event: str | None = None
    symbol: str | None = None
    trade_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "line_number": self.line_number,
            "event": self.event,
            "symbol": self.symbol,
            "trade_id": self.trade_id,
            "detail": dict(self.detail),
        }
        return {key: value for key, value in payload.items() if value not in (None, {}, [])}


def _read_text(path: Path | None) -> str:
    if path is None or not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_lines(path: Path | None) -> list[str]:
    text = _read_text(path)
    return text.splitlines() if text else []


def _parse_payload(line: str) -> dict[str, Any] | None:
    if "{" not in line or "}" not in line:
        return None
    raw = line[line.find("{") : line.rfind("}") + 1]
    try:
        parsed = ast.literal_eval(raw)
    except Exception:
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
    return parsed if isinstance(parsed, dict) else None


def _line_event_name(line: str, payload: dict[str, Any] | None) -> str:
    if isinstance(payload, dict):
        event = str(payload.get("event") or payload.get("event_type") or "").strip()
        if event:
            return event
    for marker in sorted(_CANDIDATE_EVENTS | _FEED_DIAGNOSTIC_EVENTS | _LATENCY_GUARD_EVENTS, key=len, reverse=True):
        if marker in line:
            return marker
    match = re.match(r".*?([A-Z][A-Z0-9_]+)\s*$", line.strip())
    return match.group(1) if match else ""


def _normalize_reason(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text


def _is_ok_marker(value: Any) -> bool:
    text = _normalize_reason(value)
    return not text or text in _OK_MARKERS or text.endswith("_OK")


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip().upper()
        if not text or text in _OK_MARKERS or text.endswith("_OK"):
            continue
        if text not in out:
            out.append(text)
    return out


def _candidate_feed_context(payload: dict[str, Any], runtime_payload: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = dict(runtime_payload or {})
    context.setdefault("quote_health", runtime_payload.get("quote_health") if isinstance(runtime_payload.get("quote_health"), dict) else {})
    context.setdefault("latency_guard", runtime_payload.get("latency_guard") if isinstance(runtime_payload.get("latency_guard"), dict) else {})

    def _set(key: str, value: Any) -> None:
        if value not in (None, "", "None"):
            context[key] = value

    _set("runtime_state", payload.get("feed_runtime_state") or payload.get("runtime_state"))
    _set("ws_connected", payload.get("ws_connected"))
    _set("effective_ws_connected", payload.get("effective_ws_connected"))
    _set("feed_truth_state", payload.get("feed_truth_state") or payload.get("feed_health_state"))
    _set("feed_truth_reason_code", payload.get("feed_truth_reason_code"))
    _set("feed_ok", payload.get("feed_ok"))
    _set("feed_truth_strict_live", payload.get("feed_truth_strict_live"))
    _set("option_feed_block_reason", payload.get("option_feed_block_reason"))
    if isinstance(payload.get("option_feed_block_reason_by_symbol"), dict):
        context["option_feed_block_reason_by_symbol"] = payload.get("option_feed_block_reason_by_symbol")
    _set("reconnect_blocked_reason", payload.get("reconnect_blocked_reason"))
    _set("recovery_action", payload.get("recovery_action"))

    quote_state = payload.get("quote_health_state")
    quote_stale_reasons = payload.get("quote_health_stale_reasons")
    if quote_state not in (None, "", "None") or quote_stale_reasons not in (None, "", "None", []):
        context["quote_health"] = {
            "state": quote_state,
            "stale_reasons": list(quote_stale_reasons or []),
        }

    latency_keys = {
        "latency_guard_triggered",
        "latency_guard_mode",
        "latency_guard_action",
        "latency_guard_source",
        "latency_guard_reason",
        "latency_guard_metric",
        "latency_guard_value",
        "latency_guard_threshold",
        "latency_guard_age_sec",
        "latency_guard_last_ok_at",
        "latency_guard_last_bad_at",
        "latency_guard_recovery_required",
    }
    latency = dict(context.get("latency_guard") or {})
    for key in latency_keys:
        value = payload.get(key)
        if value not in (None, "", "None"):
            latency[key] = value
    if latency:
        context["latency_guard"] = latency

    return context


def _collect_runtime_truth(payload: dict[str, Any]) -> dict[str, Any]:
    runtime: dict[str, Any] = dict(payload or {})
    if isinstance(runtime.get("quote_health"), dict):
        runtime["quote_health"] = dict(runtime["quote_health"])
    if isinstance(runtime.get("latency_guard"), dict):
        runtime["latency_guard"] = dict(runtime["latency_guard"])
    return runtime


def _blocker_histogram(*, runtime_payload: dict[str, Any], candidate_payloads: list[dict[str, Any]]) -> Counter[str]:
    hist: Counter[str] = Counter()
    runtime_contract = build_feed_truth_contract(runtime_payload)
    for blocker in runtime_contract.blockers:
        hist[_normalize_reason(blocker)] += 1
    for payload in candidate_payloads:
        for blocker in list(payload.get("execution_truth_blockers") or payload.get("blockers") or []):
            text = _normalize_reason(blocker)
            if text and text not in _OK_MARKERS and not text.endswith("_OK"):
                hist[text] += 1
    return hist


def _candidate_status(payload: dict[str, Any]) -> str:
    status = str(
        payload.get("candidate_status")
        or payload.get("execution_status")
        or payload.get("readiness")
        or payload.get("permission")
        or payload.get("visibility_bucket")
        or ""
    ).strip().lower()
    return status or "unknown"


def _candidate_fallback_source(payload: dict[str, Any]) -> str:
    for key in (
        "quote_source",
        "entry_quote_source",
        "option_ltp_source",
        "execution_entry_source",
        "source_quote_source",
        "source",
    ):
        value = str(payload.get(key) or "").strip().lower()
        if value:
            return value
    return ""


def _candidate_warnings_and_errors(
    *,
    line_number: int,
    event_name: str,
    payload: dict[str, Any],
    runtime_payload: dict[str, Any],
) -> tuple[list[AuditIssue], list[AuditIssue]]:
    warnings: list[AuditIssue] = []
    errors: list[AuditIssue] = []

    runtime_contract = build_feed_truth_contract(_candidate_feed_context(payload, runtime_payload))
    state = runtime_contract.state
    entries_allowed = bool(runtime_contract.entries_allowed)
    blockers = list(runtime_contract.blockers)
    blocker_list = _dedupe_preserve_order(list(payload.get("execution_truth_blockers") or payload.get("blockers") or []))
    raw_blocker_list = [str(reason or "").strip().upper() for reason in list(payload.get("execution_truth_blockers") or payload.get("blockers") or []) if str(reason or "").strip()]
    candidate_status = _candidate_status(payload)
    reportable_executable = bool(payload.get("reportable_executable"))
    final_action = str(payload.get("final_action") or "").strip().upper()
    execution_entry_status = str(payload.get("execution_entry_status") or "").strip().lower()
    visibility_bucket = str(payload.get("visibility_bucket") or "").strip().lower()
    execution_allowed = bool(payload.get("execution_allowed"))
    eligible_for_execution = payload.get("eligible_for_execution")
    if eligible_for_execution is None:
        eligible_for_execution = execution_allowed
    eligible_for_execution = bool(eligible_for_execution)
    trade_id = str(payload.get("trade_id") or "").strip()
    symbol = str(payload.get("symbol") or "").strip()
    quote_health_state = str(payload.get("quote_health_state") or "").strip().upper()
    runtime_state = str(payload.get("feed_runtime_state") or payload.get("runtime_state") or runtime_payload.get("runtime_state") or "").strip().upper()
    feed_truth_reason_code = str(payload.get("feed_truth_reason_code") or runtime_payload.get("feed_truth_reason_code") or "").strip().upper()
    feed_state = str(payload.get("feed_truth_state") or runtime_payload.get("feed_truth_state") or state or "").strip().upper()
    latency_action = str(payload.get("latency_guard_action") or runtime_payload.get("latency_guard", {}).get("latency_guard_action") or "").strip().upper()
    latency_reason = str(payload.get("latency_guard_reason") or runtime_payload.get("latency_guard", {}).get("latency_guard_reason") or "").strip().upper()

    if raw_blocker_list != blocker_list and raw_blocker_list:
        warnings.append(
            AuditIssue(
                severity=_SEVERITY_WARNING,
                code="blockers_not_deduped",
                message="Blocker list is not normalized deterministically",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"blockers": raw_blocker_list, "normalized_blockers": blocker_list},
            )
        )
    if len(raw_blocker_list) != len(blocker_list):
        errors.append(
            AuditIssue(
                severity=_SEVERITY_ERROR,
                code="duplicate_blockers",
                message="Duplicate blockers are present in normalized output",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"blockers": raw_blocker_list, "normalized_blockers": blocker_list},
            )
        )

    if any(_is_ok_marker(blocker) for blocker in raw_blocker_list):
        errors.append(
            AuditIssue(
                severity=_SEVERITY_ERROR,
                code="ok_marker_used_as_blocker",
                message="An *_OK marker appeared in blocker output",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"blockers": raw_blocker_list},
            )
        )

    blocked_state = state in _BLOCKED_STATES or runtime_state in _BLOCKED_STATES or feed_state in _BLOCKED_STATES
    if reportable_executable and not entries_allowed:
        errors.append(
            AuditIssue(
                severity=_SEVERITY_ERROR,
                code="unsafe_reportable_executable_under_blocked_feedtruth",
                message="reportable_executable=true while FeedTruth.entries_allowed=false",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"feed_truth_state": state, "blockers": list(runtime_contract.blockers)},
            )
        )
    if reportable_executable and runtime_state == "DISCONNECTED":
        errors.append(
            AuditIssue(
                severity=_SEVERITY_ERROR,
                code="unsafe_reportable_executable_under_disconnected_runtime",
                message="reportable_executable=true while runtime state is DISCONNECTED",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"runtime_state": runtime_state},
            )
        )
    if reportable_executable and state in {"RECOVERY_BLOCKED", "STALE", "AUTH_BLOCKED", "IMPORT_MISSING", "UNKNOWN", "DISCONNECTED"}:
        errors.append(
            AuditIssue(
                severity=_SEVERITY_ERROR,
                code="unsafe_reportable_executable_under_blocked_feed_state",
                message="reportable_executable=true while FeedTruth state is blocked",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"feed_truth_state": state, "blockers": list(runtime_contract.blockers)},
            )
        )
    if reportable_executable and quote_health_state == "OK" and blocked_state:
        warnings.append(
            AuditIssue(
                severity=_SEVERITY_WARNING,
                code="quote_health_ok_contradicts_blocked_feedtruth",
                message="quote_health.ok/state appears healthy while FeedTruth/runtime is blocked",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={
                    "feed_truth_state": state,
                    "runtime_state": runtime_state,
                    "quote_health_state": quote_health_state,
                },
            )
        )
    if reportable_executable and latency_action == "OK" and blocked_state:
        warnings.append(
            AuditIssue(
                severity=_SEVERITY_WARNING,
                code="latency_guard_ok_contradicts_blocked_feedtruth",
                message="latency guard reported OK while FeedTruth/runtime is blocked",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"latency_guard_action": latency_action, "latency_guard_reason": latency_reason},
            )
        )
    if event_name == "TB_TOP_EXECUTABLE_CANDIDATE" and blocked_state and reportable_executable:
        errors.append(
            AuditIssue(
                severity=_SEVERITY_ERROR,
                code="top_executable_emitted_under_blocked_truth",
                message="Top executable candidate was emitted while runtime/feed truth is blocked",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"feed_truth_state": state, "runtime_state": runtime_state},
            )
        )
    if event_name == "TB_TOP_EXECUTABLE_CANDIDATE" and not reportable_executable and blocked_state:
        warnings.append(
            AuditIssue(
                severity=_SEVERITY_WARNING,
                code="top_executable_marker_but_payload_blocked",
                message="Top executable marker appeared but payload was not reportable executable",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"visibility_bucket": visibility_bucket, "candidate_status": candidate_status},
            )
        )
    if candidate_status in {"blocked", "blocked_contract"} and not str(payload.get("final_emit_block_reason") or "").strip():
        warnings.append(
            AuditIssue(
                severity=_SEVERITY_WARNING,
                code="blocked_candidate_missing_final_emit_block_reason",
                message="Blocked candidate is missing final_emit_block_reason",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"candidate_status": candidate_status},
            )
        )
    if candidate_status in {"blocked", "blocked_contract"} and str(payload.get("execution_entry_status") or "").strip().lower() == "executable":
        warnings.append(
            AuditIssue(
                severity=_SEVERITY_WARNING,
                code="blocked_candidate_looks_executable_internally",
                message="Blocked candidate still has executable-looking inner fields",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={
                    "execution_entry_status": payload.get("execution_entry_status"),
                    "final_action": final_action,
                    "permission": payload.get("permission"),
                    "reportable_executable": reportable_executable,
                },
            )
        )
    if candidate_status == "executable" and not reportable_executable and (
        execution_entry_status == "executable" or final_action == "EXECUTE" or visibility_bucket == "executable" or execution_allowed or eligible_for_execution
    ):
        warnings.append(
            AuditIssue(
                severity=_SEVERITY_WARNING,
                code="looks_executable_but_not_reportable",
                message="Candidate looks executable internally but final output is blocked",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={
                    "execution_entry_status": execution_entry_status,
                    "final_action": final_action,
                    "execution_allowed": execution_allowed,
                    "eligible_for_execution": eligible_for_execution,
                },
            )
        )
    source = _candidate_fallback_source(payload)
    if reportable_executable and any(marker in source for marker in ("fallback", "recovered")):
        errors.append(
            AuditIssue(
                severity=_SEVERITY_ERROR,
                code="fallback_quote_marked_executable",
                message="Fallback or recovered quote source is reportable executable",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"source": source},
            )
        )
    if reportable_executable and not bool(payload.get("final_emit_block_reason")) and blocked_state:
        warnings.append(
            AuditIssue(
                severity=_SEVERITY_WARNING,
                code="blocked_candidate_missing_block_reason",
                message="Blocked candidate is missing a final emit block reason",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"feed_truth_state": state, "runtime_state": runtime_state},
            )
        )
    if reportable_executable and (
        feed_state in {"DISCONNECTED", "RECOVERY_BLOCKED", "STALE", "AUTH_BLOCKED", "IMPORT_MISSING", "UNKNOWN"}
        or runtime_state in {"DISCONNECTED", "RECOVERY_BLOCKED", "STALE", "AUTH_BLOCKED", "IMPORT_MISSING", "UNKNOWN"}
    ):
        errors.append(
            AuditIssue(
                severity=_SEVERITY_ERROR,
                code="reportable_executable_under_blocked_truth",
                message="Unsafe reportable executable output under blocked feed truth",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"feed_truth_state": feed_state, "runtime_state": runtime_state},
            )
        )
    if reportable_executable and execution_entry_status == "executable" and final_action == "BLOCK":
        errors.append(
            AuditIssue(
                severity=_SEVERITY_ERROR,
                code="executable_entry_but_block_final_action",
                message="Candidate has executable entry status with BLOCK final action while reportable",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"execution_entry_status": execution_entry_status, "final_action": final_action},
            )
        )

    optional_fields = [
        "execution_truth_blockers",
        "execution_truth_state",
        "execution_truth_blocked",
        "runtime_truth_consistent",
        "quote_health_state",
        "quote_health_stale_reasons",
        "feed_runtime_state",
        "latency_guard_action",
        "final_emit_block_reason",
    ]
    missing_optional = [field for field in optional_fields if field not in payload]
    if missing_optional:
        warnings.append(
            AuditIssue(
                severity=_SEVERITY_WARNING,
                code="missing_optional_audit_fields",
                message="Candidate event is missing optional audit fields",
                line_number=line_number,
                event=event_name,
                symbol=symbol or None,
                trade_id=trade_id or None,
                detail={"missing_optional_fields": missing_optional},
            )
        )

    return warnings, errors


def _diagnostic_details(payload: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if isinstance(payload.get("feed_health"), dict):
        details["feed_health"] = dict(payload["feed_health"])
    if isinstance(payload.get("quote_health"), dict):
        details["quote_health"] = dict(payload["quote_health"])
    for key in ("primary_regime", "regime_entropy", "regime_entropy_max", "regime_prob_max", "regime_prob_min", "regime_unstable_streak", "regime_unstable_block_after", "regime_unstable_debounced", "unstable_reasons"):
        if key in payload:
            details[key] = payload.get(key)
    return details


def _parse_latency_guard_line(line: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    details: dict[str, Any] = {"line": line}
    if isinstance(payload, dict):
        details.update({
            "action": payload.get("action"),
            "execution_mode": payload.get("execution_mode"),
            "feed_ok": payload.get("feed_ok"),
            "feed_reasons": payload.get("feed_reasons"),
        })
    return details


def build_feed_truth_audit_report(
    *,
    log_file: str | Path | None,
    runtime_file: str | Path | None,
) -> dict[str, Any]:
    log_path = Path(log_file).expanduser() if log_file else None
    runtime_path = Path(runtime_file).expanduser() if runtime_file else None
    log_exists = bool(log_path and log_path.exists())
    runtime_exists = bool(runtime_path and runtime_path.exists())
    log_lines = _load_lines(log_path) if log_exists else []
    runtime_payload = _read_json(runtime_path) if runtime_exists else {}
    runtime_contract = build_feed_truth_contract(runtime_payload) if runtime_payload else build_feed_truth_contract({})

    candidate_events: list[dict[str, Any]] = []
    diagnostic_events: list[dict[str, Any]] = []
    latency_events: list[dict[str, Any]] = []
    feed_truth_state_counts: Counter[str] = Counter()
    candidate_status_counts: Counter[str] = Counter()
    blocker_hist = Counter()
    warnings: list[AuditIssue] = []
    errors: list[AuditIssue] = []

    if runtime_payload:
        feed_truth_state_counts[_normalize_reason(runtime_contract.state) or "UNKNOWN"] += 1
        for blocker in runtime_contract.blockers:
            blocker_hist[_normalize_reason(blocker)] += 1
        if runtime_payload.get("quote_health") and isinstance(runtime_payload.get("quote_health"), dict):
            q_state = _normalize_reason(runtime_payload["quote_health"].get("state"))
            if q_state:
                feed_truth_state_counts[q_state] += 1

    for line_no, line in enumerate(log_lines, start=1):
        payload = _parse_payload(line)
        event_name = _line_event_name(line, payload)
        if event_name in _CANDIDATE_EVENTS and isinstance(payload, dict):
            candidate_events.append({"line_number": line_no, "event": event_name, "payload": payload, "line": line})
            status = _candidate_status(payload)
            candidate_status_counts[status] += 1
            ctx = _candidate_feed_context(payload, runtime_payload)
            runtime_state = _normalize_reason(ctx.get("runtime_state"))
            feed_state = _normalize_reason(ctx.get("feed_truth_state"))
            if runtime_state:
                feed_truth_state_counts[runtime_state] += 1
            if feed_state:
                feed_truth_state_counts[feed_state] += 1
            cand_warnings, cand_errors = _candidate_warnings_and_errors(
                line_number=line_no,
                event_name=event_name,
                payload=payload,
                runtime_payload=runtime_payload,
            )
            warnings.extend(cand_warnings)
            errors.extend(cand_errors)
            blocker_hist.update(_blocker_histogram(runtime_payload=ctx, candidate_payloads=[payload]))
            continue
        if event_name in _FEED_DIAGNOSTIC_EVENTS and isinstance(payload, dict):
            diagnostic_events.append({"line_number": line_no, "event": event_name, "payload": payload, "line": line})
            feed = payload.get("feed_health") if isinstance(payload.get("feed_health"), dict) else {}
            quote = payload.get("quote_health") if isinstance(payload.get("quote_health"), dict) else {}
            runtime_state = _normalize_reason(feed.get("runtime_state") or feed.get("state"))
            ws_connected = feed.get("ws_connected")
            quote_state = _normalize_reason(quote.get("state"))
            if runtime_state:
                feed_truth_state_counts[runtime_state] += 1
            if quote_state:
                feed_truth_state_counts[quote_state] += 1
            diagnostic_feed_blocked = _normalize_reason(feed.get("option_feed_block_reason"))
            if diagnostic_feed_blocked:
                blocker_hist[diagnostic_feed_blocked] += 1
            if ws_connected is False and quote_state in {"OK", "LIVE", "FRESH"}:
                warnings.append(
                    AuditIssue(
                        severity=_SEVERITY_WARNING,
                        code="quote_health_ok_while_runtime_blocked",
                        message="quote_health appears healthy while runtime/feed state is blocked",
                        line_number=line_no,
                        event=event_name,
                        detail=_diagnostic_details(payload),
                    )
                )
            continue
        if event_name in _LATENCY_GUARD_EVENTS:
            latency_events.append({"line_number": line_no, "event": event_name, "payload": payload or {}, "line": line})
            if isinstance(payload, dict):
                action = _normalize_reason(payload.get("action") or payload.get("latency_guard_action"))
                reason = _normalize_reason(payload.get("reason") or payload.get("latency_guard_reason"))
                if action == "OK" or reason == "LATENCY_GUARD_OK":
                    pass
                elif action:
                    blocker_hist[f"LATENCY_GUARD_{action}"] += 1
            continue
        if isinstance(payload, dict) and payload.get("feed_truth_state"):
            state = _normalize_reason(payload.get("feed_truth_state"))
            if state:
                feed_truth_state_counts[state] += 1

    if not log_exists:
        warnings.append(
            AuditIssue(
                severity=_SEVERITY_WARNING,
                code="missing_log_file",
                message="Log file is missing or unreadable",
                detail={"path": str(log_path) if log_path else None},
            )
        )
    if not runtime_exists:
        warnings.append(
            AuditIssue(
                severity=_SEVERITY_WARNING,
                code="missing_runtime_file",
                message="Runtime file is missing or unreadable",
                detail={"path": str(runtime_path) if runtime_path else None},
            )
        )
    if not log_exists and not runtime_exists:
        errors.append(
            AuditIssue(
                severity=_SEVERITY_ERROR,
                code="no_valid_input_sources",
                message="Neither log_file nor runtime_file is available",
            )
        )
    if not candidate_events and diagnostic_events:
        warnings.append(
            AuditIssue(
                severity=_SEVERITY_WARNING,
                code="no_candidate_events_but_feed_diagnostics_exist",
                message="No candidate events found, but feed diagnostics exist",
            )
        )
    if runtime_exists and _normalize_reason(runtime_contract.state) in {"DISCONNECTED", "RECOVERY_BLOCKED", "STALE", "AUTH_BLOCKED", "IMPORT_MISSING", "UNKNOWN"} and any(
        event["event"] == "TB_TOP_EXECUTABLE_CANDIDATE" and bool(event["payload"].get("reportable_executable"))
        for event in candidate_events
    ):
        errors.append(
            AuditIssue(
                severity=_SEVERITY_ERROR,
                code="blocked_runtime_with_executable_candidate",
                message="Runtime feed state is blocked but executable candidate was reported",
            )
        )

    reportable_executable_count = sum(1 for event in candidate_events if bool(event["payload"].get("reportable_executable")))
    blocked_candidate_count = sum(
        1
        for event in candidate_events
        if _candidate_status(event["payload"]) in {"blocked", "blocked_contract"} or str(event["payload"].get("visibility_bucket") or "").strip().lower() == "blocked"
    )
    advisory_candidate_count = sum(
        1
        for event in candidate_events
        if _candidate_status(event["payload"]) in {"advisory_only", "advisory", "queue_only", "near_executable"}
        or str(event["payload"].get("visibility_bucket") or "").strip().lower() == "advisory"
    )

    for event in candidate_events:
        payload = event["payload"]
        blockers = list(payload.get("execution_truth_blockers") or payload.get("blockers") or [])
        blocker_hist.update(_normalize_reason(blocker) for blocker in blockers if _normalize_reason(blocker) and not _is_ok_marker(blocker))
    for event in diagnostic_events:
        feed = event["payload"].get("feed_health") if isinstance(event["payload"].get("feed_health"), dict) else {}
        quote = event["payload"].get("quote_health") if isinstance(event["payload"].get("quote_health"), dict) else {}
        state = _normalize_reason(feed.get("runtime_state") or feed.get("state"))
        if state:
            feed_truth_state_counts[state] += 1
        q_state = _normalize_reason(quote.get("state"))
        if q_state:
            feed_truth_state_counts[q_state] += 1

    contradiction_count = len([issue for issue in errors])
    warning_count = len([issue for issue in warnings])
    verdict = "FAIL" if contradiction_count else ("WARN" if warning_count else "PASS")

    report = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "generated_epoch": time.time(),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_allowed": False,
        "verdict": verdict,
        "strict": False,
        "source_files_inspected": [
            {"path": str(log_path) if log_path else None, "exists": log_exists, "kind": "log_file"},
            {"path": str(runtime_path) if runtime_path else None, "exists": runtime_exists, "kind": "runtime_file"},
        ],
        "counts": {
            "total_candidate_events_inspected": len(candidate_events),
            "total_feed_diagnostic_events_inspected": len(diagnostic_events),
            "total_latency_guard_events_inspected": len(latency_events),
            "reportable_executable_count": reportable_executable_count,
            "blocked_candidate_count": blocked_candidate_count,
            "advisory_candidate_count": advisory_candidate_count,
            "contradiction_count": contradiction_count,
            "warning_count": warning_count,
        },
        "feed_truth_state_counts": dict(sorted(feed_truth_state_counts.items())),
        "candidate_status_counts": dict(sorted(candidate_status_counts.items())),
        "blocker_histogram": dict(sorted(blocker_hist.items(), key=lambda item: (-int(item[1]), str(item[0])))),
        "contradictions": [issue.to_dict() for issue in errors],
        "warnings": [issue.to_dict() for issue in warnings],
        "top_inconsistency_examples": [
            *(issue.to_dict() for issue in errors[:5]),
            *(issue.to_dict() for issue in warnings[:5]),
        ],
    }
    return report


def render_feed_truth_audit_markdown(report: dict[str, Any]) -> str:
    counts = report.get("counts") or {}
    lines = [
        "# FeedTruth Audit Report",
        "",
        f"- Verdict: `{report.get('verdict')}`",
        f"- Generated: `{report.get('generated_epoch')}`",
        f"- Read-only: `{report.get('read_only')}`",
        f"- Append: `{report.get('append')}`",
        f"- Is order action: `{report.get('is_order_action')}`",
        f"- Broker API called: `{report.get('broker_api_called')}`",
        f"- Live order allowed: `{report.get('live_order_allowed')}`",
        "",
        "## Counts",
        f"- Candidate events inspected: `{counts.get('total_candidate_events_inspected', 0)}`",
        f"- Feed diagnostic events inspected: `{counts.get('total_feed_diagnostic_events_inspected', 0)}`",
        f"- Latency guard events inspected: `{counts.get('total_latency_guard_events_inspected', 0)}`",
        f"- Reportable executable count: `{counts.get('reportable_executable_count', 0)}`",
        f"- Blocked candidate count: `{counts.get('blocked_candidate_count', 0)}`",
        f"- Advisory candidate count: `{counts.get('advisory_candidate_count', 0)}`",
        f"- Contradiction count: `{counts.get('contradiction_count', 0)}`",
        f"- Warning count: `{counts.get('warning_count', 0)}`",
        "",
        "## Feed Truth States",
        json.dumps(report.get("feed_truth_state_counts") or {}, indent=2, sort_keys=True),
        "",
        "## Candidate Status Counts",
        json.dumps(report.get("candidate_status_counts") or {}, indent=2, sort_keys=True),
        "",
        "## Blocker Histogram",
        json.dumps(report.get("blocker_histogram") or {}, indent=2, sort_keys=True),
        "",
        "## Contradictions",
        json.dumps(report.get("contradictions") or [], indent=2, sort_keys=True),
        "",
        "## Warnings",
        json.dumps(report.get("warnings") or [], indent=2, sort_keys=True),
        "",
        "## Top Inconsistency Examples",
        json.dumps(report.get("top_inconsistency_examples") or [], indent=2, sort_keys=True),
        "",
    ]
    return "\n".join(lines)


def write_feed_truth_audit_report(
    *,
    log_file: str | Path | None,
    runtime_file: str | Path | None,
    out: str | Path,
    fmt: str = "json",
    strict: bool = False,
) -> tuple[Path, dict[str, Any]]:
    report = build_feed_truth_audit_report(log_file=log_file, runtime_file=runtime_file)
    report["strict"] = bool(strict)
    output = Path(out).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    format_name = str(fmt or "json").strip().lower()
    if format_name == "markdown":
        output.write_text(render_feed_truth_audit_markdown(report), encoding="utf-8")
    else:
        output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output, report
