from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.code_excellence.ariadne_clustering import AriadneCluster, NormalizedFinding, cluster_findings, load_normalized_findings
from tools.code_excellence.config import CodeExcellenceAgentParameters, load_code_excellence_agent_parameters
from tools.repo_forensics.config_loader import ConfigError, ForensicsConfig, load_config


class RemediationPlannerError(ValueError):
    """Raised when remediation planner input is missing or invalid."""


SEVERITY_ORDER = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "warning": 3,
    "low": 2,
    "info": 1,
    "unknown": 0,
}

CONFIDENCE_ORDER = {
    "CONFIRMED": 4,
    "LIKELY": 3,
    "POSSIBLE": 2,
    "UNKNOWN": 1,
}


@dataclass(frozen=True)
class FindingCluster:
    cluster_id: str
    title: str
    severity: str
    confidence_level: str
    root_cause: str
    affected_files: tuple[str, ...]
    findings: tuple[str, ...]
    unresolved_unknowns: tuple[str, ...]
    tags: tuple[str, ...]
    raw: dict[str, Any]


@dataclass(frozen=True)
class RemediationPlan:
    plan_id: str
    status: str
    source_cluster_id: str
    decision: str
    priority: str
    title: str
    root_cause: str
    files_to_change: tuple[str, ...]
    files_not_to_touch: tuple[str, ...]
    patch_behavior: str
    tests_required: tuple[str, ...]
    negative_tests_required: tuple[str, ...]
    evidence_required: tuple[str, ...]
    regression_risks: tuple[str, ...]
    done_means: tuple[str, ...]
    block_reasons: tuple[str, ...]
    proof_required: tuple[str, ...]


@dataclass(frozen=True)
class RemediationPlanningReport:
    source_path: str
    config_path: str
    plans: tuple[RemediationPlan, ...]
    blocked_count: int
    accepted_unknown_count: int

    @property
    def total_plans(self) -> int:
        return len(self.plans)


def load_remediation_source(path: str | Path) -> tuple[FindingCluster, ...]:
    """Load Ariadne clusters or normalized findings without executing product code."""

    source_path = Path(path)
    if not source_path.exists():
        raise RemediationPlannerError(f"remediation_source_not_found path={source_path}")
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RemediationPlannerError(f"remediation_source_must_be_json path={source_path} error={exc.msg}") from exc

    if _looks_like_normalized_findings_payload(payload):
        report = cluster_findings(load_normalized_findings(source_path))
        return tuple(_from_ariadne_cluster(cluster) for cluster in report.clusters)

    return parse_finding_clusters(payload)


def parse_finding_clusters(payload: object) -> tuple[FindingCluster, ...]:
    raw_items = _extract_cluster_items(payload)
    if not raw_items:
        raise RemediationPlannerError("remediation_source_has_no_clusters_or_findings")
    clusters = tuple(_normalize_cluster(item, index) for index, item in enumerate(raw_items, start=1))
    return tuple(sorted(clusters, key=lambda cluster: cluster.cluster_id))


def plan_remediation(
    *,
    source_path: str | Path,
    config_path: str | Path,
) -> RemediationPlanningReport:
    config = load_config(config_path)
    params = load_code_excellence_agent_parameters(config_path)
    clusters = load_remediation_source(source_path)
    plans = tuple(
        build_remediation_plan(
            cluster=cluster,
            config=config,
            params=params,
            index=index,
        )
        for index, cluster in enumerate(clusters, start=1)
    )
    blocked_count = sum(1 for plan in plans if plan.status == "blocked")
    accepted_unknown_count = sum(1 for plan in plans if plan.decision == "ACCEPTED_UNKNOWN")
    return RemediationPlanningReport(
        source_path=str(source_path),
        config_path=str(config_path),
        plans=plans,
        blocked_count=blocked_count,
        accepted_unknown_count=accepted_unknown_count,
    )


def build_remediation_plan(
    *,
    cluster: FindingCluster,
    config: ForensicsConfig,
    params: CodeExcellenceAgentParameters,
    index: int,
) -> RemediationPlan:
    daedalus = params.daedalus
    allowed_decisions = set(daedalus.require_list("decisions"))
    block_on = set(daedalus.require_list("block_on"))

    block_reasons = _block_reasons(cluster, block_on)
    decision = _select_decision(cluster, allowed_decisions, has_blocks=bool(block_reasons))
    priority = _priority_for(cluster, decision)
    files_to_change = _files_to_change(cluster)
    files_not_to_touch = _files_not_to_touch(config, files_to_change)
    tests_required = _tests_required(cluster, params)
    negative_tests_required = _negative_tests_required(cluster, params, has_blocks=bool(block_reasons))
    evidence_required = _evidence_required(cluster, params)
    proof_required = _proof_required(tests_required, negative_tests_required, evidence_required)

    return RemediationPlan(
        plan_id=f"CE-DAEDALUS-{index:04d}",
        status="blocked" if block_reasons else "draft",
        source_cluster_id=cluster.cluster_id,
        decision=decision,
        priority=priority,
        title=cluster.title,
        root_cause=cluster.root_cause,
        files_to_change=files_to_change,
        files_not_to_touch=files_not_to_touch,
        patch_behavior=_patch_behavior(cluster, decision),
        tests_required=tests_required,
        negative_tests_required=negative_tests_required,
        evidence_required=evidence_required,
        regression_risks=_regression_risks(cluster, files_to_change),
        done_means=_done_means(decision),
        block_reasons=block_reasons,
        proof_required=proof_required,
    )


def write_remediation_report(report: RemediationPlanningReport, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_remediation_report(report), encoding="utf-8")
    return path


def render_remediation_report(report: RemediationPlanningReport) -> str:
    lines: list[str] = [
        "# CE-06 Daedalus Remediation Planner Report",
        "",
        "## Scope Guard",
        "",
        "- Read-only remediation planning only.",
        "- No code mutation.",
        "- No auto-fix.",
        "- No auto-PR.",
        "- No product runtime execution.",
        "- No broker calls.",
        "",
        "## Summary",
        "",
        f"- source_path: `{report.source_path}`",
        f"- config_path: `{report.config_path}`",
        f"- total_plans: `{report.total_plans}`",
        f"- blocked_count: `{report.blocked_count}`",
        f"- accepted_unknown_count: `{report.accepted_unknown_count}`",
        "",
    ]
    for plan in report.plans:
        lines.extend(_render_plan(plan))
    return "\n".join(lines).rstrip() + "\n"


def _render_plan(plan: RemediationPlan) -> list[str]:
    lines = [
        f"## {plan.plan_id} — {plan.title}",
        "",
        f"- status: `{plan.status}`",
        f"- source_cluster_id: `{plan.source_cluster_id}`",
        f"- decision: `{plan.decision}`",
        f"- priority: `{plan.priority}`",
        f"- root_cause: {plan.root_cause or '_missing_'}",
        "",
        "### Scope",
        "",
        _bullet_list("files_to_change", plan.files_to_change),
        _bullet_list("files_not_to_touch", plan.files_not_to_touch),
        "",
        "### Change Plan",
        "",
        f"- patch_behavior: {plan.patch_behavior}",
        "",
        "### Proof Plan",
        "",
        _bullet_list("tests_required", plan.tests_required),
        _bullet_list("negative_tests_required", plan.negative_tests_required),
        _bullet_list("evidence_required", plan.evidence_required),
        _bullet_list("proof_required", plan.proof_required),
        "",
        "### Risk Model",
        "",
        _bullet_list("regression_risks", plan.regression_risks),
        "",
        "### Done Means",
        "",
        _bullet_list("done_means", plan.done_means),
    ]
    if plan.block_reasons:
        lines.extend(["", "### Block Reasons", "", _bullet_list("block_reasons", plan.block_reasons)])
    lines.append("")
    return lines


def _bullet_list(title: str, items: Iterable[str]) -> str:
    values = tuple(item for item in items if item)
    if not values:
        return f"- {title}: []"
    joined = "\n".join(f"  - `{item}`" for item in values)
    return f"- {title}:\n{joined}"


def _looks_like_normalized_findings_payload(payload: object) -> bool:
    if isinstance(payload, list):
        return bool(payload) and all(isinstance(item, Mapping) and "finding_id" in item for item in payload)
    if isinstance(payload, Mapping):
        findings = payload.get("findings")
        return isinstance(findings, list) and bool(findings) and all(
            isinstance(item, Mapping) and "finding_id" in item for item in findings
        )
    return False


def _from_ariadne_cluster(cluster: AriadneCluster) -> FindingCluster:
    root_cause = "" if cluster.root_cause_family in {"", "unknown"} else cluster.root_cause_family
    findings = tuple(finding.finding_id for finding in cluster.findings)
    affected_files = _as_unique_tuple(file_path for finding in cluster.findings for file_path in finding.files)
    confidence_level = _confidence_from_findings(cluster.findings)
    return FindingCluster(
        cluster_id=cluster.cluster_id,
        title=f"{cluster.root_cause_family} / {cluster.finding_type}",
        severity=cluster.severity if cluster.severity in SEVERITY_ORDER else "unknown",
        confidence_level=confidence_level,
        root_cause=root_cause,
        affected_files=affected_files,
        findings=findings,
        unresolved_unknowns=() if root_cause else ("root_cause_family_unknown",),
        tags=(cluster.finding_type, cluster.root_cause_family),
        raw={
            "cluster_id": cluster.cluster_id,
            "root_cause_family": cluster.root_cause_family,
            "finding_type": cluster.finding_type,
            "severity": cluster.severity,
            "findings": findings,
            "duplicate_count": cluster.duplicate_count,
            "related_finding_ids": cluster.related_finding_ids,
        },
    )


def _confidence_from_findings(findings: tuple[NormalizedFinding, ...]) -> str:
    values = {finding.confidence.strip().lower() for finding in findings}
    if "high" in values:
        return "CONFIRMED"
    if "medium" in values:
        return "LIKELY"
    if "low" in values:
        return "POSSIBLE"
    return "UNKNOWN"


def _extract_cluster_items(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [_require_mapping(item, "cluster") for item in payload]
    if not isinstance(payload, Mapping):
        raise RemediationPlannerError(f"remediation_source_root_must_be_mapping_or_list type={type(payload).__name__}")

    for key in ("finding_clusters", "clusters", "ariadne_clusters"):
        value = payload.get(key)
        if isinstance(value, list):
            return [_require_mapping(item, key) for item in value]

    for key in ("normalized_findings",):
        value = payload.get(key)
        if isinstance(value, list):
            return [_finding_as_cluster(_require_mapping(item, key), index) for index, item in enumerate(value, start=1)]

    if _looks_like_single_cluster(payload):
        return [dict(payload)]

    return []


def _normalize_cluster(item: dict[str, Any], index: int) -> FindingCluster:
    cluster_id = _first_text(item, ("cluster_id", "finding_cluster", "id", "finding_id")) or f"cluster-{index:04d}"
    title = _first_text(item, ("title", "summary", "message", "name")) or "Untitled remediation candidate"
    severity = (_first_text(item, ("severity", "risk", "level")) or "UNKNOWN").lower()
    confidence_level = (_first_text(item, ("confidence_level", "confidence")) or "UNKNOWN").upper()
    root_cause = _first_text(item, ("root_cause", "suspected_root_cause", "root_cause_summary", "root_cause_family"))
    if root_cause.lower() == "unknown":
        root_cause = ""
    affected_files = _as_unique_tuple(
        _collect_strings(item.get("affected_files"))
        + _collect_strings(item.get("files"))
        + _collect_strings(item.get("file_paths"))
        + [_first_text(item, ("file", "path", "file_path"))]
    )
    findings = _as_unique_tuple(
        _collect_strings(item.get("source_findings"))
        + _collect_strings(item.get("findings"))
        + [_first_text(item, ("finding_id", "id"))]
    )
    unresolved_unknowns = _as_unique_tuple(_collect_strings(item.get("unresolved_unknowns")))
    tags = _as_unique_tuple(_collect_strings(item.get("tags")) + [_first_text(item, ("category", "type", "finding_type"))])
    return FindingCluster(
        cluster_id=cluster_id,
        title=title,
        severity=severity if severity in SEVERITY_ORDER else "unknown",
        confidence_level=confidence_level if confidence_level in CONFIDENCE_ORDER else "UNKNOWN",
        root_cause=root_cause,
        affected_files=affected_files,
        findings=findings,
        unresolved_unknowns=unresolved_unknowns,
        tags=tags,
        raw=dict(item),
    )


def _finding_as_cluster(finding: dict[str, Any], index: int) -> dict[str, Any]:
    result = dict(finding)
    result.setdefault("cluster_id", _first_text(finding, ("finding_id", "id")) or f"finding-{index:04d}")
    result.setdefault("source_findings", [_first_text(finding, ("finding_id", "id")) or result["cluster_id"]])
    return result


def _looks_like_single_cluster(payload: Mapping[str, object]) -> bool:
    return any(key in payload for key in ("cluster_id", "finding_id", "root_cause", "suspected_root_cause", "affected_files"))


def _block_reasons(cluster: FindingCluster, block_on: set[str]) -> tuple[str, ...]:
    reasons: list[str] = []
    if "no_root_cause" in block_on and not cluster.root_cause.strip():
        reasons.append("no_root_cause")
    if "broad_fix" in block_on and len(cluster.affected_files) > 5:
        reasons.append("broad_fix")
    if "missing_negative_tests" in block_on and _is_safety_or_runtime_cluster(cluster) and not cluster.root_cause.strip():
        reasons.append("missing_negative_tests")
    if "no_non_touch_list" in block_on and not cluster.affected_files:
        reasons.append("no_non_touch_list")
    return tuple(reasons)


def _select_decision(cluster: FindingCluster, allowed_decisions: set[str], *, has_blocks: bool) -> str:
    if has_blocks or cluster.confidence_level == "UNKNOWN" or cluster.unresolved_unknowns:
        return _require_decision("ACCEPTED_UNKNOWN", allowed_decisions)
    raw_decision = _first_text(cluster.raw, ("decision", "recommended_decision"))
    if raw_decision and raw_decision in allowed_decisions:
        return raw_decision
    status = (_first_text(cluster.raw, ("status", "classification")) or "").lower()
    if status in {"false_positive", "false-positive"}:
        return _require_decision("FALSE_POSITIVE", allowed_decisions)
    if SEVERITY_ORDER[cluster.severity] >= SEVERITY_ORDER["high"]:
        return _require_decision("FIX_NOW", allowed_decisions)
    if SEVERITY_ORDER[cluster.severity] >= SEVERITY_ORDER["medium"]:
        return _require_decision("BACKLOG", allowed_decisions)
    return _require_decision("DEFER", allowed_decisions)


def _require_decision(decision: str, allowed_decisions: set[str]) -> str:
    if decision not in allowed_decisions:
        raise ConfigError(f"daedalus_decision_not_configured decision={decision}")
    return decision


def _priority_for(cluster: FindingCluster, decision: str) -> str:
    if decision == "FIX_NOW" and cluster.severity == "critical":
        return "P0"
    if decision == "FIX_NOW":
        return "P1"
    if decision in {"BACKLOG", "ACCEPTED_UNKNOWN"}:
        return "P2"
    return "P3"


def _files_to_change(cluster: FindingCluster) -> tuple[str, ...]:
    return _as_unique_tuple(
        _collect_strings(cluster.raw.get("files_to_change"))
        + _collect_strings(cluster.raw.get("allowed_files"))
        + list(cluster.affected_files)
    )


def _files_not_to_touch(config: ForensicsConfig, files_to_change: tuple[str, ...]) -> tuple[str, ...]:
    allowed = set(files_to_change)
    configured: list[str] = []
    for values in config.critical_modules.values():
        configured.extend(values)
    configured.extend(_collect_strings(config.data.get("entrypoints", {}).get("required", [])))
    configured.extend(_collect_strings(config.data.get("entrypoints", {}).get("optional", [])))
    return tuple(path for path in _as_unique_tuple(configured) if path not in allowed)[:50]


def _tests_required(cluster: FindingCluster, params: CodeExcellenceAgentParameters) -> tuple[str, ...]:
    classes = params.minerva.require_list("classes")
    tests = ["regression_test_for_root_cause"]
    if _is_safety_or_runtime_cluster(cluster) and "SAFETY_REGRESSION" in classes:
        tests.append("safety_regression_test")
    if "EVIDENCE_CONTRACT" in classes and _mentions(cluster, ("evidence", "report", "log")):
        tests.append("evidence_contract_test")
    if "INTEGRATION_WIRING" in classes and _mentions(cluster, ("wiring", "runtime_flow", "entrypoint")):
        tests.append("integration_wiring_test")
    return _as_unique_tuple(tests)


def _negative_tests_required(
    cluster: FindingCluster,
    params: CodeExcellenceAgentParameters,
    *,
    has_blocks: bool,
) -> tuple[str, ...]:
    configured = params.minerva.require_list("required_negative_tests")
    if has_blocks:
        return ("planner_blocks_weak_or_unknown_rca",)
    if _is_safety_or_runtime_cluster(cluster):
        return configured
    return ("broken_behavior_cannot_pass",)


def _evidence_required(cluster: FindingCluster, params: CodeExcellenceAgentParameters) -> tuple[str, ...]:
    evidence = list(params.daedalus.require_list("output_required"))
    if _is_safety_or_runtime_cluster(cluster):
        evidence.extend(params.cerberus.require_list("required_non_action_fields"))
    return _as_unique_tuple(evidence)


def _proof_required(
    tests_required: tuple[str, ...],
    negative_tests_required: tuple[str, ...],
    evidence_required: tuple[str, ...],
) -> tuple[str, ...]:
    return _as_unique_tuple(
        list(tests_required)
        + list(negative_tests_required)
        + list(evidence_required)
        + ["repo-forensics-pr-gate"]
    )


def _patch_behavior(cluster: FindingCluster, decision: str) -> str:
    if decision in {"DEFER", "FALSE_POSITIVE", "ACCEPTED_UNKNOWN"}:
        return "No implementation patch approved by this plan."
    if cluster.root_cause:
        return f"Repair the scoped contract for root cause: {cluster.root_cause}"
    return "Blocked until root cause is proven."


def _regression_risks(cluster: FindingCluster, files_to_change: tuple[str, ...]) -> tuple[str, ...]:
    risks = ["fix_changes_behavior_without_matching_contract_proof"]
    if len(files_to_change) > 3:
        risks.append("multi_file_patch_may_expand_scope")
    if _is_safety_or_runtime_cluster(cluster):
        risks.append("safety_boundary_regression")
    if _mentions(cluster, ("dashboard", "ui")):
        risks.append("dashboard_claim_may_diverge_from_runtime_truth")
    return tuple(risks)


def _done_means(decision: str) -> tuple[str, ...]:
    if decision in {"DEFER", "FALSE_POSITIVE", "ACCEPTED_UNKNOWN"}:
        return ("decision_recorded_with_reason", "no_product_code_changed")
    return (
        "scoped_patch_matches_files_to_change",
        "all_required_tests_pass",
        "required_evidence_is_updated",
        "repo-forensics-pr-gate_passes",
    )


def _is_safety_or_runtime_cluster(cluster: FindingCluster) -> bool:
    return _mentions(cluster, ("safety", "broker", "live", "paper", "sim", "runtime", "order", "execution"))


def _mentions(cluster: FindingCluster, needles: tuple[str, ...]) -> bool:
    haystack = " ".join(
        [
            cluster.title,
            cluster.root_cause,
            cluster.severity,
            cluster.confidence_level,
            " ".join(cluster.tags),
            " ".join(cluster.affected_files),
            json.dumps(cluster.raw, sort_keys=True, default=str),
        ]
    ).lower()
    return any(needle.lower() in haystack for needle in needles)


def _first_text(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (dict, list, tuple, set)):
            return str(value).strip()
    return ""


def _collect_strings(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Mapping):
        collected: list[str] = []
        for key in ("file", "path", "file_path", "id", "finding_id"):
            text = _first_text(value, (key,))
            if text:
                collected.append(text)
        return collected
    if isinstance(value, Iterable):
        collected: list[str] = []
        for item in value:
            collected.extend(_collect_strings(item))
        return collected
    text = str(value).strip()
    return [text] if text else []


def _as_unique_tuple(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)


def _require_mapping(item: object, source: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise RemediationPlannerError(f"remediation_source_item_must_be_mapping source={source} type={type(item).__name__}")
    return item
