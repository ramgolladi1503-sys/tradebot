from __future__ import annotations

from core.debug_forensics.flow_contracts import get_flow_contract
from core.debug_forensics.models import EvidenceLoadResult, ForensicsFinding, ForensicsReport, Severity


def _event_names(evidence: EvidenceLoadResult) -> list[str]:
    return [event.event for event in evidence.events]


def _last_expected_seen(expected: tuple[str, ...], seen: set[str]) -> str | None:
    last: str | None = None
    for event in expected:
        if event in seen:
            last = event
        else:
            break
    return last


def _first_missing_expected(expected: tuple[str, ...], seen: set[str]) -> str | None:
    for event in expected:
        if event not in seen:
            return event
    return None


def _killed_hypotheses(last_confirmed: str | None) -> tuple[str, ...]:
    if not last_confirmed:
        return (
            "Do not blame WebSocket/feed/strategy/execution before MAIN_BOOT_STARTED is proven.",
            "Do not tune thresholds before startup evidence exists.",
        )
    if last_confirmed in {"MAIN_BOOT_STARTED", "MAIN_SAFETY_VALIDATED", "DB_READY_COMPLETED"}:
        return (
            "Do not blame WebSocket: live monitoring has not been proven reached.",
            "Do not blame strategy/ranking: orchestrator construction has not been proven complete.",
            "Do not blame broker execution: no execution gate has been proven reached.",
        )
    if last_confirmed.startswith("ORCHESTRATOR_") and last_confirmed != "ORCHESTRATOR_INIT_COMPLETED":
        return (
            "Do not blame dashboard: startup is still inside orchestrator construction.",
            "Do not blame strategy quality: live cycle has not been proven reached.",
            "Do not blame WebSocket unless FEED_START_REQUEST_BOUNDARY_REACHED or LIVE_MONITORING_ENTERED is proven.",
        )
    if last_confirmed.startswith("MARKET_DATA_WARMUP"):
        return (
            "Do not blame strategy/ranking: market-data warmup has not completed.",
            "Do not blame dashboard: constructor warmup is still the active boundary.",
            "Do not blame broker execution: no order path is involved in warmup evidence.",
        )
    if last_confirmed in {"LIVE_MONITORING_CALLING", "LIVE_MONITORING_ENTERED"}:
        return (
            "Do not blame constructor: orchestrator init is already proven complete.",
            "Do not blame market-data warmup unless warmup completion is missing in the same run.",
        )
    return (
        "Do not propose broad refactors; use the first missing event as the next proof boundary.",
    )


def _next_scope(first_missing: str | None) -> str:
    if not first_missing:
        return "Startup flow contract completed for the selected run. No diagnostic patch is required from this profile."
    if first_missing == "MAIN_BOOT_STARTED":
        return "Prove main/runtime guard entry before investigating downstream systems."
    if first_missing == "DB_READY_COMPLETED":
        return "Inspect DB readiness evidence; add only DB boundary proof if CALLING exists but COMPLETED is missing."
    if first_missing == "ORCHESTRATOR_INIT_ENTERED":
        return "Add or inspect proof between DB readiness and Orchestrator construction entry."
    if first_missing.startswith("ORCHESTRATOR_"):
        return f"Add the smallest constructor-stage proof before or around {first_missing}."
    if first_missing.startswith("MARKET_DATA_WARMUP"):
        return f"Add the smallest market-data warmup internal proof before or around {first_missing}."
    if first_missing.startswith("LIVE_MONITORING") or first_missing.startswith("RUNTIME_STATUS"):
        return f"Inspect live-monitoring/cycle boundary proof before or around {first_missing}."
    return f"Add the smallest deterministic proof for missing event {first_missing}."


def analyze_evidence(evidence: EvidenceLoadResult) -> ForensicsReport:
    contract = get_flow_contract(evidence.profile)
    findings: list[ForensicsFinding] = []

    if evidence.validation_errors:
        findings.append(
            ForensicsFinding(
                severity=Severity.INSUFFICIENT_EVIDENCE,
                code="EVIDENCE_VALIDATION_FAILED",
                message="Runtime evidence failed validation; refusing to infer startup state.",
                evidence={"errors": list(evidence.validation_errors)},
            )
        )
    if evidence.validation_warnings:
        findings.append(
            ForensicsFinding(
                severity=Severity.WARN,
                code="EVIDENCE_VALIDATION_WARNINGS",
                message="Runtime evidence loaded with warnings.",
                evidence={"warnings": list(evidence.validation_warnings)},
            )
        )

    names = _event_names(evidence)
    seen = set(names)
    forbidden_seen = sorted(event for event in seen if event in set(contract.forbidden_events))
    order_action_events = [event.event for event in evidence.events if event.is_order_action]

    if forbidden_seen:
        findings.append(
            ForensicsFinding(
                severity=Severity.SAFETY_VIOLATION,
                code="FORBIDDEN_EVENT_SEEN",
                message="Forbidden startup-profile event appeared in evidence.",
                evidence={"events": forbidden_seen},
            )
        )
    if order_action_events:
        findings.append(
            ForensicsFinding(
                severity=Severity.SAFETY_VIOLATION,
                code="ORDER_ACTION_EVIDENCE_SEEN",
                message="Startup forensics requires read-only evidence, but order-action evidence was found.",
                evidence={"events": order_action_events},
            )
        )

    last_confirmed = _last_expected_seen(contract.expected_events, seen)
    first_missing = _first_missing_expected(contract.expected_events, seen)

    if evidence.valid and not evidence.events:
        findings.append(
            ForensicsFinding(
                severity=Severity.INSUFFICIENT_EVIDENCE,
                code="NO_EVENTS_FOR_SELECTED_RUN",
                message="No runtime startup events exist for the selected run.",
            )
        )
    elif evidence.valid and first_missing:
        findings.append(
            ForensicsFinding(
                severity=Severity.BLOCKER,
                code="FIRST_MISSING_EXPECTED_EVENT",
                message=f"Startup flow stopped before expected event {first_missing}.",
                evidence={"last_confirmed_event": last_confirmed, "first_missing_event": first_missing},
            )
        )
    elif evidence.valid and not first_missing:
        findings.append(
            ForensicsFinding(
                severity=Severity.INFO,
                code="FLOW_CONTRACT_COMPLETE",
                message="Startup flow contract completed for the selected run.",
            )
        )

    return ForensicsReport(
        profile=contract.profile,
        evidence_valid=evidence.valid,
        selected_run_id=evidence.selected_run_id,
        last_confirmed_event=last_confirmed,
        first_missing_event=first_missing,
        findings=tuple(findings),
        killed_hypotheses=_killed_hypotheses(last_confirmed),
        next_diagnostic_scope=_next_scope(first_missing),
        forbidden_distractions=(
            "broker execution",
            "strategy scoring",
            "ranking thresholds",
            "dashboard UI",
            "profitability claims",
            "broad refactors",
        ),
        is_order_action=False,
    )
